from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """One session = one transaction per request.

    Commits on success, rolls back on error. The RLS context (set via
    `set_config(..., true)`) lives exactly as long as this transaction, so a
    pooled connection can never carry tenant context into the next request.
    """
    async with SessionLocal() as session:
        async with session.begin():
            yield session
