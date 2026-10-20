from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.supplier import SUPPLIER_PROVIDERS
from app.schemas.common import ORMModel


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: str = Field(default="stub", max_length=20)
    portal_url: str | None = Field(default=None, max_length=500)

    @field_validator("provider")
    @classmethod
    def _known_provider(cls, value: str) -> str:
        if value not in SUPPLIER_PROVIDERS:
            raise ValueError(
                f"Unknown provider. Choose one of: {', '.join(SUPPLIER_PROVIDERS)}"
            )
        return value

    @field_validator("portal_url")
    @classmethod
    def _http_url(cls, value: str | None) -> str | None:
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("Portal URL must start with http:// or https://")
        return value


class SupplierOut(ORMModel):
    id: uuid.UUID
    name: str
    provider: str
    portal_url: str | None
    catalog_size: int = 0
    created_at: datetime


class CatalogImportResult(BaseModel):
    imported: int
    updated: int
    skipped: int


class OfferOut(BaseModel):
    connection_id: uuid.UUID
    supplier: str
    sku: str
    brand: str | None
    description: str
    cost: Decimal
    price: Decimal
    stock_qty: Decimal
    portal_url: str | None


class OfferImportIn(BaseModel):
    connection_id: uuid.UUID
    sku: str = Field(min_length=1, max_length=80)


class OfferImportOut(BaseModel):
    part_id: uuid.UUID
    created: bool
