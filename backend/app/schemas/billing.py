from __future__ import annotations

from pydantic import BaseModel


class PlanOut(BaseModel):
    id: str
    name: str
    price_monthly_usd: float
    features: dict
    limits: dict


class BillingStatusOut(BaseModel):
    plan: str
    status: str
    provider: str
    currency: str
    current_period_end: str | None = None
    checkout_available: bool
    portal_available: bool


class CheckoutRequest(BaseModel):
    plan: str
    success_url: str | None = None
    cancel_url: str | None = None


class CheckoutResponse(BaseModel):
    url: str | None
    message: str


class WebhookAck(BaseModel):
    received: bool = True
    applied: bool = False
    detail: str | None = None
