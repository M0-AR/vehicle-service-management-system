"""Billing webhooks (unauthenticated — verified by provider signature).

Sequence: verify signature -> resolve tenant (registry lookup) -> dedupe by
provider event id -> apply plan/status -> mark processed -> ack. Invalid
signatures are 400; unknown tenants are acknowledged without side effects so
providers stop retrying events that belong to another environment.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import set_rls_context
from app.db.session import get_db
from app.schemas.billing import WebhookAck
from app.services import audit
from app.services.billing import apply as billing_apply
from app.services.billing.paddle import PaddleProvider
from app.services.billing.stripe import StripeProvider
from fastapi import Depends

log = logging.getLogger("vsms.billing.webhooks")
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

PROVIDERS = {"paddle": PaddleProvider, "stripe": StripeProvider}


async def _apply_invoice_payment(
    session: AsyncSession, tenant_id, provider_name: str, effect
) -> bool:
    """Mark an invoice paid from a verified payment webhook (idempotent)."""
    from datetime import datetime, timezone

    from app.models.invoice import Invoice

    await set_rls_context(session, tenant_id)
    invoice = await session.get(Invoice, effect.invoice_id)
    if invoice is None:
        return False
    obj = (effect.raw.get("data", {}) or {}).get("object", {}) or {}
    if effect.event_type == "checkout.session.completed":
        if obj.get("payment_status") not in (None, "paid"):
            return False
    elif effect.event_type not in (
        "payment_intent.succeeded",
        "checkout.session.async_payment_succeeded",
    ):
        return False
    if invoice.status == "paid":
        return True

    invoice.status = "paid"
    invoice.paid_at = datetime.now(timezone.utc)
    invoice.payment_provider = provider_name
    invoice.payment_session_id = str(obj.get("id") or "")[:255] or None
    if invoice.issued_at is None:
        invoice.issued_at = invoice.paid_at
    await session.flush()
    await audit.record(
        session,
        tenant_id=tenant_id,
        user_id=None,
        action="invoice.paid",
        entity="invoice",
        entity_id=invoice.id,
        meta={
            "number": invoice.number,
            "provider": provider_name,
            "amount": str(invoice.total),
            "via": "webhook",
        },
    )
    return True


@router.post("/billing/{provider_name}", response_model=WebhookAck)
async def billing_webhook(
    provider_name: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> WebhookAck:
    provider_cls = PROVIDERS.get(provider_name)
    if provider_cls is None:
        raise HTTPException(status_code=404, detail="Unknown provider")
    provider = provider_cls()

    raw_body = await request.body()
    try:
        effect = provider.verify_and_parse(raw_body, request.headers)
    except ValueError as exc:
        log.warning("rejected %s webhook: %s", provider_name, exc)
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    tenant_id = await billing_apply.resolve_tenant(session, effect)
    if tenant_id is None:
        log.warning(
            "webhook %s/%s could not be matched to a tenant",
            provider_name,
            effect.event_id,
        )
        return WebhookAck(received=True, applied=False, detail="Tenant not found")

    effect.tenant_id = tenant_id
    if not await billing_apply.record_event(session, provider_name, effect):
        return WebhookAck(received=True, applied=False, detail="Duplicate event")

    if effect.invoice_id is not None:
        applied = await _apply_invoice_payment(
            session, tenant_id, provider_name, effect
        )
        await billing_apply.mark_processed(session, provider_name, effect.event_id)
        return WebhookAck(
            received=True,
            applied=applied,
            detail="invoice payment" if applied else "Event noted",
        )

    if effect.handled and effect.plan:
        await set_rls_context(session, tenant_id)
        await billing_apply.apply_plan_change(
            session,
            tenant_id=tenant_id,
            plan=effect.plan,
            status=effect.status,
            period_end=effect.period_end,
            external_customer_id=effect.external_customer_id,
            subscription_id=effect.subscription_id,
        )
        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=None,
            action="billing.webhook_applied",
            entity="billing_account",
            entity_id=tenant_id,
            meta={"provider": provider_name, "event": effect.event_type, "plan": effect.plan},
        )
        await billing_apply.mark_processed(session, provider_name, effect.event_id)
        return WebhookAck(received=True, applied=True, detail=effect.event_type)

    await billing_apply.mark_processed(session, provider_name, effect.event_id)
    return WebhookAck(received=True, applied=False, detail="Event noted")
