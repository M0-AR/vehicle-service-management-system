from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk

SUPPLIER_PROVIDERS = ("stub", "csv")


class SupplierConnection(Base):
    __tablename__ = "supplier_connections"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "name", name="uq_supplier_connections_tenant_name"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    portal_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class SupplierCatalogItem(Base):
    __tablename__ = "supplier_catalog_items"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "sku", name="uq_supplier_catalog_connection_sku"
        ),
        Index("ix_supplier_catalog_tenant_sku", "tenant_id", "sku"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("supplier_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    cost: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    price: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    stock_qty: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    updated_at: Mapped[datetime] = updated_at_col()
