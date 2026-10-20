"""Pembatasan percobaan (rate limit) sederhana untuk endpoint autentikasi.

Jendela geser di memori proses. Cukup untuk satu proses/worker; bila API dijalankan
dengan beberapa worker atau replika, ganti penyimpanan ke Redis (``settings.redis_url``)
dengan antarmuka yang sama.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.config import settings

_MAX_KEYS = 20_000


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        """Catat satu percobaan. Mengembalikan detik tunggu bila melewati batas, selain itu None."""
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > _MAX_KEYS:
                self._purge(now)
            q = self._hits[key]
            while q and now - q[0] >= window_seconds:
                q.popleft()
            if len(q) >= limit:
                return max(1, int(window_seconds - (now - q[0])) + 1)
            q.append(now)
            return None

    def _purge(self, now: float) -> None:
        for k in [k for k, q in self._hits.items() if not q or now - q[-1] > 3600]:
            self._hits.pop(k, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check(scope: str, key: str, limit: int, window_seconds: int) -> None:
    """Lempar 429 bila ``key`` pada ``scope`` melewati ``limit`` percobaan per ``window_seconds``."""
    if not settings.rate_limit_enabled:
        return
    retry = limiter.hit(f"{scope}:{key}", limit, window_seconds)
    if retry is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Terlalu banyak percobaan. Coba lagi beberapa saat lagi.",
            headers={"Retry-After": str(retry)},
        )


def check_ip(request: Request, scope: str, limit: int, window_seconds: int) -> None:
    check(scope, client_ip(request), limit, window_seconds)
