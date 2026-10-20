from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.db.session import SessionLocal

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/livez")
async def livez() -> dict:
    return {"status": "ok", "service": settings.app_name, "env": settings.env}


@router.get("/readyz")
async def readyz() -> JSONResponse:
    checks: dict[str, str] = {}
    healthy = True

    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc.__class__.__name__}"
        healthy = False

    try:
        client = await limiter.client()
        if client is not None:
            await client.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "degraded"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"degraded: {exc.__class__.__name__}"

    return JSONResponse(
        {"status": "ok" if healthy else "unavailable", "checks": checks},
        status_code=200 if healthy else 503,
    )


@router.get("/version")
async def version() -> dict:
    return {"version": "1.0.0", "env": settings.env}
