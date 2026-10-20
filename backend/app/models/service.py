from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk

ORDER_STATUSES = (
    "scheduled",
    "in_progress",
    "awaiting_parts",
    "completed",
    "invoiced",
    "cancelled",
)
ORDER_PRIORITIES = ("low", "normal", "high", "urgent")
ITEM_KINDS = ("labor", "part")


class Counter(Base):
    """Atomic per-tenant sequence (contract-safe numbering)."""

    __tablename__ = "counters"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )


class ServiceOrder(Base):
    __tablename__ = "service_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_orders_tenant_number"),
        Index("ix_orders_tenant_status", "tenant_id", "status"),
        Index("ix_orders_tenant_vehicle", "tenant_id", "vehicle_id"),
        Index("ix_orders_tenant_location", "tenant_id", "location_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    number: Mapped[str] = mapped_column(String(30), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL")
    )
    mechanic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'scheduled'")
    )
    priority: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'normal'")
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    odometer: Mapped[int | None] = mapped_column(BigInteger)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class ServiceItem(Base):
    __tablename__ = "service_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    part_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("parts.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'labor'")
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, server_default=text("1")
    )
    unit_price: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = created_at_col()
