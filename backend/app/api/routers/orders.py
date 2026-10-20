from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, require_roles
from app.db.session import get_db
from app.models.customer import Customer
from app.models.inventory import Part
from app.models.location import Location
from app.models.invoice import Invoice
from app.models.service import ServiceItem, ServiceOrder
from app.models.tenant import Tenant
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.common import Ok, Page
from app.schemas.public import ShareOut
from app.schemas.service import (
    ItemIn,
    ItemOut,
    OrderIn,
    OrderListItem,
    OrderOut,
    OrderUpdate,
    StatusChange,
)
from app.services import (
    audit,
    entitlements,
    inventory,
    locations,
    notifications,
    push,
    sharing,
)
from app.services.numbering import next_number

router = APIRouter(prefix="/service-orders", tags=["service-orders"])

TRANSITIONS = {
    "scheduled": {"in_progress", "cancelled"},
    "in_progress": {"awaiting_parts", "completed", "cancelled"},
    "awaiting_parts": {"in_progress", "cancelled"},
    "completed": set(),
    "invoiced": set(),
    "cancelled": set(),
}
OPEN_STATUSES = ("scheduled", "in_progress", "awaiting_parts")


def _totals(items: list[ServiceItem]) -> dict:
    labor = sum(
        (Decimal(i.quantity) * Decimal(i.unit_price) for i in items if i.kind == "labor"),
        Decimal("0"),
    )
    parts = sum(
        (Decimal(i.quantity) * Decimal(i.unit_price) for i in items if i.kind == "part"),
        Decimal("0"),
    )
    return {"labor": str(labor), "parts": str(parts), "total": str(labor + parts)}


