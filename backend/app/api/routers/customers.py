from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, require_roles
from app.db.session import get_db
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.service import ServiceOrder
from app.models.vehicle import Vehicle
from app.schemas.common import Ok, Page
from app.schemas.customer import CustomerIn, CustomerOut, CustomerSummary, CustomerUpdate
from app.services import audit

router = APIRouter(prefix="/customers", tags=["customers"])

OPEN_STATUSES = ("scheduled", "in_progress", "awaiting_parts")


async def _get_customer(session: AsyncSession, customer_id: uuid.UUID) -> Customer:
    customer = await session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.get("", response_model=Page[CustomerSummary])
async def list_customers(
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> Page[CustomerSummary]:
    base = select(Customer)
    if q:
        pattern = f"%{q.strip()}%"
        base = base.where(
            or_(
                Customer.name.ilike(pattern),
                Customer.email.ilike(pattern),
                Customer.phone.ilike(pattern),
            )
        )

    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = await session.scalars(
        base.order_by(Customer.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    customers = list(rows)
    ids = [c.id for c in customers]

    vehicle_counts: dict[uuid.UUID, int] = {}
    open_counts: dict[uuid.UUID, int] = {}
    billed: dict[uuid.UUID, Decimal] = {}
    if ids:
        vc = await session.execute(
            select(Vehicle.customer_id, func.count())
            .where(Vehicle.customer_id.in_(ids))
            .group_by(Vehicle.customer_id)
        )
        vehicle_counts = {r[0]: int(r[1]) for r in vc}
        oc = await session.execute(
            select(ServiceOrder.customer_id, func.count())
            .where(ServiceOrder.customer_id.in_(ids))
            .where(ServiceOrder.status.in_(OPEN_STATUSES))
            .group_by(ServiceOrder.customer_id)
        )
        open_counts = {r[0]: int(r[1]) for r in oc}
        bt = await session.execute(
            select(Invoice.customer_id, func.coalesce(func.sum(Invoice.total), 0))
            .where(Invoice.customer_id.in_(ids))
            .where(Invoice.status.in_(("sent", "paid", "overdue")))
            .group_by(Invoice.customer_id)
        )
        billed = {r[0]: Decimal(r[1]) for r in bt}

    return Page[CustomerSummary](
        items=[
            CustomerSummary(
                id=c.id,
                name=c.name,
                phone=c.phone,
                vehicle_count=vehicle_counts.get(c.id, 0),
                open_orders=open_counts.get(c.id, 0),
                total_billed=billed.get(c.id, Decimal("0")),
            )
            for c in customers
        ],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=CustomerOut, status_code=201)
async def create_customer(
    payload: CustomerIn,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager", "mechanic")),
    session: AsyncSession = Depends(get_db),
) -> CustomerOut:
    customer = Customer(**payload.model_dump(), tenant_id=ctx.tenant_id)
    session.add(customer)
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="customer.created",
        entity="customer",
        entity_id=customer.id,
        meta={"name": customer.name},
    )
    return CustomerOut.model_validate(customer)


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> CustomerOut:
    return CustomerOut.model_validate(await _get_customer(session, customer_id))


@router.patch("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager", "mechanic")),
    session: AsyncSession = Depends(get_db),
) -> CustomerOut:
    customer = await _get_customer(session, customer_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(customer, key, value)
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="customer.updated",
        entity="customer",
        entity_id=customer.id,
        meta={"fields": sorted(data.keys())},
    )
    return CustomerOut.model_validate(customer)


@router.delete("/{customer_id}", response_model=Ok)
async def delete_customer(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager")),
    session: AsyncSession = Depends(get_db),
) -> Ok:
    customer = await _get_customer(session, customer_id)
    vehicle_count = await session.scalar(
        select(func.count()).select_from(Vehicle).where(Vehicle.customer_id == customer_id)
    )
    if vehicle_count:
        raise HTTPException(
            status_code=409,
            detail="This customer still has vehicles. Reassign or remove them first.",
        )
    await session.delete(customer)
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="customer.deleted",
        entity="customer",
        entity_id=customer_id,
        meta={"name": customer.name},
    )
    return Ok(detail="Customer deleted")
