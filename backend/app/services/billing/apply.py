"""Webhook application + plan-change side effects (provider-independent).

Dedupe: provider event ids are unique — a duplicate webhook is a no-op.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.billing.base import WebhookEffect


async def record_event(
    session: AsyncSession, provider: str, effect: WebhookEffect
) -> bool:
    """Returns False when this event was already processed (duplicate)."""
    result = await session.execute(
        text(
            """
            INSERT INTO billing_events (provider, event_id, event_type, tenant_id, payload)
            VALUES (:p, :eid, :etype, :t, :payload)
            ON CONFLICT (event_id) DO NOTHING
            RETURNING id
            """
        ),
        {
            "p": provider,
            "eid": effect.event_id,
            "etype": effect.event_type,
            "t": effect.tenant_id,
            "payload": __import__("json").dumps(effect.raw or {}),
        },
    )
    return result.scalar_one_or_none() is not None


async def resolve_tenant(session: AsyncSession, effect: WebhookEffect) -> uuid.UUID | None:
    """Find the tenant this billing event belongs to (registry lookup —
    billing_accounts is RLS-free precisely so unauthenticated webhooks can
    resolve tenants safely)."""
    if effect.tenant_id:
        return effect.tenant_id
    if effect.subscription_id:
        row = await session.execute(
            text("SELECT tenant_id FROM billing_accounts WHERE subscription_id = :s"),
            {"s": effect.subscription_id},
        )
        found = row.scalar_one_or_none()
        if found:
            return found
    if effect.external_customer_id:
        row = await session.execute(
            text(
                "SELECT tenant_id FROM billing_accounts WHERE external_customer_id = :c"
            ),
            {"c": effect.external_customer_id},
        )
        found = row.scalar_one_or_none()
        if found:
            return found
    return None


async def apply_plan_change(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    plan: str,
    status: str | None = None,
    period_end: str | None = None,
    external_customer_id: str | None = None,
    subscription_id: str | None = None,
) -> None:
    await session.execute(
        text(
            """
            UPDATE tenants SET plan = :plan WHERE id = :t
            """
        ),
        {"plan": plan, "t": tenant_id},
    )
    await session.execute(
        text(
            """
            UPDATE billing_accounts
               SET plan = :plan,
                   status = coalesce(:status, status),
                   current_period_end = coalesce(:period_end, current_period_end),
                   external_customer_id = coalesce(:cust, external_customer_id),
                   subscription_id = coalesce(:sub, subscription_id),
                   updated_at = now()
             WHERE tenant_id = :t
            """
        ),
        {
            "plan": plan,
            "status": status,
            "period_end": period_end,
            "cust": external_customer_id,
            "sub": subscription_id,
            "t": tenant_id,
        },
    )


async def mark_processed(
    session: AsyncSession, provider: str, event_id: str
) -> None:
    await session.execute(
        text(
            "UPDATE billing_events SET processed_at = now()"
            " WHERE provider = :p AND event_id = :e"
        ),
        {"p": provider, "e": event_id},
    )
