"""Plan entitlements: what a tenant may DO (server-enforced).

Two distinct concepts (verified pattern — docs/ARCHITECTURE.md):
- Entitlements = plan/paid capabilities. Enforced here, never in the UI only.
- Release flags  = code-level feature rollout. Not in this module.

Effective features = plan features merged with tenant_settings.features
(sales can grant per-tenant overrides without changing the plan).
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

UNLIMITED = -1


async def get_plan(session: AsyncSession, plan_id: str) -> dict:
    row = await session.execute(
        text(
            "SELECT id, name, price_monthly_usd, features, limits"
            " FROM plans WHERE id = :id"
        ),
        {"id": plan_id},
    )
    record = row.mappings().one_or_none()
    if record is None:
        return {"id": "free", "name": "Free", "price_monthly_usd": 0,
                "features": {}, "limits": {}}
    return dict(record)


async def get_effective(session: AsyncSession, tenant_id: uuid.UUID, plan_id: str) -> dict:
    plan = await get_plan(session, plan_id)
    row = await session.execute(
        text("SELECT features FROM tenant_settings WHERE tenant_id = :t"),
        {"t": tenant_id},
    )
    overrides = row.scalar_one_or_none() or {}
    features = {**plan["features"], **(overrides or {})}
    plan["features"] = features
    return plan


def has_feature(plan: dict, feature: str) -> bool:
    return bool(plan.get("features", {}).get(feature, False))


def require_feature(plan: dict, feature: str) -> None:
    if not has_feature(plan, feature):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Your plan does not include '{feature}'. Please upgrade.",
        )


async def check_limit(
    session: AsyncSession, plan: dict, limit_key: str, table: str
) -> None:
    """Raise 402 when a plan limit (users/vehicles/orders_per_month) is hit."""
    limit = int(plan.get("limits", {}).get(limit_key, UNLIMITED))
    if limit == UNLIMITED:
        return
    if limit_key == "orders_per_month":
        row = await session.execute(
            text(
                "SELECT count(*) FROM service_orders"
                " WHERE created_at >= date_trunc('month', now())"
            )
        )
    else:
        row = await session.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608 (fixed table names)
    current = int(row.scalar_one())
    if current >= limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Plan limit reached ({limit_key}: {limit}). Please upgrade.",
        )
