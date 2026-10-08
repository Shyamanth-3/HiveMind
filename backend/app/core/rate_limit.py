"""
In-memory sliding-window rate limiting for sensitive / expensive operations.

Limits are per API PROCESS: with several API replicas each keeps its own counters, so the effective limit is
N x configured. That is acceptable for a single-instance deployment; a shared store (e.g. Redis) would be needed for
strict distributed limits (documented limitation, not pretended away). Behind a reverse proxy run uvicorn with
`--proxy-headers --forwarded-allow-ips=<proxy>` so `request.client.host` is the real client address.
"""

import threading
import time
from collections import deque

from fastapi import HTTPException, Request

from app.core.config import settings
from app.core.metrics import metrics

_MAX_KEYS = 50_000


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, bucket: str, key: str, limit: int, window_s: float) -> float | None:
        """Record one request. Returns None if allowed, else the seconds until a slot frees up."""
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > _MAX_KEYS:  # bound memory: drop idle keys
                self._hits = {k: q for k, q in self._hits.items() if q and now - q[-1] < window_s}
            q = self._hits.setdefault((bucket, key), deque())
            while q and now - q[0] >= window_s:
                q.popleft()
            if len(q) >= limit:
                return max(1.0, window_s - (now - q[0]))
            q.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def enforce(bucket: str, key: str, limit: int, window_s: float) -> None:
    """Raise HTTP 429 (with Retry-After) when `key` exceeded `limit` requests in `window_s`. limit <= 0 = unlimited."""
    if not settings.RATE_LIMIT_ENABLED or limit <= 0:
        return
    retry = limiter.hit(bucket, key, limit, window_s)
    if retry is not None:
        metrics.inc("rate_limited", bucket=bucket)
        raise HTTPException(status_code=429, detail="Too many requests. Please retry later.",
                            headers={"Retry-After": str(int(retry))})


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
