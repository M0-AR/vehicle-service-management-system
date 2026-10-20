"""Tenant-aware structured logging + request metrics.

Every request log line carries request_id, tenant_id and user_id (feature
presence is enough — never log payloads or PII; see docs/SECURITY.md).
"""

from __future__ import annotations

import json
import logging
import time
import uuid

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import get_settings

settings = get_settings()

HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests", ["method", "route", "status"]
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds", "HTTP request duration", ["route"]
)
RATE_LIMIT_REJECTIONS = Counter(
    "rate_limit_rejections_total", "Requests rejected by throttling", ["scope"]
)

_EXTRA_FIELDS = (
    "tenant_id",
    "tenant_slug",
    "user_id",
    "request_id",
    "method",
    "path",
    "route",
    "status",
    "duration_ms",
    "client",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            route = _route_template(request)
            HTTP_REQUESTS.labels(request.method, route, "500").inc()
            logging.getLogger("vsms.request").exception(
                "unhandled error",
                extra={"request_id": request_id, "route": route},
            )
            raise

        duration = (time.perf_counter() - start) * 1000
        route = _route_template(request)
        HTTP_REQUESTS.labels(request.method, route, str(response.status_code)).inc()
        HTTP_DURATION.labels(route).observe(duration / 1000)

        response.headers["X-Request-ID"] = request_id
        logging.getLogger("vsms.request").info(
            "request",
            extra={
                "request_id": request_id,
                "tenant_id": getattr(request.state, "tenant_id", None),
                "tenant_slug": getattr(request.state, "tenant_slug", None),
                "user_id": getattr(request.state, "user_id", None),
                "method": request.method,
                "path": request.url.path,
                "route": route,
                "status": response.status_code,
                "duration_ms": round(duration, 1),
                "client": request.client.host if request.client else None,
            },
        )
        return response


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", "__unmatched__")
