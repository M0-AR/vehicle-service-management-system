from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk

CAMPAIGN_CHANNELS = ("sms", "email")
CAMPAIGN_SEGMENTS = ("all", "inactive", "due_service")
CAMPAIGN_STATUSES = ("draft", "sent")
RECIPIENT_STATUSES = ("pending", "sent", "failed", "skipped")

MAX_CAMPAIGN_RECIPIENTS = 500
DEFAULT_LOOKBACK_DAYS = {"inactive": 90, "due_service": 180}


class Campaign(Base):
    """One-shot marketing message to a computed customer segment.

    Delivery reuses the notification outbox, so an unconfigured provider
    records `skipped` recipients instead of failing the send.
    """

    __tablename__ = "campaigns"
    __table_args__ = (
        Index("ix_campaigns_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    channel: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'sms'")
    )
    segment: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'all'")
    )
    lookback_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("90")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'draft'")
    )
    recipients_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    sent_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    skipped_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"
    __table_args__ = (
        Index("ix_campaign_recipients_tenant_campaign", "tenant_id", "campaign_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL")
    )
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'pending'")
    )
    notification_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("notifications.id", ondelete="SET NULL")
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
