"""Ollama akış istemcisi: tüm Localaitest düzeneklerinin ortak istemcisi (hukuk, kod, uzun bağlam bu dosyaya yönlenir).

Kullanıcı kuralı (2026-10-24):
- Örnekleme ayarı yalnızca modelin önerdiği değerdir: `model_ayarlari.json` (kaynağıyla). Kayıtta olmayan model koşmaz.
- Bağlam NUM_CTX = 131072 (bu makinenin üst sınırı; model daha azını destekliyorsa o). Token bütçesi yok: num_predict
  gönderilmez; model bağlam dolana kadar yazabilir. Ollama bağlam dolunca bağlamı kaydırmaz, done_reason="length" ile durur
  (2026-10-24 doğrulandı: num_ctx 4096'da istem 30 + çıktı 4064 = 4094, length).

Döngü koruması: düşünme ve cevap metni AYRI izlenir. Her ~1.500 yeni karakterde, metnin son 300 karakterlik penceresi
(boşluklar tek boşluğa indirilmiş) son 30.000 karakterde en az 6 kez geçiyorsa akış kesilir: done_reason="dongu".
Pencerenin en az yarısı kesintisiz olarak istemde geçiyorsa (kaynaktan alıntı) eşik 12'dir. Eşik verisi (2026-10-24,
tüm eski kayıtlar): başarıyla biten çağrılarda alıntı dışı en yüksek tekrar 4, istemden alıntıyla 8 (hukuk g2).
Eski kural (9.000'de 3) bu çağrılarda sınırdaydı (mali-4 akış ortasında 3'e ulaştı). Eşikler gözlenen en yüksek meşru değerin 2 ve 4 üstündedir.

Durma süresi: akıştan STALL_TIMEOUT saniye hiç veri gelmezse çağrı kesilir (done_reason="zaman_asimi"). Toplam süre
sınırı yoktur; uzunluğu bağlam ve döngü koruması belirler. 300 sn = model yükleme (~45 sn) + 128k istem okuma
(~3.000 token/sn ile ~45 sn) en kötü durumunun yaklaşık 3 katı.
Test için `opener=` ile sahte akış verilebilir (Ollama'ya bağlanılmaz).
"""
import json
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

OLLAMA = "http://localhost:11434"

NUM_CTX = 131072
STALL_TIMEOUT = 300
AYAR_DOSYASI = Path(__file__).with_name("model_ayarlari.json")
BOLUM = None  # koşucunun o an çalıştırdığı bölüm ("kart_bolum" ayarlı modellerde profil seçimi için)

LOOP_CHECK_EVERY = 1500
LOOP_WINDOW = 300
LOOP_LOOKBACK = 30000
LOOP_MIN_COUNT = 6
QUOTE_MIN_COUNT = 12



def _post(path, payload, timeout=60):
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def _get(path):
    with urllib.request.urlopen(OLLAMA + path, timeout=30) as r:
        return json.loads(r.read())


def loaded_models():
    return _get("/api/ps").get("models", [])


def version():
    try:
        return _get("/api/version").get("version")
    except Exception:
        return None


def has_model(name):
    """Model yerelde kurulu mu? (/api/tags)"""
    tags = _get("/api/tags").get("models", [])
    return any(m.get("name") == name or m.get("model") == name for m in tags)


def unload_all():
    for m in loaded_models():
        with _post("/api/generate", {"model": m["name"], "keep_alive": 0}) as r:
            r.read()
    for _ in range(60):
        if not loaded_models():
            return
        time.sleep(1)


def model_info(model):
    with _post("/api/show", {"model": model}) as r:
        return json.loads(r.read())


def model_context_limit(model):
    """Modelin desteklediği bağlam (model_info içindeki *.context_length); okunamazsa None."""
    info = model_info(model).get("model_info", {})
    vals = [v for k, v in info.items() if k.endswith(".context_length")]
    return int(vals[0]) if vals else None


def package_parameters(model):
    """Ollama paketinin parametreleri (`ollama show --parameters`), sözlük olarak."""
    out = {}
    for line in model_info(model).get("parameters", "").splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0] != "stop":
            out[parts[0]] = parts[1].strip().strip('"')
    return out


