"""Stripe Billing (alternative provider).

Webhook verification: `Stripe-Signature: t=...,v1=...`; signed payload is
`"{t}.{raw_body}"` HMAC-SHA256'd with the signing secret (documented scheme).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Mapping

import httpx

from app.core.config import get_settings
from app.services.billing.base import WebhookEffect

settings = get_settings()

EVENT_MAP = {
    "checkout.session.completed": "active",
    "customer.subscription.created": "active",
    "customer.subscription.updated": "active",
    "customer.subscription.deleted": "canceled",
    "invoice.payment_failed": "past_due",
}


class StripeProvider:
    name = "stripe"

    def verify_and_parse(
        self, raw_body: bytes, headers: Mapping[str, str]
    ) -> WebhookEffect:
        secret = settings.stripe_webhook_secret
        if not secret:
            raise ValueError("STRIPE_WEBHOOK_SECRET is not configured")
        header = headers.get("stripe-signature", "")
        parts = dict(
            part.split("=", 1) for part in header.split(",") if "=" in part
        )
        ts, v1 = parts.get("t"), parts.get("v1")
        if not ts or not v1:
            raise ValueError("missing Stripe-Signature parts")
        try:
            skew = abs(time.time() - int(ts))
        except ValueError as exc:
            raise ValueError("bad ts") from exc
        if skew > 300:
            raise ValueError("webhook timestamp out of tolerance")
        signed = f"{ts}.{raw_body.decode('utf-8')}".encode("utf-8")
        expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, v1):
            raise ValueError("signature mismatch")

        payload = json.loads(raw_body)
        obj = (payload.get("data", {}) or {}).get("object", {}) or {}
        metadata = obj.get("metadata", {}) or {}
        tenant_raw = metadata.get("tenant_id")
        effect = WebhookEffect(
            event_id=payload.get("id", ""),
            event_type=payload.get("type", ""),
            raw=payload,
        )
        if tenant_raw:
            try:
                effect.tenant_id = uuid.UUID(str(tenant_raw))
            except ValueError:
                effect.tenant_id = None
        invoice_raw = metadata.get("invoice_id")
        if invoice_raw:
            try:
                effect.invoice_id = uuid.UUID(str(invoice_raw))
            except ValueError:
                effect.invoice_id = None

        if effect.event_type in EVENT_MAP:
            effect.handled = True
            effect.status = EVENT_MAP[effect.event_type]
            effect.subscription_id = obj.get("subscription") or obj.get("id")
            effect.external_customer_id = obj.get("customer")
            plan = metadata.get("plan")
            if plan:
                effect.plan = plan
            effect.period_end = obj.get("current_period_end")
            if effect.event_type == "customer.subscription.deleted":
                effect.plan = "free"
            if effect.event_type == "checkout.session.completed":
                effect.subscription_id = obj.get("subscription")
                effect.external_customer_id = obj.get("customer")
        return effect

    async def create_payment_checkout(
        self,
        *,
        tenant_id: uuid.UUID,
        invoice_id: uuid.UUID,
        invoice_number: str,
        amount_cents: int,
        currency: str,
        success_url: str | None,
        cancel_url: str | None,
    ) -> tuple[str | None, str]:
        """Checkout in `payment` mode for one invoice (no subscription)."""
        if not settings.stripe_secret_key:
            return None, "Stripe is not configured (STRIPE_SECRET_KEY missing)."
        if amount_cents < 50:
            return None, "The invoice total is too small for online payment."
        form = {
            "mode": "payment",
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": currency.lower(),
            "line_items[0][price_data][unit_amount]": str(amount_cents),
            "line_items[0][price_data][product_data][name]": f"Invoice {invoice_number}",
            "metadata[tenant_id]": str(tenant_id),
            "metadata[invoice_id]": str(invoice_id),
            "payment_intent_data[metadata][tenant_id]": str(tenant_id),
            "payment_intent_data[metadata][invoice_id]": str(invoice_id),
            "success_url": success_url or "https://example.com/payment/success",
            "cancel_url": cancel_url or "https://example.com/payment/cancel",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=form,
                headers={"Authorization": f"Bearer {settings.stripe_secret_key}"},
            )
        if response.status_code >= 400:
            return None, f"Stripe error: {response.text[:200]}"
        return response.json().get("url"), "Redirecting to secure payment."

    async def create_checkout(
        self,
        *,
        tenant_id: uuid.UUID,
        plan: str,
        currency: str,
        success_url: str | None,
        cancel_url: str | None,
    ) -> tuple[str | None, str]:
        if not settings.stripe_secret_key:
            return None, "Stripe is not configured (STRIPE_SECRET_KEY missing)."
        price_id = os.environ.get(f"STRIPE_PRICE_{plan.upper()}", "")
        if not price_id:
            return None, (
                f"No Stripe price configured for plan '{plan}'"
                f" (set STRIPE_PRICE_{plan.upper()})."
            )
        form = {
            "mode": "subscription",
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
            "metadata[tenant_id]": str(tenant_id),
            "metadata[plan]": plan,
            "subscription_data[metadata][tenant_id]": str(tenant_id),
            "subscription_data[metadata][plan]": plan,
            "success_url": success_url or "https://example.com/billing/success",
            "cancel_url": cancel_url or "https://example.com/billing/cancel",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=form,
                headers={"Authorization": f"Bearer {settings.stripe_secret_key}"},
            )
        if response.status_code >= 400:
            return None, f"Stripe error: {response.text[:200]}"
        return response.json().get("url"), "Redirecting to Stripe checkout."
