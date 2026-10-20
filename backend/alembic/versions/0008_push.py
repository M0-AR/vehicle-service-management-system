"""Tier C: staff Web Push (PWA)

Additive migration following the 0002–0007 convention: SQLAlchemy models are
the source of truth (`create_all` creates the new tables), then RLS is
enabled/forced and grants are confirmed for the runtime role.

- push_config         deployment-level VAPID keypair (registry table, no RLS);
                      private key stored encrypted with the master KEK
- push_subscriptions  one row per staff browser/device (RLS tenant-scoped)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app import models  # noqa: F401

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

NEW_RLS_TABLES = ["push_subscriptions"]


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
        sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON push_subscriptions TO app_user")
    )
    bind.execute(
        sa.text("GRANT SELECT, INSERT, UPDATE ON push_config TO app_user")
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in NEW_RLS_TABLES:
        bind.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
    bind.execute(sa.text("DROP TABLE IF EXISTS push_subscriptions"))
    bind.execute(sa.text("DROP TABLE IF EXISTS push_config"))
