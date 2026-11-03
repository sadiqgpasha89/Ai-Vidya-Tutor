"""Token-bucket rate limiting (in memory; per process)."""
from __future__ import annotations

import threading
import time


class Limiter:
    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, per_minute: int, burst: int | None = None) -> tuple[bool, float]:
        """-> (allowed, seconds_until_next_token)."""
        capacity = float(burst or per_minute)
        rate = per_minute / 60.0
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (capacity, now))
            tokens = min(capacity, tokens + (now - last) * rate)
            if tokens >= 1:
                self._buckets[key] = (tokens - 1, now)
                allowed, wait = True, 0.0
            else:
                self._buckets[key] = (tokens, now)
                allowed, wait = False, (1 - tokens) / rate
            if len(self._buckets) > 50000:  # forget idle keys
                cutoff = now - 600
                self._buckets = {k: v for k, v in self._buckets.items() if v[1] > cutoff}
        return allowed, wait

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


limiter = Limiter()
