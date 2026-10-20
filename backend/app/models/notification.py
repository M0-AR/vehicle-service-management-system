from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, uuid_pk

NOTIFICATION_CHANNELS = ("sms", "email")
NOTIFICATION_STATUSES = ("pending", "sent", "failed", "skipped")


class Notification(Base):
    """Outbox: every customer message is recorded before/after delivery.

    Providers are config-gated; when no provider is configured the row is kept
    with status='skipped' so the intent is auditable and retryable.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_tenant_status", "tenant_id", "status"),
        Index("ix_notifications_tenant_entity", "tenant_id", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'sms'")
    )
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    template: Mapped[str] = mapped_column(String(60), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'pending'")
    )
    provider: Mapped[str | None] = mapped_column(String(30))
    error: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    meta: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
