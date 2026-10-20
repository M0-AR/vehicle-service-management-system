from __future__ import annotations

import logging

from app.core.config import get_settings
from app.services.billing.paddle import PaddleProvider
from app.services.billing.stripe import StripeProvider
from app.services.billing.stub import StubProvider

log = logging.getLogger("vsms.billing")
settings = get_settings()

_PROVIDERS = {
    "stub": StubProvider,
    "paddle": PaddleProvider,
    "stripe": StripeProvider,
}


def get_provider():
    provider = _PROVIDERS.get(settings.billing_provider, StubProvider)()
    if provider.name == "stub" and settings.env != "dev":
        log.warning(
            "billing provider is 'stub' outside dev — plan changes are applied"
            " directly with no payment. Configure PADDLE_API_KEY/STRIPE_SECRET_KEY."
        )
    return provider
