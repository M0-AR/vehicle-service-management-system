from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class PublicWorkspace(BaseModel):
    display_name: str
    primary_color: str
    accent_color: str
    currency: str
    support_email: str | None = None


class ShareOut(BaseModel):
    token: str
    url_path: str
    kind: str


class PublicOrderItem(BaseModel):
    kind: str
    description: str


class PublicInspectionItem(BaseModel):
    label: str
    status: str
    note: str | None = None
    photos: list[str] = []


class PublicOrderOut(BaseModel):
    workspace: PublicWorkspace
    number: str
    status: str
    description: str
    vehicle: dict
    scheduled_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
    items: list[PublicOrderItem]
    inspection: list[PublicInspectionItem] = []
    inspection_completed: bool = False


class PublicEstimateItem(BaseModel):
    kind: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal


class PublicEstimateOut(BaseModel):
    workspace: PublicWorkspace
    number: str
    status: str
    description: str
    vehicle: dict
    items: list[PublicEstimateItem]
    totals: dict
    sent_at: datetime | None
    responded_at: datetime | None
    responded_by_name: str | None
    converted_order_number: str | None = None


class EstimateRespondIn(BaseModel):
    decision: str = Field(pattern="^(approve|decline)$")
    name: str | None = Field(default=None, max_length=120)
