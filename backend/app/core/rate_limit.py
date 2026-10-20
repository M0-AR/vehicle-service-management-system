"""Per-tenant and per-IP throttling (noisy-neighbor protection).

Redis fixed-window counters. Failure policy: fail OPEN with a loud log —
availability bias for a small platform; documented in docs/SECURITY.md.
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings

log = logging.getLogger("vsms.ratelimit")
settings = get_settings()


class RateLimiter:
    def __init__(self, url: str) -> None:
        self._url = url
        self._client: aioredis.Redis | None = None

    async def client(self) -> aioredis.Redis | None:
        if self._client is None:
            try:
                self._client = aioredis.from_url(
                    self._url, encoding="utf-8", decode_responses=True
                )
                await self._client.ping()
            except Exception as exc:  # noqa: BLE001
                log.error("redis unavailable, rate limiting degraded: %s", exc)
                self._client = None
        return self._client

    async def hit(self, key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        if not settings.rate_limit_enabled:
            return True, 0
        client = await self.client()
        if client is None:
            return True, 0
        try:
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, window_seconds)
            if count > limit:
                ttl = await client.ttl(key)
                return False, max(ttl, 1)
            return True, 0
        except Exception as exc:  # noqa: BLE001
            log.error("rate limit check failed (fail-open): %s", exc)
            return True, 0


limiter = RateLimiter(settings.redis_url)

SKIP_PATHS = {"/api/v1/livez", "/api/v1/readyz", "/metrics"}


class PreAuthRateLimitMiddleware(BaseHTTPMiddleware):
    """Coarse protection before authentication.

    Keyed by tenant routing hint when present, else client IP. Authenticated
    per-plan limits are enforced in `api/deps.py` (get_auth_context).
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/") or path in SKIP_PATHS:
            return await call_next(request)

        state = request.state
        scope = (
            getattr(state, "tenant_slug", None)
            or getattr(state, "host_domain", None)
            or (request.client.host if request.client else "unknown")
        )
        allowed, retry_after = await limiter.hit(
            f"rl:pre:{scope}:{path.split('/')[3] if len(path.split('/')) > 3 else 'root'}",
            settings.preauth_rate_per_minute,
        )
        if not allowed:
            return JSONResponse(
                {"detail": "Too many requests, slow down."},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
