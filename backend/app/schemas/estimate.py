from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.service import ItemIn, ItemOut


class EstimateIn(BaseModel):
    vehicle_id: uuid.UUID
    description: str = Field(min_length=3)
    notes: str | None = None
    items: list[ItemIn] = []


class EstimateUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=3)
    notes: str | None = None


class EstimateOut(ORMModel):
    id: uuid.UUID
    number: str
    status: str
    description: str
    vehicle_id: uuid.UUID
    customer_id: uuid.UUID | None
    notes: str | None
    sent_at: datetime | None
    responded_at: datetime | None
    responded_by_name: str | None
    converted_order_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    items: list[ItemOut] = []
    totals: dict = {}


class EstimateListItem(ORMModel):
    id: uuid.UUID
    number: str
    status: str
    description: str
    vehicle_plate: str | None = None
    customer_name: str | None = None
    total: Decimal = Decimal("0")
    created_at: datetime