async def _get_order(session: AsyncSession, order_id: uuid.UUID) -> ServiceOrder:
    order = await session.get(ServiceOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Service order not found")
    return order


async def _order_items(session: AsyncSession, order_id: uuid.UUID) -> list[ServiceItem]:
    rows = await session.scalars(
        select(ServiceItem).where(ServiceItem.order_id == order_id).order_by(
            ServiceItem.created_at
        )
    )
    return list(rows)


async def _notify_ready(
    session: AsyncSession,
    ctx: AuthContext,
    order: ServiceOrder,
    vehicle: Vehicle | None,
) -> None:
    """Best-effort 'ready for pickup' SMS; never blocks order completion."""
    if not entitlements.has_feature(ctx.plan, "sms_notifications"):
        return
    customer = (
        await session.get(Customer, order.customer_id) if order.customer_id else None
    )
    if customer is None or not customer.phone:
        return
    tenant = await session.get(Tenant, ctx.tenant_id)
    body = notifications.render(
        "order_ready",
        name=customer.name.split(" ")[0],
        plate=vehicle.plate_number if vehicle else "your vehicle",
        shop=tenant.name if tenant else "your workshop",
    )
    await notifications.queue_notification(
        session,
        tenant_id=ctx.tenant_id,
        channel="sms",
        recipient=customer.phone,
        template="order_ready",
        body=body,
        entity_type="service_order",
        entity_id=order.id,
    )


async def _resolve_part(
    session: AsyncSession, ctx: AuthContext, part_id: uuid.UUID
) -> Part:
    entitlements.require_feature(ctx.plan, "inventory")
    part = await session.scalar(
        select(Part)
        .where(Part.id == part_id, Part.active.is_(True))
        .with_for_update()
    )
    if part is None:
        raise HTTPException(status_code=404, detail="Part not found or inactive")
    return part


async def _prepare_item(
    session: AsyncSession, ctx: AuthContext, order_id: uuid.UUID, payload: ItemIn
) -> ServiceItem:
    part = None
    if payload.part_id is not None:
        part = await _resolve_part(session, ctx, payload.part_id)
    record = ServiceItem(
        tenant_id=ctx.tenant_id,
        order_id=order_id,
        kind=payload.kind if part is None else "part",
        part_id=part.id if part else None,
        description=(payload.description or "").strip()
        or (part.name if part else ""),
        quantity=payload.quantity,
        unit_price=payload.unit_price if payload.unit_price else (part.price if part else 0),
    )
    if part is not None:
        await inventory.issue_part(
            session,
            tenant_id=ctx.tenant_id,
            part=part,
            quantity=payload.quantity,
            order_id=order_id,
            user_id=ctx.user_id,
        )
    session.add(record)
    return record


def _serialize_order(order: ServiceOrder, items: list[ServiceItem]) -> OrderOut:
    out = OrderOut.model_validate(order)
    out.items = [
        ItemOut(
            id=i.id,
            kind=i.kind,
            description=i.description,
            quantity=i.quantity,
            unit_price=i.unit_price,
            part_id=i.part_id,
            total=Decimal(i.quantity) * Decimal(i.unit_price),
        )
        for i in items
    ]
    out.totals = _totals(items)
    return out


@router.get("", response_model=Page[OrderListItem])
async def list_orders(
    order_status: str | None = Query(default=None, alias="status"),
    vehicle_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    q: str | None = Query(default=None, max_length=100),
    mine: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> Page[OrderListItem]:
    where: list[str] = []
    params: dict = {}
    if order_status:
        where.append("o.status = :status")
        params["status"] = order_status
    if vehicle_id:
        where.append("o.vehicle_id = :vehicle_id")
        params["vehicle_id"] = vehicle_id
    if customer_id:
        where.append("o.customer_id = :customer_id")
        params["customer_id"] = customer_id
    if location_id:
        where.append("o.location_id = :location_id")
        params["location_id"] = location_id
    if q:
        where.append(
            "(o.number ILIKE :q OR o.description ILIKE :q OR v.plate_number ILIKE :q)"
        )
        params["q"] = f"%{q.strip()}%"
    if mine and ctx.user_id:
        where.append("o.mechanic_id = :me")
        params["me"] = ctx.user_id

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    base_sql = f"""
        FROM service_orders o
        JOIN vehicles v ON v.id = o.vehicle_id
        LEFT JOIN customers c ON c.id = o.customer_id
        LEFT JOIN users m ON m.id = o.mechanic_id
        LEFT JOIN locations l ON l.id = o.location_id
        {where_sql}
    """

    total = await session.execute(
        text(f"SELECT count(*) {base_sql}"), params
    )
    rows = await session.execute(
        text(
            f"""
            SELECT o.id, o.number, o.status, o.priority, o.description, o.created_at,
                   v.plate_number, c.name AS customer_name, m.name AS mechanic_name,
                   l.name AS location_name,
                   coalesce((
                       SELECT sum(i.quantity * i.unit_price)
                       FROM service_items i WHERE i.order_id = o.id
                   ), 0) AS total
            {base_sql}
            ORDER BY o.created_at DESC
            OFFSET :offset LIMIT :limit
            """
        ),
        {**params, "offset": (page - 1) * page_size, "limit": page_size},
    )
    return Page[OrderListItem](
        items=[
            OrderListItem(
                id=r["id"],
                number=r["number"],
                status=r["status"],
                priority=r["priority"],
                description=r["description"],
                vehicle_plate=r["plate_number"],
                customer_name=r["customer_name"],
                mechanic_name=r["mechanic_name"],
                location_name=r["location_name"],
                total=Decimal(r["total"]),
                created_at=r["created_at"],
            )
            for r in rows.mappings()
        ],
        total=int(total.scalar_one()),
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=OrderOut, status_code=201)
async def create_order(
    payload: OrderIn,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager", "mechanic")),
    session: AsyncSession = Depends(get_db),
) -> OrderOut:
    await entitlements.check_limit(session, ctx.plan, "orders_per_month", "service_orders")
    vehicle = await session.get(Vehicle, payload.vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=422, detail="Vehicle not found")
    if payload.mechanic_id:
        mechanic = await session.get(User, payload.mechanic_id)
        if mechanic is None or not mechanic.is_active:
            raise HTTPException(status_code=422, detail="Mechanic not found")
    if payload.location_id:
        location = await session.get(Location, payload.location_id)
        if location is None:
            raise HTTPException(status_code=422, detail="Location not found")
    else:
        location = await locations.ensure_default(session, ctx.tenant_id)

    number = await next_number(session, ctx.tenant_id, "service_order", "SO")
    order = ServiceOrder(
        tenant_id=ctx.tenant_id,
        number=number,
        vehicle_id=payload.vehicle_id,
        customer_id=vehicle.customer_id,
        mechanic_id=payload.mechanic_id,
        location_id=location.id,
        priority=payload.priority,
        description=payload.description,
        odometer=payload.odometer,
        scheduled_at=payload.scheduled_at,
        estimated_cost=payload.estimated_cost,
        notes=payload.notes,
    )
    session.add(order)
    await session.flush()

    items: list[ServiceItem] = []
    for item in payload.items:
        items.append(await _prepare_item(session, ctx, order.id, item))
    await session.flush()

    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="order.created",
        entity="service_order",
        entity_id=order.id,
        meta={"number": order.number},
    )
    if order.mechanic_id:
        await push.notify_user(
            session,
            tenant_id=ctx.tenant_id,
            user_id=order.mechanic_id,
            title="Service order assigned to you",
            body=f"{order.number} · {vehicle.plate_number}",
            url=f"/app/orders/{order.id}",
        )
    return _serialize_order(order, items)


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> OrderOut:
    order = await _get_order(session, order_id)
    return _serialize_order(order, await _order_items(session, order_id))


@router.patch("/{order_id}", response_model=OrderOut)
async def update_order(
    order_id: uuid.UUID,
    payload: OrderUpdate,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager", "mechanic")),
    session: AsyncSession = Depends(get_db),
) -> OrderOut:
    order = await _get_order(session, order_id)
    if order.status in ("invoiced", "cancelled"):
        raise HTTPException(
            status_code=409, detail=f"A {order.status} order cannot be edited"
        )
    data = payload.model_dump(exclude_unset=True)
    reassigned_to: uuid.UUID | None = None
    if "mechanic_id" in data and data["mechanic_id"]:
        mechanic = await session.get(User, data["mechanic_id"])
        if mechanic is None or not mechanic.is_active:
            raise HTTPException(status_code=422, detail="Mechanic not found")
        if data["mechanic_id"] != order.mechanic_id:
            reassigned_to = data["mechanic_id"]
    if "location_id" in data:
        if data["location_id"] is None:
            raise HTTPException(
                status_code=422, detail="Choose a location for this order"
            )
        if await session.get(Location, data["location_id"]) is None:
            raise HTTPException(status_code=422, detail="Location not found")
    for key, value in data.items():
        setattr(order, key, value)
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="order.updated",
        entity="service_order",
        entity_id=order.id,
        meta={"fields": sorted(data.keys())},
    )
    if reassigned_to is not None:
        await push.notify_user(
            session,
            tenant_id=ctx.tenant_id,
            user_id=reassigned_to,
            title="Service order assigned to you",
            body=f"{order.number}",
            url=f"/app/orders/{order.id}",
        )
    return _serialize_order(order, await _order_items(session, order_id))


