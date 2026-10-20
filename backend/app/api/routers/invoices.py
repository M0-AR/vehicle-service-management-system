from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, require_feature, require_roles
from app.db.session import get_db
from app.models.invoice import Invoice
from app.models.service import ServiceItem, ServiceOrder
from app.models.tenant import TenantSettings
from app.models.vehicle import Vehicle
from app.schemas.common import Ok, Page
from app.schemas.invoice import (
    InvoiceFromOrder,
    InvoiceListItem,
    InvoiceOut,
    InvoiceUpdate,
    PaymentLinkOut,
)
from app.services import audit
from app.services.billing.registry import get_provider
from app.services.numbering import next_number

router = APIRouter(prefix="/invoices", tags=["invoices"])

SETTABLE_STATUSES = ("draft", "sent", "paid", "overdue", "void")


async def _get_invoice(session: AsyncSession, invoice_id: uuid.UUID) -> Invoice:
    invoice = await session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.get("", response_model=Page[InvoiceListItem])
async def list_invoices(
    invoice_status: str | None = Query(default=None, alias="status"),
    customer_id: uuid.UUID | None = None,
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> Page[InvoiceListItem]:
    where: list[str] = []
    params: dict = {}
    if invoice_status:
        where.append("i.status = :status")
        params["status"] = invoice_status
    if customer_id:
        where.append("i.customer_id = :customer_id")
        params["customer_id"] = customer_id
    if q:
        where.append("i.number ILIKE :q")
        params["q"] = f"%{q.strip()}%"
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    base_sql = f"""
        FROM invoices i
        LEFT JOIN customers c ON c.id = i.customer_id
        {where_sql}
    """
    total = await session.execute(text(f"SELECT count(*) {base_sql}"), params)
    rows = await session.execute(
        text(
            f"""
            SELECT i.id, i.number, i.status, i.total, i.currency,
                   i.issued_at, i.due_at, c.name AS customer_name
            {base_sql}
            ORDER BY i.created_at DESC
            OFFSET :offset LIMIT :limit
            """
        ),
        {**params, "offset": (page - 1) * page_size, "limit": page_size},
    )
    return Page[InvoiceListItem](
        items=[
            InvoiceListItem(
                id=r["id"],
                number=r["number"],
                status=r["status"],
                customer_name=r["customer_name"],
                total=Decimal(r["total"]),
                currency=r["currency"],
                issued_at=r["issued_at"],
                due_at=r["due_at"],
            )
            for r in rows.mappings()
        ],
        total=int(total.scalar_one()),
        page=page,
        page_size=page_size,
    )


@router.post("/from-order", response_model=InvoiceOut, status_code=201)
async def create_from_order(
    payload: InvoiceFromOrder,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager")),
    session: AsyncSession = Depends(get_db),
) -> InvoiceOut:
    order = await session.get(ServiceOrder, payload.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Service order not found")
    if order.status != "completed":
        raise HTTPException(
            status_code=409,
            detail="Only completed orders can be invoiced",
        )
    existing = await session.scalar(
        select(func.count()).select_from(Invoice).where(Invoice.order_id == order.id)
    )
    if existing:
        raise HTTPException(
            status_code=409, detail="This order has already been invoiced"
        )

    items = list(
        await session.scalars(
            select(ServiceItem).where(ServiceItem.order_id == order.id)
        )
    )
    if not items:
        raise HTTPException(status_code=409, detail="The order has no service items")

    subtotal = sum(
        (Decimal(i.quantity) * Decimal(i.unit_price) for i in items), Decimal("0")
    )
    settings_row = await session.get(TenantSettings, ctx.tenant_id)
    tax_rate = Decimal(settings_row.tax_rate) if settings_row else Decimal("0")
    tax_amount = (subtotal * tax_rate).quantize(Decimal("0.01"))
    now = datetime.now(timezone.utc)

    vehicle = await session.get(Vehicle, order.vehicle_id)
    number = await next_number(session, ctx.tenant_id, "invoice", "INV")
    invoice = Invoice(
        tenant_id=ctx.tenant_id,
        number=number,
        order_id=order.id,
        customer_id=order.customer_id,
        status="draft",
        issued_at=None,
        due_at=now + timedelta(days=payload.due_days),
        subtotal=subtotal,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        total=subtotal + tax_amount,
        currency=settings_row.currency if settings_row else "USD",
        lines=[
            {
                "kind": i.kind,
                "description": i.description,
                "quantity": str(i.quantity),
                "unit_price": str(i.unit_price),
                "total": str(Decimal(i.quantity) * Decimal(i.unit_price)),
            }
            for i in items
        ],
        meta={
            "order_number": order.number,
            "order_description": order.description,
            "vehicle": {
                "plate_number": vehicle.plate_number if vehicle else None,
                "make": vehicle.make if vehicle else None,
                "model": vehicle.model if vehicle else None,
                "year": vehicle.year if vehicle else None,
            },
            "tax_rate": str(tax_rate),
        },
    )
    session.add(invoice)

    order.status = "invoiced"
    await session.flush()

    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="invoice.created",
        entity="invoice",
        entity_id=invoice.id,
        meta={"number": invoice.number, "order": order.number},
    )
    return InvoiceOut.model_validate(invoice)


@router.get("/{invoice_id}", response_model=InvoiceOut)
async def get_invoice(
    invoice_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> InvoiceOut:
    return InvoiceOut.model_validate(await _get_invoice(session, invoice_id))


@router.post("/{invoice_id}/status", response_model=InvoiceOut)
async def set_status(
    invoice_id: uuid.UUID,
    payload: InvoiceUpdate,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager")),
    session: AsyncSession = Depends(get_db),
) -> InvoiceOut:
    invoice = await _get_invoice(session, invoice_id)
    if payload.status is None:
        raise HTTPException(status_code=422, detail="status is required")
    if payload.status not in SETTABLE_STATUSES:
        raise HTTPException(
            status_code=422, detail=f"status must be one of {SETTABLE_STATUSES}"
        )

    invoice.status = payload.status
    now = datetime.now(timezone.utc)
    if payload.status == "sent" and invoice.issued_at is None:
        invoice.issued_at = now
    if payload.status == "paid":
        invoice.paid_at = now
        if invoice.issued_at is None:
            invoice.issued_at = now
    if payload.due_at is not None:
        invoice.due_at = payload.due_at
    await session.flush()

    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="invoice.status_changed",
        entity="invoice",
        entity_id=invoice.id,
        meta={"status": payload.status},
    )
    return InvoiceOut.model_validate(invoice)


@router.post("/{invoice_id}/payment-link", response_model=PaymentLinkOut)
async def create_payment_link(
    invoice_id: uuid.UUID,
    payload: dict | None = None,
    ctx: AuthContext = Depends(require_feature("online_payments")),
    session: AsyncSession = Depends(get_db),
) -> PaymentLinkOut:
    """Create (or reuse) a Stripe Checkout link for this invoice."""
    ctx.require_rank("owner", "admin", "manager")
    invoice = await _get_invoice(session, invoice_id)
    if invoice.status == "paid":
        raise HTTPException(status_code=409, detail="This invoice is already paid")
    if invoice.status == "void":
        raise HTTPException(status_code=409, detail="This invoice was voided")
    if Decimal(invoice.total) <= 0:
        raise HTTPException(status_code=409, detail="This invoice has no amount due")

    provider = get_provider()
    if provider.name != "stripe" or not hasattr(provider, "create_payment_checkout"):
        raise HTTPException(
            status_code=409,
            detail=(
                "Online invoice payments need Stripe. Set BILLING_PROVIDER=stripe"
                " and STRIPE_SECRET_KEY."
            ),
        )

    data = payload or {}
    url, message = await provider.create_payment_checkout(
        tenant_id=ctx.tenant_id,
        invoice_id=invoice.id,
        invoice_number=invoice.number,
        amount_cents=int(Decimal(invoice.total) * 100),
        currency=invoice.currency,
        success_url=data.get("success_url"),
        cancel_url=data.get("cancel_url"),
    )
    if url is None:
        raise HTTPException(status_code=409, detail=message)

    invoice.payment_url = url
    invoice.payment_provider = "stripe"
    if invoice.status == "draft":
        invoice.status = "sent"
    if invoice.issued_at is None:
        invoice.issued_at = datetime.now(timezone.utc)
    await session.flush()

    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="invoice.payment_link_created",
        entity="invoice",
        entity_id=invoice.id,
        meta={"number": invoice.number, "provider": "stripe"},
    )
    return PaymentLinkOut(url=url, message=message)


@router.delete("/{invoice_id}", response_model=Ok)
async def delete_invoice(
    invoice_id: uuid.UUID,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager")),
    session: AsyncSession = Depends(get_db),
) -> Ok:
    invoice = await _get_invoice(session, invoice_id)
    if invoice.status not in ("draft", "void"):
        raise HTTPException(
            status_code=409, detail="Only draft or void invoices can be deleted"
        )
    order = (
        await session.get(ServiceOrder, invoice.order_id) if invoice.order_id else None
    )
    if order is not None and order.status == "invoiced":
        order.status = "completed"
    await session.delete(invoice)
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="invoice.deleted",
        entity="invoice",
        entity_id=invoice_id,
        meta={"number": invoice.number},
    )
    return Ok(detail="Invoice deleted")
