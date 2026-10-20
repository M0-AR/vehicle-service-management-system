"""Provider-agnostic billing interface.

Merchant-of-record first (Paddle) with Stripe as an alternative — MoR handles
global VAT/sales-tax registration for digital services (verified,
docs/RESEARCH.md §billing). The stub provider keeps local dev keyless.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Mapping, Protocol


@dataclass
class WebhookEffect:
    """What a provider webhook told us to do, already signature-verified."""

    event_id: str
    event_type: str
    handled: bool = False
    tenant_id: uuid.UUID | None = None
    plan: str | None = None
    status: str | None = None
    period_end: str | None = None
    external_customer_id: str | None = None
    subscription_id: str | None = None
    invoice_id: uuid.UUID | None = None
    detail: str | None = None
    raw: dict = field(default_factory=dict)


class BillingProvider(Protocol):
    name: str

    def verify_and_parse(
        self, raw_body: bytes, headers: Mapping[str, str]
    ) -> WebhookEffect:
        """Verify the webhook signature; raise ValueError when invalid."""
        ...

    async def create_checkout(
        self,
        *,
        tenant_id: uuid.UUID,
        plan: str,
        currency: str,
        success_url: str | None,
        cancel_url: str | None,
    ) -> tuple[str | None, str]:
        """Returns (checkout_url | None, human message)."""
        ...