@router.post("/{order_id}/status", response_model=OrderOut)
async def change_status(
    order_id: uuid.UUID,
    payload: StatusChange,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager", "mechanic")),
    session: AsyncSession = Depends(get_db),
) -> OrderOut:
    order = await _get_order(session, order_id)
    allowed = TRANSITIONS.get(order.status, set())
    if payload.status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot move an order from '{order.status}' to '{payload.status}'",
        )
    if payload.status == "completed" and not await _order_items(session, order_id):
        raise HTTPException(
            status_code=409,
            detail="Add at least one service item before completing the order",
        )

    if payload.status == "cancelled":
        for item in await _order_items(session, order_id):
            if item.part_id is None:
                continue
            part = await session.get(Part, item.part_id)
            if part is not None:
                await inventory.return_part(
                    session,
                    tenant_id=ctx.tenant_id,
                    part=part,
                    quantity=item.quantity,
                    order_id=order.id,
                    user_id=ctx.user_id,
                    note="Order cancelled",
                )

    order.status = payload.status
    now = datetime.now(timezone.utc)
    if payload.status == "in_progress" and order.started_at is None:
        order.started_at = now
    if payload.status == "completed":
        order.completed_at = now

    # Mirror the original console design: vehicle status follows the active
    # work order (in_service while being worked on, active again afterwards).
    vehicle = await session.get(Vehicle, order.vehicle_id)
    if vehicle is not None:
        if payload.status == "in_progress":
            vehicle.status = "in_service"
        elif payload.status in ("completed", "cancelled"):
            vehicle.status = "active"

    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="order.status_changed",
        entity="service_order",
        entity_id=order.id,
        meta={"status": payload.status},
    )

    if payload.status == "completed":
        await _notify_ready(session, ctx, order, vehicle)

    return _serialize_order(order, await _order_items(session, order_id))


