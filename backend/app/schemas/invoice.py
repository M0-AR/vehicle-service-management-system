from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class InvoiceFromOrder(BaseModel):
    order_id: uuid.UUID
    due_days: int = Field(default=14, ge=0, le=365)


class InvoiceUpdate(BaseModel):
    status: str | None = None
    due_at: datetime | None = None


class InvoiceOut(ORMModel):
    id: uuid.UUID
    number: str
    order_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    status: str
    issued_at: datetime | None
    due_at: datetime | None
    subtotal: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total: Decimal
    currency: str
    paid_at: datetime | None
    payment_url: str | None = None
    payment_provider: str | None = None
    lines: list
    meta: dict
    created_at: datetime


class PaymentLinkOut(BaseModel):
    url: str
    message: str


class InvoiceListItem(ORMModel):
    id: uuid.UUID
    number: str
    status: str
    customer_name: str | None = None
    total: Decimal
    currency: str
    issued_at: datetime | None
    due_at: datetime | None
