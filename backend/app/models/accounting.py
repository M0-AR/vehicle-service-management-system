from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk

ACCOUNTING_PROVIDERS = ("stub", "quickbooks", "xero")
CONNECTION_STATUSES = ("connected", "disconnected", "error")
RUN_STATUSES = ("pending", "succeeded", "failed", "partial")
ITEM_STATUSES = ("posted", "failed")

DEFAULT_ACCOUNTS = {"payment": "1000", "income": "4000", "tax": "2200"}


class AccountingConnection(Base):
    __tablename__ = "accounting_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_accounting_connections_tenant"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'connected'")
    )
    external_tenant_id: Mapped[str | None] = mapped_column(String(120))
    access_token_enc: Mapped[str | None] = mapped_column(Text)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class AccountingSyncRun(Base):
    __tablename__ = "accounting_sync_runs"
    __table_args__ = (
        Index("ix_accounting_runs_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounting_connections.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    invoices_count: Mapped[int] = mapped_column(
        nullable=False, server_default=text("0")
    )
    total_amount: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'USD'")
    )
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountingSyncItem(Base):
    __tablename__ = "accounting_sync_items"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "invoice_id",
            name="uq_accounting_items_connection_invoice",
        ),
        Index("ix_accounting_items_run", "run_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounting_sync_runs.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounting_connections.id", ondelete="SET NULL")
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invoices.id", ondelete="SET NULL")
    )
    invoice_number: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    external_id: Mapped[str | None] = mapped_column(String(120))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
