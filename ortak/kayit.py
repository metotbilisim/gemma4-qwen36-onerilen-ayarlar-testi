"""Kayıt ve devam kuralları (v2, tüm bölümler).

Bir görev biriminin klasöründeki dosyalar:
  deneme.json  çağrıdan önce yazılır ("basladi") ve birim kimliğini taşır
  ham.json     model yanıtı gelir gelmez yazılır (content, thinking, tool_calls, metrics); puanlamadan önce
  record.json  puanlamadan sonra yazılır; KANONİK kayıt budur (results.jsonl rapor betiğince bunlardan türetilir)
Birim kimliği (meta): {"bolum", "model", "anahtar"}; her durumda kayda yazılır.
Durumlar (record.json "durum"):
  tamam            model yanıtı alındı ve puanlandı
  puanlama_hatasi  ham yanıt var, puanlama hata verdi ya da puanlayıcı ölçüm yapamadı (grading_status
                   measurement_missing/grader_error); devamda model çağrılmadan yeniden puanlanır
  olcum_eksik      çağrı başladı ama ham yanıt kaydedilmeden kesildi; model yeniden ÇAĞRILMAZ (sıfır puan değil)
Devam: "tamam" ya da "olcum_eksik" kayıt varsa atlanır. Tüm yazımlar atomiktir (geçici dosya + yeniden adlandırma).
"""
import datetime as dt
import json
import os
import traceback
from pathlib import Path


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def atomic_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_json(path: Path, obj):
    atomic_text(path, json.dumps(obj, indent=2, ensure_ascii=False))


def append_jsonl(path: Path, obj):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _kimlik_denetle(d: Path, meta: dict, kayit: dict, ad: str):
    eski = {k: kayit.get(k) for k in ("bolum", "model", "anahtar")}
    if any(v is not None for v in eski.values()) and eski != meta:
        raise SystemExit(f"DURDU: {d / ad} başka bir birime ait ({eski}), beklenen {meta}.")


def birim(d: Path, meta: dict, cagir, puanla, jsonl: Path = None):
    """Bir görev birimini kurallara göre yürütür.

    meta: {"bolum", "model", "anahtar"}  birim kimliği
    cagir() -> ham yanıt sözlüğü (content, thinking, tool_calls, metrics)
    puanla(ham) -> kayıt sözlüğü (kimlik alanları puanlayıcı tarafından değiştirilemez)
    jsonl: kullanılmaz (geri uyum); results.jsonl rapor betiğince kayıtlardan türetilir.
    Döner: ("atla" | "yeni" | "yeniden_puanlandi" | "puanlama_hatasi" | "olcum_eksik", kayıt ya da None)
    """
    meta = {"bolum": meta["bolum"], "model": meta["model"], "anahtar": meta["anahtar"]}
    rec_p, ham_p, den_p = d / "record.json", d / "ham.json", d / "deneme.json"
    if rec_p.exists():
        eski = json.loads(rec_p.read_text(encoding="utf-8"))
        _kimlik_denetle(d, meta, eski, "record.json")
        if eski.get("durum") != "puanlama_hatasi":
            return "atla", None
    d.mkdir(parents=True, exist_ok=True)
    if den_p.exists():
        _kimlik_denetle(d, meta, json.loads(den_p.read_text(encoding="utf-8")), "deneme.json")
    if ham_p.exists():
        ham, durum = json.loads(ham_p.read_text(encoding="utf-8")), "yeniden_puanlandi"
    elif den_p.exists():
        rec = {"durum": "olcum_eksik", "not": "çağrı başladı ama ham yanıt kaydedilmeden kesildi; model yeniden çağrılmadı",
               "deneme": json.loads(den_p.read_text(encoding="utf-8"))}
        rec.update(meta)
        rec["bitis"] = _now()
        atomic_json(rec_p, rec)
        return "olcum_eksik", rec
    else:
        atomic_json(den_p, dict(meta, durum="basladi", zaman=_now()))
        ham = cagir()
        atomic_json(ham_p, ham)
        atomic_text(d / "response.md", ham.get("content") or "")
        atomic_text(d / "thinking.txt", ham.get("thinking") or "")
        durum = "yeni"
    try:
        rec = puanla(ham)
        rec["durum"] = "tamam"
        if durum == "yeniden_puanlandi":
            rec["yeniden_puanlandi"] = _now()
        # Puanlayıcı ölçüm yapamadıysa (altyapı/puanlayıcı hatası) kayıt kapanmaz: devamda model çağrılmadan yeniden puanlanır.
        gs = (rec.get("grade") or {}).get("grading_status")
        if gs in ("measurement_missing", "grader_error"):
            rec["durum"], durum = "puanlama_hatasi", "puanlama_hatasi"
            rec.setdefault("hata", f"puanlayıcı ölçüm yapamadı ({gs}): {(rec.get('grade') or {}).get('sebep')}")
    except Exception as e:  # puanlama hatası ölçüm hatasıdır, model başarısızlığı değil
        rec = {"durum": "puanlama_hatasi", "hata": f"{type(e).__name__}: {e}", "iz": traceback.format_exc()[-2000:]}
        durum = "puanlama_hatasi"
    rec.update(meta)
    rec["bitis"] = _now()
    atomic_json(rec_p, rec)
    return durum, rec
