from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, uuid_pk


class PushConfig(Base):
    """Deployment-level VAPID keypair (registry table, no RLS).

    Generated once on first use when the VAPID_* envs are unset; the private
    key is encrypted with the master KEK, like other platform-held secrets.
    """

    __tablename__ = "push_config"
    __table_args__ = (CheckConstraint("id = 1", name="ck_push_config_singleton"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    public_key: Mapped[str] = mapped_column(String(255), nullable=False)
    private_key: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class PushSubscription(Base):
    """One browser/device per row, owned by a staff user, tenant-scoped by RLS."""

    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "endpoint", name="uq_push_subscriptions_tenant_endpoint"
        ),
        Index("ix_push_subscriptions_tenant_user", "tenant_id", "user_id"),
        {"comment": "Web Push subscriptions for staff devices"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(Text, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
