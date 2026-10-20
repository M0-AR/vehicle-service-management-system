from __future__ import annotations

import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, require_roles
from app.db.session import get_db
from app.models.customer import Customer
from app.models.service import ServiceOrder
from app.models.vehicle import Vehicle
from app.schemas.common import Ok, Page
from app.schemas.vehicle import (
    VehicleIn,
    VehicleOut,
    VehicleSummary,
    VehicleUpdate,
    VinDecodeOut,
)
from app.services import audit, entitlements
from app.services import vin as vin_service

router = APIRouter(prefix="/vehicles", tags=["vehicles"])

OPEN_STATUSES = ("scheduled", "in_progress", "awaiting_parts")


async def _get_vehicle(session: AsyncSession, vehicle_id: uuid.UUID) -> Vehicle:
    vehicle = await session.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return vehicle


async def _check_customer(session: AsyncSession, customer_id: uuid.UUID | None) -> None:
    if customer_id is None:
        return
    exists = await session.get(Customer, customer_id)
    if exists is None:
        raise HTTPException(status_code=422, detail="Customer not found")


@router.get("", response_model=Page[VehicleSummary])
async def list_vehicles(
    q: str | None = Query(default=None, max_length=100),
    vehicle_status: str | None = Query(default=None, alias="status"),
    customer_id: uuid.UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> Page[VehicleSummary]:
    base = select(Vehicle)
    if q:
        pattern = f"%{q.strip()}%"
        base = base.where(
            or_(
                Vehicle.plate_number.ilike(pattern),
                Vehicle.make.ilike(pattern),
                Vehicle.model.ilike(pattern),
            )
        )
    if vehicle_status:
        base = base.where(Vehicle.status == vehicle_status)
    if customer_id:
        base = base.where(Vehicle.customer_id == customer_id)

    total = await session.scalar(
        select(func.count()).select_from(base.subquery())
    )
    rows = await session.scalars(
        base.order_by(Vehicle.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    vehicles = list(rows)

    ids = [v.id for v in vehicles]
    customer_names: dict[uuid.UUID, str] = {}
    open_counts: dict[uuid.UUID, int] = {}
    if ids:
        name_rows = await session.execute(
            select(Customer.id, Customer.name).where(
                Customer.id.in_([v.customer_id for v in vehicles if v.customer_id])
            )
        )
        customer_names = {r.id: r.name for r in name_rows}
        count_rows = await session.execute(
            select(ServiceOrder.vehicle_id, func.count())
            .where(ServiceOrder.vehicle_id.in_(ids))
            .where(ServiceOrder.status.in_(OPEN_STATUSES))
            .group_by(ServiceOrder.vehicle_id)
        )
        open_counts = {r[0]: int(r[1]) for r in count_rows}

    return Page[VehicleSummary](
        items=[
            VehicleSummary(
                id=v.id,
                plate_number=v.plate_number,
                make=v.make,
                model=v.model,
                year=v.year,
                status=v.status,
                customer_name=customer_names.get(v.customer_id) if v.customer_id else None,
                open_orders=open_counts.get(v.id, 0),
            )
            for v in vehicles
        ],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=VehicleOut, status_code=201)
async def create_vehicle(
    payload: VehicleIn,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager", "mechanic")),
    session: AsyncSession = Depends(get_db),
) -> VehicleOut:
    await entitlements.check_limit(session, ctx.plan, "vehicles", "vehicles")
    await _check_customer(session, payload.customer_id)

    vehicle = Vehicle(**payload.model_dump(), tenant_id=ctx.tenant_id)
    session.add(vehicle)
    try:
        await session.flush()
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A vehicle with this plate number already exists",
        )
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="vehicle.created",
        entity="vehicle",
        entity_id=vehicle.id,
        meta={"plate_number": vehicle.plate_number},
    )
    return VehicleOut.model_validate(vehicle)


@router.get("/decode-vin", response_model=VinDecodeOut)
async def decode_vehicle_vin(
    vin: str = Query(min_length=1, max_length=40),
    ctx: AuthContext = Depends(get_auth_context),
) -> VinDecodeOut:
    """Decode a VIN via the free NHTSA vPIC service (server-side proxy)."""
    cleaned = vin_service.normalize_vin(vin)
    if not vin_service.is_valid_vin(cleaned):
        raise HTTPException(
            status_code=422,
            detail="That does not look like a valid 17-character VIN",
        )
    try:
        result = await vin_service.decode_vin(cleaned)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(
            status_code=502,
            detail="The VIN decoder service is unreachable right now",
        )
    return VinDecodeOut(**result)


@router.get("/{vehicle_id}", response_model=VehicleOut)
async def get_vehicle(
    vehicle_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> VehicleOut:
    return VehicleOut.model_validate(await _get_vehicle(session, vehicle_id))


@router.patch("/{vehicle_id}", response_model=VehicleOut)
async def update_vehicle(
    vehicle_id: uuid.UUID,
    payload: VehicleUpdate,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager", "mechanic")),
    session: AsyncSession = Depends(get_db),
) -> VehicleOut:
    vehicle = await _get_vehicle(session, vehicle_id)
    data = payload.model_dump(exclude_unset=True)
    if "customer_id" in data:
        await _check_customer(session, data["customer_id"])
    if data.get("plate_number"):
        data["plate_number"] = data["plate_number"].strip().upper()
    for key, value in data.items():
        setattr(vehicle, key, value)
    try:
        await session.flush()
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A vehicle with this plate number already exists",
        )
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="vehicle.updated",
        entity="vehicle",
        entity_id=vehicle.id,
        meta={"fields": sorted(data.keys())},
    )
    return VehicleOut.model_validate(vehicle)


@router.delete("/{vehicle_id}", response_model=Ok)
async def delete_vehicle(
    vehicle_id: uuid.UUID,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager")),
    session: AsyncSession = Depends(get_db),
) -> Ok:
    vehicle = await _get_vehicle(session, vehicle_id)
    order_count = await session.scalar(
        select(func.count())
        .select_from(ServiceOrder)
        .where(ServiceOrder.vehicle_id == vehicle_id)
    )
    if order_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This vehicle has service history. Set its status to 'retired' instead.",
        )
    await session.delete(vehicle)
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="vehicle.deleted",
        entity="vehicle",
        entity_id=vehicle_id,
        meta={"plate_number": vehicle.plate_number},
    )
    return Ok(detail="Vehicle deleted")
