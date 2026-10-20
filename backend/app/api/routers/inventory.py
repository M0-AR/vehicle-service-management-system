from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_feature
from app.db.session import get_db
from app.models.inventory import Part, StockMovement
from app.schemas.common import Ok, Page
from app.schemas.inventory import (
    InventorySummary,
    MovementOut,
    PartIn,
    PartOut,
    PartUpdate,
    StockAdjustIn,
)
from app.services import audit, inventory, numbering

router = APIRouter(prefix="/inventory", tags=["inventory"])

READ_ROLES = ("owner", "admin", "manager", "mechanic", "viewer")
WRITE_ROLES = ("owner", "admin", "manager")


async def _get_part(session: AsyncSession, part_id: uuid.UUID) -> Part:
    part = await session.get(Part, part_id)
    if part is None:
        raise HTTPException(status_code=404, detail="Part not found")
    return part


async def _unique_sku(session: AsyncSession, tenant_id: uuid.UUID, sku: str) -> str:
    exists = await session.scalar(
        select(func.count()).select_from(Part).where(Part.sku == sku)
    )
    if not exists:
        return sku
    raise HTTPException(status_code=409, detail=f"SKU {sku} already exists")


@router.get("/parts", response_model=Page[PartOut])
async def list_parts(
    q: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=60),
    low_stock: bool = False,
    include_inactive: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: AuthContext = Depends(require_feature("inventory")),
    session: AsyncSession = Depends(get_db),
) -> Page[PartOut]:
    base = select(Part)
    if not include_inactive:
        base = base.where(Part.active.is_(True))
    if q:
        pattern = f"%{q.strip()}%"
        base = base.where(
            or_(
                Part.name.ilike(pattern),
                Part.sku.ilike(pattern),
                Part.brand.ilike(pattern),
            )
        )
    if category:
        base = base.where(Part.category == category)
    if low_stock:
        base = base.where(Part.stock_qty <= Part.reorder_level)

    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = await session.scalars(
        base.order_by(Part.name.asc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page[PartOut](
        items=[PartOut.model_validate(p) for p in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.get("/parts/categories", response_model=list[str])
async def list_categories(
    ctx: AuthContext = Depends(require_feature("inventory")),
    session: AsyncSession = Depends(get_db),
) -> list[str]:
    rows = await session.scalars(
        select(Part.category)
        .where(Part.category.is_not(None), Part.active.is_(True))
        .distinct()
        .order_by(Part.category)
    )
    return [c for c in rows if c]


@router.post("/parts", response_model=PartOut, status_code=201)
async def create_part(
    payload: PartIn,
    ctx: AuthContext = Depends(require_feature("inventory")),
    session: AsyncSession = Depends(get_db),
) -> PartOut:
    ctx.require_rank(*WRITE_ROLES)
    sku = (payload.sku or "").strip() or await numbering.next_number(
        session, ctx.tenant_id, "part", "P"
    )
    await _unique_sku(session, ctx.tenant_id, sku)
    part = Part(
        tenant_id=ctx.tenant_id,
        sku=sku,
        name=payload.name.strip(),
        category=payload.category,
        brand=payload.brand,
        supplier=payload.supplier,
        location=payload.location,
        cost=payload.cost,
        price=payload.price,
        stock_qty=payload.stock_qty,
        reorder_level=payload.reorder_level,
        notes=payload.notes,
    )
    session.add(part)
    await session.flush()
    if payload.stock_qty:
        session.add(
            StockMovement(
                tenant_id=ctx.tenant_id,
                part_id=part.id,
                delta=payload.stock_qty,
                reason="received",
                note="Initial stock",
                user_id=ctx.user_id,
            )
        )
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="inventory.part_created",
        entity="part",
        entity_id=part.id,
        meta={"sku": sku, "name": part.name},
    )
    return PartOut.model_validate(part)


@router.patch("/parts/{part_id}", response_model=PartOut)
async def update_part(
    part_id: uuid.UUID,
    payload: PartUpdate,
    ctx: AuthContext = Depends(require_feature("inventory")),
    session: AsyncSession = Depends(get_db),
) -> PartOut:
    ctx.require_rank(*WRITE_ROLES)
    part = await _get_part(session, part_id)
    data = payload.model_dump(exclude_unset=True)
    if "sku" in data and data["sku"]:
        data["sku"] = data["sku"].strip()
        if data["sku"] != part.sku:
            await _unique_sku(session, ctx.tenant_id, data["sku"])
    if "name" in data and data["name"]:
        data["name"] = data["name"].strip()
    for key, value in data.items():
        setattr(part, key, value)
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="inventory.part_updated",
        entity="part",
        entity_id=part.id,
        meta={"fields": sorted(data)},
    )
    return PartOut.model_validate(part)


@router.delete("/parts/{part_id}", response_model=Ok)
async def deactivate_part(
    part_id: uuid.UUID,
    ctx: AuthContext = Depends(require_feature("inventory")),
    session: AsyncSession = Depends(get_db),
) -> Ok:
    ctx.require_rank(*WRITE_ROLES)
    part = await _get_part(session, part_id)
    part.active = False
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="inventory.part_deactivated",
        entity="part",
        entity_id=part.id,
        meta={"sku": part.sku},
    )
    return Ok(detail="Part archived")


@router.post("/parts/{part_id}/adjust", response_model=PartOut)
async def adjust_stock(
    part_id: uuid.UUID,
    payload: StockAdjustIn,
    ctx: AuthContext = Depends(require_feature("inventory")),
    session: AsyncSession = Depends(get_db),
) -> PartOut:
    ctx.require_rank(*WRITE_ROLES)
    part = await _get_part(session, part_id)
    await inventory.record_movement(
        session,
        tenant_id=ctx.tenant_id,
        part=part,
        delta=payload.delta,
        reason=payload.reason,
        note=payload.note,
        order_id=payload.order_id,
        user_id=ctx.user_id,
    )
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="inventory.stock_adjusted",
        entity="part",
        entity_id=part.id,
        meta={"delta": str(payload.delta), "reason": payload.reason},
    )
    return PartOut.model_validate(part)


@router.get("/movements", response_model=Page[MovementOut])
async def list_movements(
    part_id: uuid.UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: AuthContext = Depends(require_feature("inventory")),
    session: AsyncSession = Depends(get_db),
) -> Page[MovementOut]:
    base = select(StockMovement)
    if part_id:
        base = base.where(StockMovement.part_id == part_id)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = await session.scalars(
        base.order_by(StockMovement.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page[MovementOut](
        items=[MovementOut.model_validate(m) for m in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.get("/summary", response_model=InventorySummary)
async def summary(
    ctx: AuthContext = Depends(require_feature("inventory")),
    session: AsyncSession = Depends(get_db),
) -> InventorySummary:
    row = (
        await session.execute(
            select(
                func.count(Part.id),
                func.count(Part.id).filter(Part.stock_qty <= Part.reorder_level),
                func.coalesce(func.sum(Part.stock_qty * Part.cost), 0),
            ).where(Part.active.is_(True))
        )
    ).one()
    return InventorySummary(
        parts=int(row[0] or 0),
        low_stock=int(row[1] or 0),
        stock_value=Decimal(row[2] or 0),
    )