@router.post("/{order_id}/items", response_model=OrderOut, status_code=201)
async def add_item(
    order_id: uuid.UUID,
    payload: ItemIn,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager", "mechanic")),
    session: AsyncSession = Depends(get_db),
) -> OrderOut:
    order = await _get_order(session, order_id)
    if order.status in ("invoiced", "cancelled"):
        raise HTTPException(
            status_code=409, detail=f"A {order.status} order cannot be edited"
        )
    await _prepare_item(session, ctx, order.id, payload)
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="order.item_added",
        entity="service_order",
        entity_id=order.id,
    )
    return _serialize_order(order, await _order_items(session, order_id))


@router.delete("/{order_id}/items/{item_id}", response_model=OrderOut)
async def delete_item(
    order_id: uuid.UUID,
    item_id: uuid.UUID,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager", "mechanic")),
    session: AsyncSession = Depends(get_db),
) -> OrderOut:
    order = await _get_order(session, order_id)
    if order.status in ("invoiced", "cancelled"):
        raise HTTPException(
            status_code=409, detail=f"A {order.status} order cannot be edited"
        )
    item = await session.get(ServiceItem, item_id)
    if item is None or item.order_id != order_id:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.part_id is not None:
        part = await session.get(Part, item.part_id)
        if part is not None:
            await inventory.return_part(
                session,
                tenant_id=ctx.tenant_id,
                part=part,
                quantity=item.quantity,
                order_id=order.id,
                user_id=ctx.user_id,
                note="Line item removed",
            )
    await session.delete(item)
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="order.item_removed",
        entity="service_order",
        entity_id=order.id,
    )
    return _serialize_order(order, await _order_items(session, order_id))


@router.post("/{order_id}/share", response_model=ShareOut)
async def share_order(
    order_id: uuid.UUID,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager", "mechanic")),
    session: AsyncSession = Depends(get_db),
) -> ShareOut:
    """(Re)generate the customer-facing status link for this order."""
    order = await _get_order(session, order_id)
    if order.status == "cancelled":
        raise HTTPException(
            status_code=409, detail="A cancelled order cannot be shared"
        )
    link = await sharing.create_link(session, ctx.tenant_id, "order", order.id)
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="order.link_shared",
        entity="service_order",
        entity_id=order.id,
        meta={"number": order.number},
    )
    return link


@router.delete("/{order_id}/share", response_model=Ok)
async def revoke_order_share(
    order_id: uuid.UUID,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager", "mechanic")),
    session: AsyncSession = Depends(get_db),
) -> Ok:
    order = await _get_order(session, order_id)
    await sharing.revoke_links(session, "order", order.id)
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="order.link_revoked",
        entity="service_order",
        entity_id=order.id,
        meta={"number": order.number},
    )
    return Ok(detail="Status link revoked")


@router.delete("/{order_id}", response_model=Ok)
async def delete_order(
    order_id: uuid.UUID,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager")),
    session: AsyncSession = Depends(get_db),
) -> Ok:
    order = await _get_order(session, order_id)
    if order.status not in ("scheduled", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail="Only scheduled or cancelled orders can be deleted",
        )
    invoice_count = await session.scalar(
        select(func.count()).select_from(Invoice).where(Invoice.order_id == order_id)
    )
    if invoice_count:
        raise HTTPException(
            status_code=409, detail="This order has invoices and cannot be deleted"
        )
    await session.delete(order)
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="order.deleted",
        entity="service_order",
        entity_id=order_id,
        meta={"number": order.number},
    )
    return Ok(detail="Order deleted")
