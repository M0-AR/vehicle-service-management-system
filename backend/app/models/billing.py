from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, updated_at_col

# Registry tables (intentionally RLS-free): webhooks are unauthenticated and
# must look up tenants by provider IDs before any tenant context exists. They
# hold billing references/status only — no customer PII.


class BillingAccount(Base):
    __tablename__ = "billing_accounts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    external_customer_id: Mapped[str | None] = mapped_column(String(120), index=True)
    subscription_id: Mapped[str | None] = mapped_column(String(120), index=True)
    plan: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'free'")
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'active'")
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'USD'")
    )
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class BillingEvent(Base):
    """Webhook dedupe ledger (provider event ids are unique)."""

    __tablename__ = "billing_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    event_id: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
