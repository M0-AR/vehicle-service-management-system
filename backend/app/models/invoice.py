from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk

INVOICE_STATUSES = ("draft", "sent", "paid", "overdue", "void")


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_invoices_tenant_number"),
        Index("ix_invoices_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    number: Mapped[str] = mapped_column(String(30), nullable=False)
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_orders.id", ondelete="SET NULL")
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'draft'")
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subtotal: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    tax_rate: Mapped[float] = mapped_column(
        Numeric(6, 4), nullable=False, server_default=text("0")
    )
    tax_amount: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    total: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'USD'")
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Online payment (Stripe Checkout). `payment_url` is reusable until paid;
    # `payment_provider` records who collected it ("stripe" / "manual").
    payment_url: Mapped[str | None] = mapped_column(String(500))
    payment_provider: Mapped[str | None] = mapped_column(String(30))
    payment_session_id: Mapped[str | None] = mapped_column(String(255))
    # Snapshot of line items and customer/vehicle details at issue time —
    # invoices are immutable documents, not live views.
    lines: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    meta: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
