from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class LocationIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    is_default: bool = False


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    is_default: bool | None = None


class LocationOut(ORMModel):
    id: uuid.UUID
    name: str
    address: str | None
    phone: str | None
    is_default: bool
    created_at: datetime
    updated_at: datetime
