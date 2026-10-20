"""Tier C: accounting sync

Additive migration following the 0002–0004 convention: SQLAlchemy models are
the source of truth (`create_all` creates the new tables), then RLS is
enabled/forced and grants are confirmed for the runtime role.

- accounting_connections  one provider connection per tenant (encrypted tokens)
- accounting_sync_runs    period runs with counts/total and failure detail
- accounting_sync_items   invoice → external journal id (idempotency)
- plans.features          + accounting_sync (Pro and Enterprise)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app import models  # noqa: F401

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

NEW_RLS_TABLES = [
    "accounting_connections",
    "accounting_sync_runs",
    "accounting_sync_items",
]
FEATURE_KEYS = ("accounting_sync",)


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
            " accounting_connections, accounting_sync_runs, accounting_sync_items"
            " TO app_user"
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
    bind.execute(sa.text("DROP TABLE IF EXISTS accounting_sync_items"))
    bind.execute(sa.text("DROP TABLE IF EXISTS accounting_sync_runs"))
    bind.execute(sa.text("DROP TABLE IF EXISTS accounting_connections"))
    for plan in ("free", "pro", "enterprise"):
        for key in FEATURE_KEYS:
            bind.execute(
                sa.text(
                    f"UPDATE plans SET features = features - '{key}' WHERE id = :plan"
                ),
                {"plan": plan},
            )
