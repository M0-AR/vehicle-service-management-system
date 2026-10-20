"""Region-aware engine resolution (geo/data-residency routing).

`REGION_DATABASE_URLS` is a JSON map, e.g.
    {"eu": "postgresql+asyncpg://.../vsms_eu",
     "us": "postgresql+asyncpg://.../vsms_us"}
Tenants carry `region`; provisioning writes the tenant into the engine for its
region. Single-region deployments leave the map empty and everything resolves
to the primary DATABASE_URL.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

_engines: dict[str, AsyncEngine] = {}
_sessionmakers: dict[str, async_sessionmaker[AsyncSession]] = {}


def _make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)


def engine_for_region(region: str | None) -> AsyncEngine:
    key = region or settings.default_region
    if key not in _engines:
        url = settings.regions.get(key, settings.database_url)
        _engines[key] = _make_engine(url)
    return _engines[key]


def sessionmaker_for_region(region: str | None) -> async_sessionmaker[AsyncSession]:
    key = region or settings.default_region
    if key not in _sessionmakers:
        _sessionmakers[key] = async_sessionmaker(
            engine_for_region(key),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmakers[key]
