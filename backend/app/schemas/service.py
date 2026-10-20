from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.service import ITEM_KINDS, ORDER_PRIORITIES, ORDER_STATUSES
from app.schemas.common import ORMModel


class ItemIn(BaseModel):
    kind: str = "labor"
    description: str = Field(default="", max_length=255)
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit_price: Decimal = Field(default=Decimal("0"), ge=0)
    part_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def check_description(self) -> "ItemIn":
        if not self.description.strip() and self.part_id is None:
            raise ValueError("description is required unless a part is linked")
        return self

    @field_validator("kind")
    @classmethod
    def check_kind(cls, v: str) -> str:
        if v not in ITEM_KINDS:
            raise ValueError(f"kind must be one of {ITEM_KINDS}")
        return v


class ItemOut(ORMModel):
    id: uuid.UUID
    kind: str
    part_id: uuid.UUID | None = None
    description: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal = Decimal("0")


class OrderIn(BaseModel):
    vehicle_id: uuid.UUID
    location_id: uuid.UUID | None = None
    description: str = Field(min_length=3)
    priority: str = "normal"
    odometer: int | None = Field(default=None, ge=0)
    scheduled_at: datetime | None = None
    mechanic_id: uuid.UUID | None = None
    estimated_cost: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None
    items: list[ItemIn] = []

    @field_validator("priority")
    @classmethod
    def check_priority(cls, v: str) -> str:
        if v not in ORDER_PRIORITIES:
            raise ValueError(f"priority must be one of {ORDER_PRIORITIES}")
        return v


class OrderUpdate(BaseModel):
    location_id: uuid.UUID | None = None
    description: str | None = Field(default=None, min_length=3)
    priority: str | None = None
    odometer: int | None = Field(default=None, ge=0)
    scheduled_at: datetime | None = None
    mechanic_id: uuid.UUID | None = None
    estimated_cost: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class StatusChange(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def check_status(cls, v: str) -> str:
        if v not in ORDER_STATUSES:
            raise ValueError(f"status must be one of {ORDER_STATUSES}")
        return v


class OrderOut(ORMModel):
    id: uuid.UUID
    number: str
    status: str
    priority: str
    description: str
    vehicle_id: uuid.UUID
    customer_id: uuid.UUID | None
    mechanic_id: uuid.UUID | None
    location_id: uuid.UUID | None
    odometer: int | None
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    estimated_cost: Decimal | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    items: list[ItemOut] = []
    totals: dict = {}


class OrderListItem(ORMModel):
    id: uuid.UUID
    number: str
    status: str
    priority: str
    description: str
    vehicle_plate: str | None = None
    customer_name: str | None = None
    mechanic_name: str | None = None
    location_name: str | None = None
    total: Decimal = Decimal("0")
    created_at: datetime
