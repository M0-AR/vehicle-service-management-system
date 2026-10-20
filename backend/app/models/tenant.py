from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk

DEFAULT_BRAND = {
    "primary_color": "#0f766e",
    "accent_color": "#f59e0b",
    "display_name": None,
    "logo_url": None,
    "support_email": None,
}


class Plan(Base):
    """Pricing catalog (registry; no tenant data)."""

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    price_monthly_usd: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, server_default=text("0")
    )
    features: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    limits: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class Tenant(Base):
    """Platform registry table (no RLS: routing data only)."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    plan: Mapped[str] = mapped_column(
        ForeignKey("plans.id"), nullable=False, server_default=text("'free'")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'active'")
    )
    region: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'eu'")
    )
    isolation_tier: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'pool'")
    )
    encryption_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'platform'")
    )
    created_at: Mapped[datetime] = created_at_col()


class TenantDomain(Base):
    """Custom domain -> tenant mapping, served publicly (like DNS)."""

    __tablename__ = "tenant_domains"

    domain: Mapped[str] = mapped_column(String(255), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    verification_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = created_at_col()
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TenantSettings(Base):
    __tablename__ = "tenant_settings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'USD'")
    )
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'UTC'")
    )
    locale: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'en'")
    )
    tax_rate: Mapped[float] = mapped_column(
        Numeric(6, 4), nullable=False, server_default=text("0")
    )
    brand: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    features: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # Public online booking: business hours ({"mon": [["09:00","17:00"]], ...})
    # and the switch that exposes the public booking page.
    business_hours: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    booking_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    review_url: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime] = updated_at_col()


class TenantKey(Base):
    """BYOK: per-tenant DEK, stored only in wrapped form (envelope encryption)."""

    __tablename__ = "tenant_keys"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    dek_wrapped: Mapped[str] = mapped_column(String(255), nullable=False)
    kms_key_ref: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = created_at_col()
