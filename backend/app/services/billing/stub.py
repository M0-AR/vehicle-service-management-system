"""Stub billing provider — development/demo only, deliberately keyless.

`create_checkout` applies the plan change immediately so the upgrade flow is
fully testable without external accounts. NEVER select this in production;
`registry.get_provider()` logs a warning when the stub is active outside dev.
"""

from __future__ import annotations

import uuid
from typing import Mapping

from app.services.billing.base import WebhookEffect


class StubProvider:
    name = "stub"

    def verify_and_parse(
        self, raw_body: bytes, headers: Mapping[str, str]
    ) -> WebhookEffect:
        raise ValueError("stub provider does not accept webhooks")

    async def create_checkout(
        self,
        *,
        tenant_id: uuid.UUID,
        plan: str,
        currency: str,
        success_url: str | None,
        cancel_url: str | None,
    ) -> tuple[str | None, str]:
        return (
            None,
            "Billing is in stub mode: the plan change was applied directly "
            "(development only). Configure PADDLE_API_KEY or STRIPE_SECRET_KEY "
            "for real checkout.",
        )
