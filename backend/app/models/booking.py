from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, uuid_pk

BOOKING_STATUSES = ("pending", "confirmed", "declined", "converted")


class BookingRequest(Base):
    """Public online booking request, converted into a scheduled order."""

    __tablename__ = "booking_requests"
    __table_args__ = (
        Index("ix_booking_requests_tenant_status", "tenant_id", "status"),
        Index("ix_booking_requests_tenant_time", "tenant_id", "preferred_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(40), nullable=False)
    plate_number: Mapped[str] = mapped_column(String(20), nullable=False)
    make: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(60))
    year: Mapped[int | None] = mapped_column(Integer)
    service_description: Mapped[str] = mapped_column(Text, nullable=False)
    preferred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'converted'")
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