def sampling_for(model):
    """Önerilen örnekleme ayarı: (istekle gönderilecek seçenekler, kayıt bilgisi). Kayıtta yoksa koşu durur."""
    reg = json.loads(AYAR_DOSYASI.read_text(encoding="utf-8"))["modeller"]
    entry = reg.get(model)
    if entry is None:
        raise SystemExit(f"DURDU: {model} için önerilen ayar kaydı yok ({AYAR_DOSYASI}). Değer tahmin edilmez; "
                         "model kartındaki önerilen değerleri kaynağıyla ekleyin.")
    if entry["ayar"] == "paket":
        params = package_parameters(model)
        beklenen = entry.get("beklenen") or {}
        if not beklenen:
            raise SystemExit(f"DURDU: {model} kaydında model kartının 'beklenen' değerleri yok; karşılaştırma yapılamaz.")
        farklar = {k: {"kart": v, "paket": params.get(k)} for k, v in beklenen.items()
                   if params.get(k) is None or abs(float(params[k]) - float(v)) > 1e-9}
        if farklar:
            raise SystemExit(f"DURDU: {model} paketinin ayarları model kartından farklı: {json.dumps(farklar, ensure_ascii=False)}")
        return {}, {"ayar": "paket", "kaynak": entry["kaynak"], "beklenen": beklenen, "paket_parametreleri": params}
    if entry["ayar"] == "kart_bolum":
        # Model kartı iş türüne göre ayrı ayar öneriyorsa: bölüm -> profil eşlemesi (kullanıcı kararı) kayıttadır.
        # Koşucu her bölümden önce BOLUM'u ayarlar; ayarlanmamışsa değer tahmin edilmez, koşu durur.
        if BOLUM == "on_kontrol":
            return {}, {"ayar": "kart_bolum", "kaynak": entry["kaynak"], "profiller": entry["profiller"], "bolumler": entry["bolumler"]}
        profil = entry["bolumler"].get(BOLUM) if BOLUM else None
        if profil is None:
            raise SystemExit(f"DURDU: {model} için '{BOLUM}' bölümünün ayar profili kayıtlı değil ({AYAR_DOSYASI}).")
        degerler = entry["profiller"][profil]
        return dict(degerler), {"ayar": "kart_bolum", "kaynak": entry["kaynak"], "bolum": BOLUM, "profil": profil, "degerler": degerler}
    return dict(entry["degerler"]), {"ayar": "kart", "kaynak": entry["kaynak"], "degerler": entry["degerler"]}


def options_for(model, messages=None, tools=None, num_ctx=None, offline=False):
    """İsteğin seçenekleri ve kayıt bilgisi: önerilen örnekleme + num_ctx. num_predict yok (sınır yalnızca bağlam)."""
    if num_ctx is None:
        num_ctx = NUM_CTX
        if not offline:
            limit = model_context_limit(model)
            if limit is None:
                raise SystemExit(f"DURDU: {model} için bağlam sınırı okunamadı; {NUM_CTX} desteği doğrulanamadı.")
            if limit < NUM_CTX:
                raise SystemExit(f"DURDU: {model} en çok {limit} bağlamı destekliyor; sabit {NUM_CTX} kullanılamaz (alta düşülmez).")
    sampling, meta = sampling_for(model) if not offline else ({}, {"ayar": "offline"})
    return dict(sampling, num_ctx=num_ctx), dict(meta, num_ctx=num_ctx)


def _norm(text):
    return re.sub(r"\s+", " ", text)


def is_quote(pat, source):
    """Pencerenin en az yarısı kesintisiz olarak istemde geçiyor mu (kaynaktan alıntı)?"""
    if not source:
        return False
    half = len(pat) // 2
    return any(pat[i:i + half] in source for i in range(0, len(pat) - half + 1, 10))


def detect_loop(text, window=LOOP_WINDOW, lookback=LOOP_LOOKBACK, min_count=LOOP_MIN_COUNT, source=""):
    """Metnin son `window` karakteri (boşluk normalize), son `lookback` karakterde en az `min_count` kez (örtüşmesiz)
    geçiyor mu? Pencere istemden alıntıysa eşik QUOTE_MIN_COUNT olur (alıntı tekrarı meşrudur ama sonsuz değildir)."""
    t = _norm(text)
    if len(t) < window * min_count:
        return False
    pat = t[-window:]
    need = QUOTE_MIN_COUNT if is_quote(pat, source) else min_count
    return t[-lookback:].count(pat) >= need


