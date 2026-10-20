from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = None
    notes: str | None = None


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = None
    notes: str | None = None


class CustomerOut(ORMModel):
    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    address: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class CustomerSummary(ORMModel):
    id: uuid.UUID
    name: str
    phone: str | None
    vehicle_count: int = 0
    open_orders: int = 0
    total_billed: Decimal = Decimal("0")
