"""A sliding-window rate limit kept in memory: one process, reset on restart. Enough for a single-instance pilot."""

import math
import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float, clock=time.monotonic):
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        return hits

    def retry_after(self, key: str) -> int:
        """Seconds until `key` may try again; 0 if it may now."""
        with self._lock:
            now = self.clock()
            hits = self._prune(key, now)
            if len(hits) < self.limit:
                return 0
            return max(1, math.ceil(hits[0] + self.window - now))

    def hit(self, key: str) -> None:
        with self._lock:
            now = self.clock()
            self._prune(key, now).append(now)
            if len(self._hits) > 10_000:  # forget keys that have gone quiet, so memory stays bounded
                for k in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
                    del self._hits[k]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