class LoopWatch:
    """Tek bir akışın (düşünme ya da cevap) döngü denetçisi."""

    def __init__(self, source=""):
        self.parts = []
        self.since = 0
        self.source = source

    def feed(self, chunk):
        self.parts.append(chunk)
        self.since += len(chunk)
        if self.since < LOOP_CHECK_EVERY:
            return False
        self.since = 0
        text = "".join(self.parts)
        self.parts = [text]
        return detect_loop(text, source=self.source)


class GpuSampler(threading.Thread):
    """nvidia-smi ile VRAM kullanımı ve GPU yükünü örnekler."""

    def __init__(self, interval=0.5):
        super().__init__(daemon=True)
        self.interval = interval
        self.samples = []
        self._halt = threading.Event()

    def run(self):
        while not self._halt.is_set():
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu,power.draw", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=5).stdout.strip().split(",")
                self.samples.append((float(out[0]), float(out[1]), float(out[2])))
            except Exception:
                pass
            self._halt.wait(self.interval)

    def stop(self):
        self._halt.set()
        self.join(timeout=5)
        if not self.samples:
            return {}
        mem = [s[0] for s in self.samples]
        util = [s[1] for s in self.samples]
        pw = [s[2] for s in self.samples]
        return {"vram_peak_mb": max(mem), "gpu_util_avg": round(sum(util) / len(util), 1),
                "gpu_util_peak": max(util), "power_avg_w": round(sum(pw) / len(pw), 1)}


def classify_error(err):
    """Hata metnini sınıflar: 'zaman_asimi' | 'ag' (bağlantı; yeniden denenebilir) | 'ollama' | None."""
    if not err:
        return None
    e = str(err)
    if "wall timeout" in e or "timed out" in e or "TimeoutError" in e:
        return "zaman_asimi"
    if any(k in e for k in ("URLError", "ConnectionError", "ConnectionReset", "ConnectionRefused", "RemoteDisconnected", "BrokenPipe", "IncompleteRead")):
        return "ag"
    return "ollama"


