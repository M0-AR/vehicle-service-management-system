from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.location import Location

DEFAULT_NAME = "Main location"


async def count_locations(session: AsyncSession) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(Location)) or 0
    )


async def ensure_default(session: AsyncSession, tenant_id: uuid.UUID) -> Location:
    existing = await session.scalar(
        select(Location).where(Location.is_default.is_(True)).limit(1)
    )
    if existing is not None:
        return existing
    first = await session.scalar(select(Location).order_by(Location.created_at).limit(1))
    if first is not None:
        first.is_default = True
        await session.flush()
        return first
    location = Location(tenant_id=tenant_id, name=DEFAULT_NAME, is_default=True)
    session.add(location)
    await session.flush()
    return location


async def make_default(session: AsyncSession, location: Location) -> None:
    await session.execute(
        update(Location)
        .where(Location.id != location.id)
        .values(is_default=False)
    )
    location.is_default = True
    await session.flush()
