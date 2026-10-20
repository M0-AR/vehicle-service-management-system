"""public share links + estimates

Additive migration. The SQLAlchemy models remain the single source of truth:
`create_all` adds any missing tables (public_links, estimates,
estimate_items), then RLS is enabled/forced for the tenant-scoped ones and
grants are (re)confirmed for the runtime role.

- public_links   registry (no RLS): capability tokens resolved before any
                 tenant context exists.
- estimates /
  estimate_items  tenant-scoped, same policy as service_orders.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app import models  # noqa: F401

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NEW_RLS_TABLES = ["estimates", "estimate_items"]
NEW_TABLES = NEW_RLS_TABLES + ["public_links"]


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
            "GRANT SELECT, INSERT, UPDATE, DELETE ON estimates, estimate_items,"
            " public_links TO app_user"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in NEW_RLS_TABLES:
        bind.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
    for table in ("estimate_items", "estimates", "public_links"):
        bind.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
