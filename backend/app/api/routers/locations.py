from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.models.location import Location
from app.models.service import ServiceOrder
from app.schemas.common import Ok
from app.schemas.location import LocationIn, LocationOut, LocationUpdate
from app.services import audit, locations

router = APIRouter(prefix="/locations", tags=["locations"])

WRITE_ROLES = ("owner", "admin")


async def _get_location(session: AsyncSession, location_id: uuid.UUID) -> Location:
    location = await session.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


async def _unique_name(
    session: AsyncSession, name: str, exclude_id: uuid.UUID | None = None
) -> str:
    name = name.strip()
    stmt = select(func.count()).select_from(Location).where(
        func.lower(Location.name) == name.lower()
    )
    if exclude_id is not None:
        stmt = stmt.where(Location.id != exclude_id)
    if await session.scalar(stmt):
        raise HTTPException(status_code=409, detail="A location with this name already exists")
    return name


@router.get("", response_model=list[LocationOut])
async def list_locations(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> list[LocationOut]:
    rows = await session.scalars(
        select(Location).order_by(Location.is_default.desc(), Location.name)
    )
    return [LocationOut.model_validate(row) for row in rows]


@router.post("", response_model=LocationOut, status_code=201)
async def create_location(
    payload: LocationIn,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> LocationOut:
    ctx.require_rank(*WRITE_ROLES)
    name = await _unique_name(session, payload.name)
    location = Location(
        tenant_id=ctx.tenant_id,
        name=name,
        address=payload.address,
        phone=payload.phone,
        is_default=False,
    )
    session.add(location)
    await session.flush()
    if payload.is_default or await locations.count_locations(session) == 1:
        await locations.make_default(session, location)
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="location.created",
        entity="location",
        entity_id=location.id,
        meta={"name": location.name, "is_default": location.is_default},
    )
    return LocationOut.model_validate(location)


@router.patch("/{location_id}", response_model=LocationOut)
async def update_location(
    location_id: uuid.UUID,
    payload: LocationUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> LocationOut:
    ctx.require_rank(*WRITE_ROLES)
    location = await _get_location(session, location_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        data["name"] = await _unique_name(session, data["name"], location.id)
    if data.get("is_default") is False and location.is_default:
        raise HTTPException(
            status_code=422,
            detail="Make another location the default instead of unsetting this one",
        )
    for key, value in data.items():
        if key != "is_default":
            setattr(location, key, value)
    if data.get("is_default"):
        await locations.make_default(session, location)
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="location.default_changed"
        if data.get("is_default")
        else "location.updated",
        entity="location",
        entity_id=location.id,
        meta={"fields": sorted(data), "name": location.name},
    )
    return LocationOut.model_validate(location)


@router.delete("/{location_id}", response_model=Ok)
async def delete_location(
    location_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> Ok:
    ctx.require_rank(*WRITE_ROLES)
    location = await _get_location(session, location_id)
    if await locations.count_locations(session) <= 1:
        raise HTTPException(
            status_code=409, detail="A workspace needs at least one location"
        )
    if location.is_default:
        raise HTTPException(
            status_code=409,
            detail="Make another location the default before deleting this one",
        )
    used = await session.scalar(
        select(func.count())
        .select_from(ServiceOrder)
        .where(ServiceOrder.location_id == location.id)
    )
    if used:
        raise HTTPException(
            status_code=409,
            detail="This location has service orders; keep it for history",
        )
    await session.delete(location)
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="location.deleted",
        entity="location",
        entity_id=location.id,
        meta={"name": location.name},
    )
    return Ok(detail="Location deleted")
