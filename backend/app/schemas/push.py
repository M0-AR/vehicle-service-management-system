from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PushConfigOut(BaseModel):
    enabled: bool
    public_key: str | None = None


class PushKeysIn(BaseModel):
    p256dh: str = Field(min_length=8, max_length=512)
    auth: str = Field(min_length=8, max_length=512)


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=12, max_length=2048)
    keys: PushKeysIn
    user_agent: str | None = Field(default=None, max_length=255)


class PushSubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    endpoint: str
    user_agent: str | None
    created_at: datetime


class PushTestOut(BaseModel):
    sent: int
    failed: int
