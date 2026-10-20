"""Tier C: parts supplier catalog

Additive migration following the 0002–0008 convention: SQLAlchemy models are
the source of truth (`create_all` creates the new tables), then RLS is
enabled/forced and grants are confirmed for the runtime role.

- supplier_connections   per-tenant distributor connections (RLS)
- supplier_catalog_items uploaded CSV price lists (RLS, cascade on delete)
- plans.features         + suppliers (Pro and Enterprise)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app import models  # noqa: F401

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

NEW_RLS_TABLES = ["supplier_connections", "supplier_catalog_items"]
FEATURE_KEYS = ("suppliers",)


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind)

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
            " supplier_connections, supplier_catalog_items TO app_user"
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
    bind.execute(sa.text("DROP TABLE IF EXISTS supplier_catalog_items"))
    bind.execute(sa.text("DROP TABLE IF EXISTS supplier_connections"))
    for plan in ("free", "pro", "enterprise"):
        for key in FEATURE_KEYS:
            bind.execute(
                sa.text(
                    f"UPDATE plans SET features = features - '{key}' WHERE id = :plan"
                ),
                {"plan": plan},
            )
