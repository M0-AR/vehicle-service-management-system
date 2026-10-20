from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AccountingConnectionOut(ORMModel):
    provider: str
    status: str
    external_tenant_id: str | None
    accounts: dict[str, str]
    last_synced_at: datetime | None


class AccountingRunOut(ORMModel):
    id: uuid.UUID
    provider: str
    period_start: date
    period_end: date
    status: str
    invoices_count: int
    total_amount: Decimal
    currency: str
    detail: str | None
    created_at: datetime
    completed_at: datetime | None


class AccountingStatus(BaseModel):
    provider: str
    configured: bool
    connection: AccountingConnectionOut | None
    pending_invoices: int
    last_run: AccountingRunOut | None


class AccountingConnectOut(BaseModel):
    connected: bool
    authorize_url: str | None = None
    message: str


class AccountingCallbackIn(BaseModel):
    code: str = Field(min_length=1, max_length=4000)
    state: str = Field(min_length=1, max_length=4000)
    realm_id: str | None = Field(default=None, max_length=120)


class AccountingMappingIn(BaseModel):
    payment: str = Field(min_length=1, max_length=30)
    income: str = Field(min_length=1, max_length=30)
    tax: str = Field(min_length=1, max_length=30)


class AccountingSyncIn(BaseModel):
    period_start: date
    period_end: date
