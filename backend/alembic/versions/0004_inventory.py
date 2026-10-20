"""Tier C: inventory and parts

Additive migration following the 0002/0003 convention: SQLAlchemy models are
the source of truth (`create_all` creates the new tables), then RLS is
enabled/forced and grants are confirmed for the runtime role. The FK column
added to the pre-existing `service_items` table needs an explicit ALTER.

- parts            tenant-scoped catalogue (sku, pricing, stock, reorder level)
- stock_movements  tenant-scoped ledger (received/issued/returned/adjustment)
- service_items    + part_id (nullable; line item draws from stock)
- plans.features   + inventory (Pro and Enterprise)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app import models  # noqa: F401

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

NEW_RLS_TABLES = ["parts", "stock_movements"]
FEATURE_KEYS = ("inventory",)


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind)

    bind.execute(
        sa.text(
            "ALTER TABLE service_items ADD COLUMN IF NOT EXISTS part_id UUID"
            " REFERENCES parts(id) ON DELETE SET NULL"
        )
    )

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
            " parts, stock_movements TO app_user"
        )
    )

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
    bind.execute(sa.text("ALTER TABLE service_items DROP COLUMN IF EXISTS part_id"))
    bind.execute(sa.text("DROP TABLE IF EXISTS stock_movements"))
    bind.execute(sa.text("DROP TABLE IF EXISTS parts"))
    for plan in ("free", "pro", "enterprise"):
        for key in FEATURE_KEYS:
            bind.execute(
                sa.text(
                    f"UPDATE plans SET features = features - '{key}' WHERE id = :plan"
                ),
                {"plan": plan},
            )