def chat(model, messages, options, think=True, timeout=STALL_TIMEOUT, keep_alive="30m", tools=None, opener=None):
    """Akışlı sohbet. content, thinking, tool_calls ve metrikleri döndürür.

    options: `options_for()` çıktısı (önerilen örnekleme + num_ctx).
    timeout: durma süresi; akıştan bu kadar saniye veri gelmezse çağrı kesilir. Toplam süre sınırı yoktur.
    opener: test için sahte akış sağlayıcı; çağrı opener(payload, timeout) biçimindedir ve satır dizisi veren bir
    bağlam yöneticisi döndürür. Verilirse GPU örnekleme ve /api/ps sorgusu yapılmaz.
    """
    # shift/truncate kapalı: bağlam dolunca Ollama eski içeriği atıp devam etmez, sığmayan istemi sessizce kırpmaz
    # (Ollama 0.40'ta bazı model ailelerinde kaydırma varsayılan açık; LFM2.5'te ölçüldü, 2026-10-25).
    payload = {"model": model, "messages": messages, "stream": True, "think": think, "options": options, "keep_alive": keep_alive,
               "shift": False, "truncate": False}
    if tools:
        payload["tools"] = tools
    offline = opener is not None
    if opener is None:
        opener = lambda p, t: _post("/api/chat", p, timeout=t)  # noqa: E731
    tool_calls = []
    gpu = None
    if not offline:
        gpu = GpuSampler()
        gpu.start()
    t0 = time.perf_counter()
    t_first_think = t_first_content = t_last_think = None
    think_chunks = content_chunks = 0
    thinking, content = [], []
    final = {}
    error = None
    forced_reason = None
    loop_source = None
    ps_info = None
    source = _norm(" ".join(str(m.get("content") or "") for m in messages))
    watch_think, watch_content = LoopWatch(source), LoopWatch(source)
    try:
        with opener(payload, timeout) as resp:
            for raw in resp:
                if not raw.strip():
                    continue
                msg = json.loads(raw)
                if "error" in msg:
                    error = msg["error"]
                    break
                now = time.perf_counter()
                m = msg.get("message", {})
                if m.get("thinking"):
                    if t_first_think is None:
                        t_first_think = now
                        if not offline:
                            try:
                                ps_info = loaded_models()
                            except Exception:
                                pass
                    t_last_think = now
                    think_chunks += 1
                    thinking.append(m["thinking"])
                    if watch_think.feed(m["thinking"]):
                        forced_reason, loop_source = "dongu", "thinking"
                        break
                if m.get("content"):
                    if t_first_content is None:
                        t_first_content = now
                        if ps_info is None and not offline:
                            try:
                                ps_info = loaded_models()
                            except Exception:
                                pass
                    content_chunks += 1
                    content.append(m["content"])
                    if watch_content.feed(m["content"]):
                        forced_reason, loop_source = "dongu", "content"
                        break
                if m.get("tool_calls"):
                    if t_first_content is None:
                        t_first_content = now
                    tool_calls.extend(m["tool_calls"])
                if msg.get("done"):
                    final = msg
                    break
    except urllib.error.HTTPError as e:  # sunucu hata gövdesini sakla
        try:
            body = e.read().decode("utf-8", "replace")[:2000]
        except Exception:
            body = ""
        error = f"HTTPError {e.code}: {body}"
    except Exception as e:  # ağ / zaman aşımı
        error = f"{type(e).__name__}: {e}"
    t_end = time.perf_counter()
    gpu_stats = gpu.stop() if gpu else {}
    kind = classify_error(error)
    if kind == "zaman_asimi":
        forced_reason = "zaman_asimi"
    # Bitiş paketi (done:true) gelmeden normal biten akış: eksik aktarım; içerik saklanır ama başarılı yanıt sayılmaz.
    if not final and not error and forced_reason is None:
        forced_reason, kind, error = "eksik_akis", "eksik_akis", "akış bitiş paketi gelmeden kapandı"

    ns = 1e9
    # Zorla kesilen akışta (döngü, durma, hata) Ollama son ölçümleri göndermez: bunlar 0 değil "ölçülmedi" (None) sayılır.
    akis_tam = bool(final)

    def _dur(k):
        v = final.get(k)
        return v / ns if isinstance(v, (int, float)) else None

    load_s = _dur("load_duration")
    pe_count = final.get("prompt_eval_count") if akis_tam else None
    pe_s = _dur("prompt_eval_duration")
    ev_count = final.get("eval_count") if akis_tam else None
    ev_s = _dur("eval_duration")
    olcum_tam = akis_tam and None not in (pe_count, ev_count, pe_s, ev_s)
    first_tok = min([t for t in (t_first_think, t_first_content) if t is not None], default=None)

    gpu_pct = None
    if ps_info:
        for p in ps_info:
            if p.get("name", "").split(":")[0] in model or model in p.get("name", ""):
                if p.get("size"):
                    gpu_pct = round(100 * p.get("size_vram", 0) / p["size"], 1)
                    gpu_stats["model_mem_gb"] = round(p["size"] / 1e9, 2)

    thinking_s = None
    if t_first_think is not None:
        end_think = t_first_content if t_first_content is not None else (t_last_think or t_end)
        thinking_s = round(end_think - t_first_think, 2)

    metrics = {
        "model": model,
        "error": error,
        "error_kind": kind,
        "done_reason": forced_reason or final.get("done_reason"),
        "loop_source": loop_source,
        "wall_s": round(t_end - t0, 2),
        "akis_tam": akis_tam,
        "olcum_tam": olcum_tam,
        "load_s": round(load_s, 2) if load_s is not None else None,
        "work_s": round((t_end - t0) - (load_s or 0), 2),
        "prompt_eval_s": round(pe_s, 3) if pe_s is not None else None,
        "eval_s": round(ev_s, 3) if ev_s is not None else None,
        "ttft_s": round(first_tok - t0, 2) if first_tok else None,
        "thinking_s": thinking_s,
        "answer_s": round(t_end - t_first_content, 2) if t_first_content else None,
        "prompt_tokens": pe_count,
        "prompt_tok_per_s": round(pe_count / pe_s, 1) if pe_count is not None and pe_s else None,
        "eval_tokens": ev_count,
        "thinking_akis_parcasi": think_chunks,
        "cevap_akis_parcasi": content_chunks,
        "gen_tok_per_s": round(ev_count / ev_s, 1) if ev_count is not None and ev_s else None,
        "gpu_offload_pct": gpu_pct,
        **gpu_stats,
    }
    return {"content": "".join(content), "thinking": "".join(thinking), "tool_calls": tool_calls, "metrics": metrics}
