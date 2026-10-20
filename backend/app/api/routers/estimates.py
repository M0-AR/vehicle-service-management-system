from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, require_roles
from app.db.session import get_db
from app.models.estimate import Estimate, EstimateItem
from app.models.vehicle import Vehicle
from app.schemas.common import Ok, Page
from app.schemas.estimate import (
    EstimateIn,
    EstimateListItem,
    EstimateOut,
    EstimateUpdate,
)
from app.schemas.public import ShareOut
from app.schemas.service import ItemIn, ItemOut
from app.services import audit, sharing
from app.services.numbering import next_number

router = APIRouter(prefix="/estimates", tags=["estimates"])

EDITABLE_STATUSES = ("draft",)


def _totals(items: list[EstimateItem]) -> dict:
    labor = sum(
        (Decimal(i.quantity) * Decimal(i.unit_price) for i in items if i.kind == "labor"),
        Decimal("0"),
    )
    parts = sum(
        (Decimal(i.quantity) * Decimal(i.unit_price) for i in items if i.kind == "part"),
        Decimal("0"),
    )
    return {"labor": str(labor), "parts": str(parts), "total": str(labor + parts)}


async def _get_estimate(session: AsyncSession, estimate_id: uuid.UUID) -> Estimate:
    estimate = await session.get(Estimate, estimate_id)
    if estimate is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return estimate


async def _estimate_items(
    session: AsyncSession, estimate_id: uuid.UUID
) -> list[EstimateItem]:
    rows = await session.scalars(
        select(EstimateItem)
        .where(EstimateItem.estimate_id == estimate_id)
        .order_by(EstimateItem.created_at)
    )
    return list(rows)


def _serialize(estimate: Estimate, items: list[EstimateItem]) -> EstimateOut:
    out = EstimateOut.model_validate(estimate)
    out.items = [
        ItemOut(
            id=i.id,
            kind=i.kind,
            description=i.description,
            quantity=i.quantity,
            unit_price=i.unit_price,
            total=Decimal(i.quantity) * Decimal(i.unit_price),
        )
        for i in items
    ]
    out.totals = _totals(items)
    return out


def _require_draft(estimate: Estimate) -> None:
    if estimate.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"A {estimate.status} estimate cannot be edited",
        )


@router.get("", response_model=Page[EstimateListItem])
async def list_estimates(
    estimate_status: str | None = Query(default=None, alias="status"),
    vehicle_id: uuid.UUID | None = None,
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> Page[EstimateListItem]:
    where: list[str] = []
    params: dict = {}
    if estimate_status:
        where.append("e.status = :status")
        params["status"] = estimate_status
    if vehicle_id:
        where.append("e.vehicle_id = :vehicle_id")
        params["vehicle_id"] = vehicle_id
    if q:
        where.append("(e.number ILIKE :q OR e.description ILIKE :q OR v.plate_number ILIKE :q)")
        params["q"] = f"%{q.strip()}%"

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    base_sql = f"""
        FROM estimates e
        JOIN vehicles v ON v.id = e.vehicle_id
        LEFT JOIN customers c ON c.id = e.customer_id
        {where_sql}
    """

    total = await session.execute(text(f"SELECT count(*) {base_sql}"), params)
    rows = await session.execute(
        text(
            f"""
            SELECT e.id, e.number, e.status, e.description, e.created_at,
                   v.plate_number, c.name AS customer_name,
                   coalesce((
                       SELECT sum(i.quantity * i.unit_price)
                       FROM estimate_items i WHERE i.estimate_id = e.id
                   ), 0) AS total
            {base_sql}
            ORDER BY e.created_at DESC
            OFFSET :offset LIMIT :limit
            """
        ),
        {**params, "offset": (page - 1) * page_size, "limit": page_size},
    )
    return Page[EstimateListItem](
        items=[
            EstimateListItem(
                id=r["id"],
                number=r["number"],
                status=r["status"],
                description=r["description"],
                vehicle_plate=r["plate_number"],
                customer_name=r["customer_name"],
                total=Decimal(r["total"]),
                created_at=r["created_at"],
            )
            for r in rows.mappings()
        ],
        total=int(total.scalar_one()),
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=EstimateOut, status_code=201)
async def create_estimate(
    payload: EstimateIn,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager", "mechanic")),
    session: AsyncSession = Depends(get_db),
) -> EstimateOut:
    vehicle = await session.get(Vehicle, payload.vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=422, detail="Vehicle not found")

    number = await next_number(session, ctx.tenant_id, "estimate", "ES")
    estimate = Estimate(
        tenant_id=ctx.tenant_id,
        number=number,
        vehicle_id=payload.vehicle_id,
        customer_id=vehicle.customer_id,
        description=payload.description,
        notes=payload.notes,
        created_by=ctx.user_id,
    )
    session.add(estimate)
    await session.flush()

    items: list[EstimateItem] = []
    for item in payload.items:
        record = EstimateItem(
            tenant_id=ctx.tenant_id,
            estimate_id=estimate.id,
            kind=item.kind,
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
        )
        session.add(record)
        items.append(record)
    await session.flush()

    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="estimate.created",
        entity="estimate",
        entity_id=estimate.id,
        meta={"number": estimate.number},
    )
    return _serialize(estimate, items)


