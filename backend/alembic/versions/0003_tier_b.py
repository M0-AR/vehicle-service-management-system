"""Tier B: payments, notifications, DVI, online booking, review requests

Additive migration, same convention as 0002: the SQLAlchemy models are the
source of truth (`create_all` creates the new tables), then RLS is
enabled/forced for tenant-scoped tables and grants are confirmed for the
runtime role. Columns added to pre-existing tables need explicit ALTERs.

- notifications   tenant-scoped outbox (SMS/email, status auditable)
- inspections /
  inspection_items tenant-scoped DVI with photo metadata
- booking_requests tenant-scoped public booking submissions
- review_requests tenant-scoped review tokens/results
- invoices        + payment_url / payment_provider / payment_session_id
- tenant_settings + business_hours / booking_enabled / review_url
- plans.features  + online_payments / sms_notifications / dvi /
                    online_booking / review_requests

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app import models  # noqa: F401

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

NEW_RLS_TABLES = [
    "notifications",
    "inspections",
    "inspection_items",
    "booking_requests",
    "review_requests",
]

FEATURE_KEYS = (
    "online_payments",
    "sms_notifications",
    "dvi",
    "online_booking",
    "review_requests",
)


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind)

    # --- columns on existing tables ----------------------------------------
    for table, column, ddl in (
        ("invoices", "payment_url", "VARCHAR(500)"),
        ("invoices", "payment_provider", "VARCHAR(30)"),
        ("invoices", "payment_session_id", "VARCHAR(255)"),
        ("tenant_settings", "business_hours", "JSONB NOT NULL DEFAULT '{}'::jsonb"),
        ("tenant_settings", "booking_enabled", "BOOLEAN NOT NULL DEFAULT false"),
        ("tenant_settings", "review_url", "VARCHAR(500)"),
    ):
        bind.execute(
            sa.text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}")
        )

    # --- RLS ---------------------------------------------------------------
    for table in NEW_RLS_TABLES:
        bind.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        bind.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        bind.execute(
            sa.text(
                f"""
                CREATE POLICY tenant_isolation ON {table}
                    USING (tenant_id = current_tenant())
                    WITH CHECK (tenant_id = current_tenant())
                """
            )
        )

    bind.execute(
        sa.text(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON"
            " notifications, inspections, inspection_items,"
            " booking_requests, review_requests TO app_user"
        )
    )

    # --- plan entitlements --------------------------------------------------
    # Tier B features ship on Pro and Enterprise; Free keeps the Tier A set.
    for plan in ("pro", "enterprise"):
        for key in FEATURE_KEYS:
            bind.execute(
                sa.text(
                    f"""
                    UPDATE plans
                       SET features = features || jsonb_build_object('{key}', true)
                     WHERE id = :plan
                    """
                ),
                {"plan": plan},
            )
    for key in FEATURE_KEYS:
        bind.execute(
            sa.text(
                f"""
                UPDATE plans
                   SET features = features || jsonb_build_object('{key}', false)
                 WHERE id = 'free'
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table in NEW_RLS_TABLES:
        bind.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
    for table in (
        "review_requests",
        "booking_requests",
        "inspection_items",
        "inspections",
        "notifications",
    ):
        bind.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
    for table, column in (
        ("invoices", "payment_url"),
        ("invoices", "payment_provider"),
        ("invoices", "payment_session_id"),
        ("tenant_settings", "business_hours"),
        ("tenant_settings", "booking_enabled"),
        ("tenant_settings", "review_url"),
    ):
        bind.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}"))
    for plan in ("free", "pro", "enterprise"):
        for key in FEATURE_KEYS:
            bind.execute(
                sa.text(
                    f"UPDATE plans SET features = features - '{key}' WHERE id = :plan"
                ),
                {"plan": plan},
            )
