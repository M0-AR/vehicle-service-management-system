"""Paddle Billing (merchant of record) — primary production provider.

Webhook verification implements Paddle's documented scheme: the
`Paddle-Signature` header carries `ts=...;h1=...`; the signed payload is
`"{ts}:{raw_body}"` HMAC-SHA256'd with the webhook secret.

Checkout uses the Paddle Billing API with price IDs per plan
(PADDLE_PRICE_<PLAN> envs). Subscription lifecycle events map to plan/status.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Mapping

import httpx

from app.core.config import get_settings
from app.services.billing.base import WebhookEffect

settings = get_settings()

PLAN_EVENT_MAP = {
    "subscription.created": "active",
    "subscription.activated": "active",
    "subscription.trialing": "trialing",
    "subscription.past_due": "past_due",
    "subscription.paused": "paused",
    "subscription.canceled": "canceled",
}

API_BASE = {
    "sandbox": "https://sandbox-api.paddle.com",
    "production": "https://api.paddle.com",
}


class PaddleProvider:
    name = "paddle"

    def verify_and_parse(
        self, raw_body: bytes, headers: Mapping[str, str]
    ) -> WebhookEffect:
        secret = settings.paddle_webhook_secret
        if not secret:
            raise ValueError("PADDLE_WEBHOOK_SECRET is not configured")
        signature_header = headers.get("paddle-signature", "")
        parts = dict(
            part.split("=", 1) for part in signature_header.split(";") if "=" in part
        )
        ts, h1 = parts.get("ts"), parts.get("h1")
        if not ts or not h1:
            raise ValueError("missing Paddle-Signature parts")
        try:
            skew = abs(time.time() - int(ts))
        except ValueError as exc:
            raise ValueError("bad ts") from exc
        if skew > 300:
            raise ValueError("webhook timestamp out of tolerance")
        signed = f"{ts}:{raw_body.decode('utf-8')}".encode("utf-8")
        expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, h1):
            raise ValueError("signature mismatch")

        payload = json.loads(raw_body)
        data = payload.get("data", {}) or {}
        custom = data.get("custom_data", {}) or {}
        tenant_raw = custom.get("tenant_id")
        effect = WebhookEffect(
            event_id=payload.get("event_id", ""),
            event_type=payload.get("event_type", ""),
            raw=payload,
        )
        if tenant_raw:
            try:
                effect.tenant_id = uuid.UUID(str(tenant_raw))
            except ValueError:
                effect.tenant_id = None

        if effect.event_type in PLAN_EVENT_MAP:
            effect.handled = True
            effect.status = PLAN_EVENT_MAP[effect.event_type]
            effect.subscription_id = data.get("id")
            effect.external_customer_id = data.get("customer_id")
            plan = custom.get("plan")
            if plan:
                effect.plan = plan
            period = data.get("current_billing_period", {}) or {}
            effect.period_end = period.get("ends_at")
            if effect.event_type == "subscription.canceled":
                effect.plan = "free"
        return effect

    async def create_checkout(
        self,
        *,
        tenant_id: uuid.UUID,
        plan: str,
        currency: str,
        success_url: str | None,
        cancel_url: str | None,
    ) -> tuple[str | None, str]:
        if not settings.paddle_api_key:
            return None, "Paddle is not configured (PADDLE_API_KEY missing)."
        price_id = _price_id_for_plan(plan)
        if not price_id:
            return None, (
                f"No Paddle price configured for plan '{plan}'"
                f" (set PADDLE_PRICE_{plan.upper()})."
            )
        base = API_BASE.get(settings.paddle_environment, API_BASE["sandbox"])
        body = {
            "items": [{"price_id": price_id, "quantity": 1}],
            "custom_data": {"tenant_id": str(tenant_id), "plan": plan},
        }
        if success_url:
            body["checkout"] = {"url": success_url}
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{base}/transactions",
                json=body,
                headers={"Authorization": f"Bearer {settings.paddle_api_key}"},
            )
        if response.status_code >= 400:
            return None, f"Paddle error: {response.text[:200]}"
        data = response.json().get("data", {})
        return data.get("checkout", {}).get("url"), "Redirecting to Paddle checkout."


def _price_id_for_plan(plan: str) -> str:
    import os

    return os.environ.get(f"PADDLE_PRICE_{plan.upper()}", "")