@router.get("/{estimate_id}", response_model=EstimateOut)
async def get_estimate(
    estimate_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> EstimateOut:
    estimate = await _get_estimate(session, estimate_id)
    return _serialize(estimate, await _estimate_items(session, estimate_id))


@router.patch("/{estimate_id}", response_model=EstimateOut)
async def update_estimate(
    estimate_id: uuid.UUID,
    payload: EstimateUpdate,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager", "mechanic")),
    session: AsyncSession = Depends(get_db),
) -> EstimateOut:
    estimate = await _get_estimate(session, estimate_id)
    _require_draft(estimate)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(estimate, key, value)
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="estimate.updated",
        entity="estimate",
        entity_id=estimate.id,
        meta={"fields": sorted(data.keys())},
    )
    return _serialize(estimate, await _estimate_items(session, estimate_id))


@router.post("/{estimate_id}/items", response_model=EstimateOut, status_code=201)
async def add_item(
    estimate_id: uuid.UUID,
    payload: ItemIn,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager", "mechanic")),
    session: AsyncSession = Depends(get_db),
) -> EstimateOut:
    estimate = await _get_estimate(session, estimate_id)
    _require_draft(estimate)
    session.add(
        EstimateItem(
            tenant_id=ctx.tenant_id,
            estimate_id=estimate.id,
            kind=payload.kind,
            description=payload.description,
            quantity=payload.quantity,
            unit_price=payload.unit_price,
        )
    )
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="estimate.item_added",
        entity="estimate",
        entity_id=estimate.id,
    )
    return _serialize(estimate, await _estimate_items(session, estimate_id))


@router.delete("/{estimate_id}/items/{item_id}", response_model=EstimateOut)
async def delete_item(
    estimate_id: uuid.UUID,
    item_id: uuid.UUID,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager", "mechanic")),
    session: AsyncSession = Depends(get_db),
) -> EstimateOut:
    estimate = await _get_estimate(session, estimate_id)
    _require_draft(estimate)
    item = await session.get(EstimateItem, item_id)
    if item is None or item.estimate_id != estimate_id:
        raise HTTPException(status_code=404, detail="Item not found")
    await session.delete(item)
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="estimate.item_removed",
        entity="estimate",
        entity_id=estimate.id,
    )
    return _serialize(estimate, await _estimate_items(session, estimate_id))


@router.post("/{estimate_id}/send", response_model=ShareOut)
async def send_estimate(
    estimate_id: uuid.UUID,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager", "mechanic")),
    session: AsyncSession = Depends(get_db),
) -> ShareOut:
    """Mark the estimate as sent and (re)issue the customer approval link."""
    estimate = await _get_estimate(session, estimate_id)
    if estimate.status not in ("draft", "sent"):
        raise HTTPException(
            status_code=409,
            detail=f"A {estimate.status} estimate cannot be sent",
        )
    items = await _estimate_items(session, estimate_id)
    if not items:
        raise HTTPException(
            status_code=409, detail="Add at least one line item before sending"
        )

    if estimate.status == "draft":
        estimate.status = "sent"
        estimate.sent_at = datetime.now(timezone.utc)
    await session.flush()

    link = await sharing.create_link(session, ctx.tenant_id, "estimate", estimate.id)
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="estimate.sent",
        entity="estimate",
        entity_id=estimate.id,
        meta={"number": estimate.number},
    )
    return link


@router.delete("/{estimate_id}/share", response_model=Ok)
async def revoke_estimate_share(
    estimate_id: uuid.UUID,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager", "mechanic")),
    session: AsyncSession = Depends(get_db),
) -> Ok:
    estimate = await _get_estimate(session, estimate_id)
    await sharing.revoke_links(session, "estimate", estimate.id)
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="estimate.link_revoked",
        entity="estimate",
        entity_id=estimate.id,
        meta={"number": estimate.number},
    )
    return Ok(detail="Approval link revoked")


@router.delete("/{estimate_id}", response_model=Ok)
async def delete_estimate(
    estimate_id: uuid.UUID,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager")),
    session: AsyncSession = Depends(get_db),
) -> Ok:
    estimate = await _get_estimate(session, estimate_id)
    if estimate.status != "draft":
        raise HTTPException(
            status_code=409, detail="Only draft estimates can be deleted"
        )
    await sharing.revoke_links(session, "estimate", estimate.id)
    await session.delete(estimate)
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="estimate.deleted",
        entity="estimate",
        entity_id=estimate_id,
        meta={"number": estimate.number},
    )
    return Ok(detail="Estimate deleted")
