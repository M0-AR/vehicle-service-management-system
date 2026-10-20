from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

Segment = Literal["all", "inactive", "due_service"]
Channel = Literal["sms", "email"]


class CampaignPreviewIn(BaseModel):
    channel: Channel = "sms"
    segment: Segment = "all"
    lookback_days: int = Field(default=90, ge=7, le=730)


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    channel: Channel = "sms"
    segment: Segment = "all"
    lookback_days: int = Field(default=90, ge=7, le=730)
    body: str = Field(min_length=1, max_length=1600)


class CampaignPreviewOut(BaseModel):
    customers_count: int
    recipients_count: int


class CampaignRecipientOut(ORMModel):
    id: uuid.UUID
    customer_id: uuid.UUID | None
    recipient: str
    status: str
    error: str | None
    created_at: datetime


class CampaignOut(ORMModel):
    id: uuid.UUID
    name: str
    channel: str
    segment: str
    lookback_days: int
    body: str
    status: str
    recipients_count: int
    sent_count: int
    skipped_count: int
    failed_count: int
    sent_at: datetime | None
    created_at: datetime


class CampaignDetailOut(CampaignOut):
    recipients: list[CampaignRecipientOut] = []
