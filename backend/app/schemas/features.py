from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.inspection import INSPECTION_ITEM_STATUSES
from app.schemas.common import ORMModel


class InspectionItemIn(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    status: str = "ok"
    note: str | None = Field(default=None, max_length=2000)
    sort_order: int = 0

    def validated_status(self) -> str:
        if self.status not in INSPECTION_ITEM_STATUSES:
            raise ValueError(f"status must be one of {INSPECTION_ITEM_STATUSES}")
        return self.status


class InspectionItemUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    status: str | None = None
    note: str | None = Field(default=None, max_length=2000)
    sort_order: int | None = None


class InspectionItemOut(ORMModel):
    id: uuid.UUID
    label: str
    status: str
    note: str | None
    photos: list = []
    sort_order: int
    created_at: datetime


class InspectionOut(ORMModel):
    id: uuid.UUID
    order_id: uuid.UUID
    status: str
    notes: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[InspectionItemOut] = []


class InspectionCreate(BaseModel):
    notes: str | None = Field(default=None, max_length=4000)


class InspectionUpdate(BaseModel):
    notes: str | None = Field(default=None, max_length=4000)
    status: str | None = None


class InspectionPhotoOut(BaseModel):
    url: str
    mime: str
    size: int
    name: str


class NotificationOut(ORMModel):
    id: uuid.UUID
    channel: str
    recipient: str
    template: str
    body: str
    status: str
    provider: str | None
    error: str | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    sent_at: datetime | None
    created_at: datetime


class NotificationTestIn(BaseModel):
    to: str = Field(min_length=3, max_length=254)
    message: str | None = Field(default=None, max_length=500)
    channel: Literal["sms", "email"] = "sms"


class BookingSlot(BaseModel):
    start: datetime
    label: str
    available: bool


class PublicBookingOut(BaseModel):
    workspace: dict
    booking_enabled: bool
    timezone: str
    slots: list[BookingSlot]
    review_url: str | None = None


class BookingRequestIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=5, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    plate_number: str = Field(min_length=1, max_length=20)
    make: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=60)
    year: int | None = Field(default=None, ge=1900, le=2100)
    service_description: str = Field(min_length=3, max_length=4000)
    preferred_at: datetime
    # Honeypot: real customers never fill this.
    company: str | None = Field(default=None, max_length=100)


class BookingRequestOut(ORMModel):
    id: uuid.UUID
    name: str
    phone: str
    email: str | None
    plate_number: str
    service_description: str
    preferred_at: datetime
    status: str
    order_id: uuid.UUID | None
    created_at: datetime


class PublicBookingResult(BaseModel):
    number: str
    scheduled_at: datetime
    message: str


class ReviewRequestOut(ORMModel):
    id: uuid.UUID
    order_id: uuid.UUID
    status: str
    rating: int | None
    comment: str | None
    submitted_at: datetime | None
    created_at: datetime
    url_path: str | None = None
    order_number: str | None = None


class PublicReviewOut(BaseModel):
    workspace: dict
    order_number: str
    status: str
    rating: int | None
    comment: str | None
    submitted_at: datetime | None
    review_url: str | None = None


class ReviewSubmitIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)
