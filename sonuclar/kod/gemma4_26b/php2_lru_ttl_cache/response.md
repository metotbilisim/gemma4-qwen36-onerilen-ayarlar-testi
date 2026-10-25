```php
<?php

class LruCache implements \Countable
{
    private int $capacity;
    private \Closure $clock;
    /** @var array<string, array{value: mixed, expires_at: float|null, prev: string|null, next: string|null}> */
    private array $items = [];
    private ?string $head = null;
    private ?string $tail = null;
    private \SplPriorityQueue $ttlHeap;

    public function __construct(int $capacity, ?\Closure $clock = null)
    {
        if ($capacity < 1) {
            throw new \InvalidArgumentException("Capacity must be at least 1.");
        }
        $this->capacity = $capacity;
        $this->clock = $clock ?? fn(): float => microtime(true);
        $this->ttlHeap = new \SplPriorityQueue();
    }

    public function set(string $key, mixed $value, ?float $ttl = null): void
    {
        if ($ttl !== null && $ttl <= 0) {
            throw new \InvalidArgumentException("TTL must be positive.");
        }

        $now = ($this->clock)();

        // If the key already exists, remove it to update its position and expiration
        if (array_key_exists($key, $this->items)) {
            $this->removeNode($key);
        } elseif (count($this->items) >= $this->capacity) {
            // If adding a new key would exceed capacity, try to free space by cleaning expired entries
            $this->cleanExpired();
            // If still at capacity after cleaning, evict the least recently used entry
            if (count($this->items) >= $this->capacity) {
                $this->removeNode($this->tail);
            }
        }

        $expiresAt = ($ttl !== null) ? ($now + $ttl) : null;
        $this->addHead($key, $value, $expiresAt);

        if ($expiresAt !== null) {
            // SplPriorityQueue is a max-heap, so we negate the timestamp to simulate a min-heap
            $this->ttlHeap->insert(['key' => $key, 'expires_at' => $expiresAt], -$expiresAt);
        }
    }

    public function get(string $key, mixed $default = null): mixed
    {
        if (!array_key_exists($key, $this->items)) {
            return $default;
        }

        $now = ($this->clock)();
        $entry = $this->items[$key];

        if ($entry['expires_at'] !== null && $entry['expires_at'] <= $now) {
            $this->removeNode($key);
            return $default;
        }

        // Move the accessed entry to the head (most recently used)
        $value = $entry['value'];
        $expiresAt = $entry['expires_at'];
        $this->removeNode($key);
        $this->addHead($key, $value, $expiresAt);

        return $value;
    }

    public function has(string $key): bool
    {
        if (!array_key_exists($key, $this->items)) {
            return false;
        }

        $now = ($this->clock)();
        $entry = $this->items[$key];

        if ($entry['expires_at'] !== null && $entry['expires_at'] <= $now) {
            $this->removeNode($key);
            return false;
        }

        return true;
    }

    public function delete(string $key): bool
    {
        if (!array_key_exists($key, $this->items)) {
            return false;
        }

        $now = ($this->clock)();
        $entry = $this->items[$key];
        $isExpired = ($entry['expires_at'] !== null && $entry['expires_at'] <= $now);

        $this->removeNode($key);

        return !$isExpired;
    }

    public function count(): int
    {
        $now = ($this->clock)();
        $count = 0;
        foreach ($this->items as $entry) {
            if ($entry['expires_at'] === null || $entry['expires_at'] > $now) {
                $count++;
            }
        }
        return $count;
    }

    public function keys(): array
    {
        $now = ($this->clock)();
        $keys = [];
        // Traverse from tail (LRU) to head (MRU)
        $curr = $this->tail;
        while ($curr !== null) {
            $entry = $this->items[$curr];
            if ($entry['expires_at'] === null || $entry['expires_at'] > $now) {
                $keys[] = $curr;
            }
            $curr = $entry['next'];
        }
        return $keys;
    }

    private function removeNode(string $key): void
    {
        $node = $this->items[$key];
        $prev = $node['prev']; // Less recent
        $next = $node['next']; // More recent

        if ($prev !== null) {
            $this->items[$prev]['next'] = $next;
        } else {
            $this->head = $next;
        }

        if ($next !== null) {
            $this->items[$next]['prev'] = $prev;
        } else {
            $this->tail = $prev;
        }

        unset($this->items[$key]);
    }

    private function addHead(string $key, mixed $value, ?float $expiresAt): void
    {
        $this->items[$key] = [
            'value' => $value,
            'expires_at' => $expiresAt,
            'prev' => null,
            'next' => $this->head,
        ];

        if ($this->head !== null) {
            $this->items[$this->head]['prev'] = $key;
        }

        $this->head = $key;

        if ($this->tail === null) {
            $this->tail = $key;
        }
    }

    private function cleanExpired(): void
    {
        $now = ($this->clock)();
        while (!$this->ttlHeap->isEmpty()) {
            $top = $this->ttlHeap->top();
            // If the earliest expiration in the heap is in the future, stop
            if ($top['expires_at'] > $now) {
                break;
            }

            $this->ttlHeap->extract();
            $key = $top['key'];

            // Lazy deletion: only remove if the key still exists and has the same expiration time
            if (array_key_exists($key, $this->items) && $this->items[$key]['expires_at'] === $top['expires_at']) {
                $this->removeNode($key);
            }
        }
    }
}
```