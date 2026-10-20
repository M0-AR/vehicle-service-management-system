from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.routers import (
    accounting as accounting_router,
    inventory as inventory_router,
    audit as audit_router,
    auth as auth_router,
    booking as booking_router,
    campaigns as campaigns_router,
    locations as locations_router,
    push as push_router,
    customers as customers_router,
    dashboard as dashboard_router,
    estimates as estimates_router,
    health as health_router,
    inspections as inspections_router,
    invoices as invoices_router,
    notifications as notifications_router,
    orders as orders_router,
    public as public_router,
    reviews as reviews_router,
    settings as settings_router,
    staff as staff_router,
    suppliers as suppliers_router,
    vehicles as vehicles_router,
    webhooks as webhooks_router,
)
from app.core.config import get_settings
from app.core.observability import RequestContextMiddleware, setup_logging
from app.core.rate_limit import PreAuthRateLimitMiddleware
from app.core.tenancy import TenantResolutionMiddleware

setup_logging()
log = logging.getLogger("vsms")
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json" if settings.env == "dev" else None,
    docs_url=f"{settings.api_v1_prefix}/docs" if settings.env == "dev" else None,
    redoc_url=None,
)

# Starlette runs the LAST added middleware first (outermost). Desired order:
# RequestContext (ids + logs) -> CORS -> TenantResolution -> PreAuthRateLimit.
app.add_middleware(PreAuthRateLimitMiddleware)
app.add_middleware(TenantResolutionMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(RequestContextMiddleware)

app.include_router(health_router.router, prefix=settings.api_v1_prefix)
app.include_router(public_router.router, prefix=settings.api_v1_prefix)
app.include_router(auth_router.router, prefix=settings.api_v1_prefix)
app.include_router(vehicles_router.router, prefix=settings.api_v1_prefix)
app.include_router(customers_router.router, prefix=settings.api_v1_prefix)
app.include_router(orders_router.router, prefix=settings.api_v1_prefix)
app.include_router(estimates_router.router, prefix=settings.api_v1_prefix)
app.include_router(invoices_router.router, prefix=settings.api_v1_prefix)
app.include_router(inventory_router.router, prefix=settings.api_v1_prefix)
app.include_router(accounting_router.router, prefix=settings.api_v1_prefix)
app.include_router(campaigns_router.router, prefix=settings.api_v1_prefix)
app.include_router(locations_router.router, prefix=settings.api_v1_prefix)
app.include_router(push_router.router, prefix=settings.api_v1_prefix)
app.include_router(suppliers_router.router, prefix=settings.api_v1_prefix)
app.include_router(dashboard_router.router, prefix=settings.api_v1_prefix)
app.include_router(staff_router.router, prefix=settings.api_v1_prefix)
app.include_router(audit_router.router, prefix=settings.api_v1_prefix)
app.include_router(settings_router.router, prefix=settings.api_v1_prefix)
app.include_router(booking_router.router, prefix=settings.api_v1_prefix)
app.include_router(inspections_router.router, prefix=settings.api_v1_prefix)
app.include_router(notifications_router.router, prefix=settings.api_v1_prefix)
app.include_router(reviews_router.router, prefix=settings.api_v1_prefix)
app.include_router(webhooks_router.router, prefix=settings.api_v1_prefix)


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Prometheus scrape endpoint. Not exposed publicly by the edge proxy."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    log.exception(
        "unhandled exception",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "route": request.url.path,
        },
    )
    return JSONResponse(
        {
            "detail": "Internal server error",
            "request_id": getattr(request.state, "request_id", None),
        },
        status_code=500,
    )
