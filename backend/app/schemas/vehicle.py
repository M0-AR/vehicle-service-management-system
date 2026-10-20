from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.vehicle import FUEL_TYPES, VEHICLE_STATUSES
from app.schemas.common import ORMModel


class VehicleIn(BaseModel):
    plate_number: str = Field(min_length=1, max_length=20)
    make: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=60)
    year: int | None = Field(default=None, ge=1900, le=2100)
    vin: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, max_length=40)
    fuel_type: str = "petrol"
    mileage: int = Field(default=0, ge=0)
    customer_id: uuid.UUID | None = None
    notes: str | None = None

    @field_validator("fuel_type")
    @classmethod
    def check_fuel(cls, v: str) -> str:
        if v not in FUEL_TYPES:
            raise ValueError(f"fuel_type must be one of {FUEL_TYPES}")
        return v

    @field_validator("plate_number")
    @classmethod
    def normalize_plate(cls, v: str) -> str:
        return v.strip().upper()


class VehicleUpdate(BaseModel):
    plate_number: str | None = Field(default=None, min_length=1, max_length=20)
    make: str | None = Field(default=None, min_length=1, max_length=60)
    model: str | None = Field(default=None, min_length=1, max_length=60)
    year: int | None = Field(default=None, ge=1900, le=2100)
    vin: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, max_length=40)
    fuel_type: str | None = None
    mileage: int | None = Field(default=None, ge=0)
    status: str | None = None
    customer_id: uuid.UUID | None = None
    notes: str | None = None


class VehicleOut(ORMModel):
    id: uuid.UUID
    plate_number: str
    make: str
    model: str
    year: int | None
    vin: str | None
    color: str | None
    fuel_type: str
    mileage: int
    status: str
    customer_id: uuid.UUID | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class VinDecodeOut(BaseModel):
    vin: str
    decoded: bool
    make: str | None = None
    model: str | None = None
    year: int | None = None
    trim: str | None = None
    body_class: str | None = None
    fuel_type: str | None = None
    engine: str | None = None
    vehicle_type: str | None = None
    message: str | None = None


class VehicleSummary(ORMModel):
    id: uuid.UUID
    plate_number: str
    make: str
    model: str
    year: int | None
    status: str
    customer_name: str | None = None
    open_orders: int = 0
