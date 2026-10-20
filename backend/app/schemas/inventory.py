from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.inventory import MOVEMENT_REASONS
from app.schemas.common import ORMModel


class PartIn(BaseModel):
    sku: str | None = Field(default=None, max_length=60)
    name: str = Field(min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=60)
    brand: str | None = Field(default=None, max_length=80)
    supplier: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=60)
    cost: Decimal = Field(default=Decimal("0"), ge=0)
    price: Decimal = Field(default=Decimal("0"), ge=0)
    stock_qty: Decimal = Field(default=Decimal("0"), ge=0)
    reorder_level: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = None


class PartUpdate(BaseModel):
    sku: str | None = Field(default=None, max_length=60)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=60)
    brand: str | None = Field(default=None, max_length=80)
    supplier: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=60)
    cost: Decimal | None = Field(default=None, ge=0)
    price: Decimal | None = Field(default=None, ge=0)
    reorder_level: Decimal | None = Field(default=None, ge=0)
    active: bool | None = None
    notes: str | None = None


class PartOut(ORMModel):
    id: uuid.UUID
    sku: str
    name: str
    category: str | None
    brand: str | None
    supplier: str | None
    location: str | None
    cost: Decimal
    price: Decimal
    stock_qty: Decimal
    reorder_level: Decimal
    active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class StockAdjustIn(BaseModel):
    delta: Decimal = Field(ne=0)
    reason: str = "adjustment"
    note: str | None = Field(default=None, max_length=255)
    order_id: uuid.UUID | None = None

    @field_validator("reason")
    @classmethod
    def check_reason(cls, v: str) -> str:
        if v not in MOVEMENT_REASONS:
            raise ValueError(f"reason must be one of {MOVEMENT_REASONS}")
        return v


class MovementOut(ORMModel):
    id: uuid.UUID
    part_id: uuid.UUID
    delta: Decimal
    reason: str
    note: str | None
    order_id: uuid.UUID | None
    user_id: uuid.UUID | None
    created_at: datetime


class InventorySummary(BaseModel):
    parts: int
    low_stock: int
    stock_value: Decimal
