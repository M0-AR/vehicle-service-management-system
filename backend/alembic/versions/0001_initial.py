"""initial schema + row-level security

Baseline migration:
1. Creates every table from the SQLAlchemy metadata (single source of truth).
2. Installs `current_tenant()` and ENABLE/FORCE RLS + policies on all
   tenant-scoped tables (USING + WITH CHECK — writes of foreign tenant_id fail).
3. Grants DML to the runtime role `app_user` (created by infra init script);
   audit_logs is append-only (no UPDATE/DELETE).
4. Seeds the plan catalog.

Registry tables (no tenant_id: tenants, tenant_domains, plans,
billing_accounts, billing_events) intentionally have NO RLS — they are
routing/billing-reference data accessed before a tenant context exists.

Revision ID: 0001
Revises:
Create Date: 2026-10-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app import models  # noqa: F401

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

RLS_TABLES = [
    "users",
    "refresh_tokens",
    "api_keys",
    "customers",
    "vehicles",
    "service_orders",
    "service_items",
    "invoices",
    "audit_logs",
    "tenant_settings",
    "tenant_keys",
    "counters",
]

APP_TABLES_READ_WRITE = [
    "users",
    "refresh_tokens",
    "api_keys",
    "customers",
    "vehicles",
    "service_orders",
    "service_items",
    "invoices",
    "tenant_settings",
    "tenant_keys",
    "counters",
]


def upgrade() -> None:
    bind = op.get_bind()

    Base.metadata.create_all(bind)

    bind.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION current_tenant() RETURNS uuid
            LANGUAGE sql STABLE AS
            $$ SELECT NULLIF(current_setting('app.current_tenant', true), '')::uuid $$
            """
        )
    )
    bind.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION current_tenant_user() RETURNS uuid
            LANGUAGE sql STABLE AS
            $$ SELECT NULLIF(current_setting('app.current_user', true), '')::uuid $$
            """
        )
    )

    for table in RLS_TABLES:
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

    # --- runtime role grants -------------------------------------------------
    bind.execute(sa.text("GRANT USAGE ON SCHEMA public TO app_user"))
    bind.execute(
        sa.text(
            "GRANT SELECT ON plans, tenants, tenant_domains, billing_accounts,"
            " billing_events TO app_user"
        )
    )
    bind.execute(
        sa.text(
            "GRANT INSERT ON tenants, tenant_domains, billing_accounts,"
            " billing_events TO app_user"
        )
    )
    bind.execute(
        sa.text(
            "GRANT UPDATE ON tenants, tenant_domains, billing_accounts,"
            " billing_events TO app_user"
        )
    )
    for table in APP_TABLES_READ_WRITE:
        bind.execute(
            sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO app_user")
        )
    # audit trail is append-only for the app role
    bind.execute(sa.text("GRANT SELECT, INSERT ON audit_logs TO app_user"))
    bind.execute(sa.text("REVOKE UPDATE, DELETE ON audit_logs FROM app_user"))

    # future objects created by the owner (postgres) stay usable
    bind.execute(
        sa.text(
            "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public"
            " GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user"
        )
    )

    # --- plan catalog --------------------------------------------------------
    bind.execute(
        sa.text(
            """
            INSERT INTO plans (id, name, price_monthly_usd, features, limits)
            VALUES
              ('free', 'Free', 0, :free_features, :free_limits),
              ('pro', 'Pro', 29, :pro_features, :pro_limits),
              ('enterprise', 'Enterprise', 99, :ent_features, :ent_limits)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "free_features": '{"white_label": false, "custom_domain": false, "api_access": false, "audit_log": false, "byok": false}',
            "free_limits": '{"users": 3, "vehicles": 50, "orders_per_month": 100}',
            "pro_features": '{"white_label": true, "custom_domain": true, "api_access": true, "audit_log": true, "byok": false}',
            "pro_limits": '{"users": 20, "vehicles": 1000, "orders_per_month": 5000}',
            "ent_features": '{"white_label": true, "custom_domain": true, "api_access": true, "audit_log": true, "byok": true}',
            "ent_limits": '{"users": -1, "vehicles": -1, "orders_per_month": -1}',
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in RLS_TABLES:
        bind.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
    bind.execute(sa.text("DROP FUNCTION IF EXISTS current_tenant()"))
    bind.execute(sa.text("DROP FUNCTION IF EXISTS current_tenant_user()"))
    Base.metadata.drop_all(bind)
