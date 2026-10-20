"""RLS isolation tests — the security backbone of the platform.

These run as the real runtime role (`app_user`, NOBYPASSRLS) against a real
database. Each asserts one of the guarantees from docs/SECURITY.md.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.core.tenancy import set_rls_context


async def _make_tenant(session, slug: str, name: str) -> uuid.UUID:
    row = await session.execute(
        text(
            "INSERT INTO tenants (name, slug) VALUES (:n, :s)"
            " ON CONFLICT (slug) DO UPDATE SET name = excluded.name RETURNING id"
        ),
        {"n": name, "s": slug},
    )
    return row.scalar_one()


async def test_tenant_isolation_between_contexts(session):
    tenant_a = await _make_tenant(session, f"rls-a-{uuid.uuid4().hex[:6]}", "RLS A")
    tenant_b = await _make_tenant(session, f"rls-b-{uuid.uuid4().hex[:6]}", "RLS B")

    await set_rls_context(session, tenant_a)
    await session.execute(
        text(
            "INSERT INTO customers (tenant_id, name) VALUES (:t, 'Alice of A')"
        ),
        {"t": tenant_a},
    )
    await set_rls_context(session, tenant_b)
    await session.execute(
        text(
            "INSERT INTO customers (tenant_id, name) VALUES (:t, 'Bob of B')"
        ),
        {"t": tenant_b},
    )

    await set_rls_context(session, tenant_a)
    rows = (await session.execute(text("SELECT name FROM customers"))).scalars().all()
    assert "Alice of A" in rows
    assert "Bob of B" not in rows

    await set_rls_context(session, tenant_b)
    rows = (await session.execute(text("SELECT name FROM customers"))).scalars().all()
    assert "Bob of B" in rows
    assert "Alice of A" not in rows


async def test_no_context_sees_nothing(session):
    await set_rls_context(session, None)
    rows = (await session.execute(text("SELECT count(*) FROM customers"))).scalar_one()
    assert rows == 0
    rows = (await session.execute(text("SELECT count(*) FROM vehicles"))).scalar_one()
    assert rows == 0
    rows = (await session.execute(text("SELECT count(*) FROM service_orders"))).scalar_one()
    assert rows == 0


async def test_cross_tenant_insert_is_rejected(session):
    tenant_a = await _make_tenant(session, f"rls-c-{uuid.uuid4().hex[:6]}", "RLS C")
    tenant_b = await _make_tenant(session, f"rls-d-{uuid.uuid4().hex[:6]}", "RLS D")

    await set_rls_context(session, tenant_a)
    with pytest.raises(ProgrammingError):
        # WITH CHECK must reject writing a row owned by another tenant.
        await session.execute(
            text(
                "INSERT INTO customers (tenant_id, name) VALUES (:t, 'Smuggled')"
            ),
            {"t": tenant_b},
        )
    await session.rollback()


async def test_registry_tables_are_visible(session):
    """tenants/plans must be readable without context (routing works pre-auth)."""
    await set_rls_context(session, None)
    plans = (await session.execute(text("SELECT id FROM plans"))).scalars().all()
    assert {"free", "pro", "enterprise"}.issubset(set(plans))
