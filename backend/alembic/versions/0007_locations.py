"""Tier C: multi-location

Additive migration following the 0002–0006 convention: SQLAlchemy models are
the source of truth (`create_all` creates the new table), then RLS is
enabled/forced and grants are confirmed for the runtime role.

- locations                 per-tenant shop branches (name, address, default flag)
- service_orders.location_id nullable branch assignment, allowed to be nulled on delete
- seeds "Main location" for every existing tenant and backfills existing orders

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app import models  # noqa: F401

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

NEW_RLS_TABLES = ["locations"]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind)

    bind.execute(
        sa.text(
            "ALTER TABLE service_orders"
            " ADD COLUMN IF NOT EXISTS location_id UUID"
            " REFERENCES locations(id) ON DELETE SET NULL"
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_orders_tenant_location"
            " ON service_orders (tenant_id, location_id)"
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
        sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON locations TO app_user")
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO locations (id, tenant_id, name, is_default)
            SELECT gen_random_uuid(), t.id, 'Main location', true
              FROM tenants t
             WHERE NOT EXISTS (
                   SELECT 1 FROM locations l WHERE l.tenant_id = t.id
             )
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE service_orders o
               SET location_id = l.id
              FROM locations l
             WHERE l.tenant_id = o.tenant_id
               AND l.is_default
               AND o.location_id IS NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DROP INDEX IF EXISTS ix_orders_tenant_location")
    )
    bind.execute(
        sa.text("ALTER TABLE service_orders DROP COLUMN IF EXISTS location_id")
    )
    for table in NEW_RLS_TABLES:
        bind.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
    bind.execute(sa.text("DROP TABLE IF EXISTS locations"))
