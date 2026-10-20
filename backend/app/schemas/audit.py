from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    user_name: str | None = None
    action: str
    entity: str
    entity_id: str | None
    meta: dict
    ip: str | None
    created_at: datetime


class ApiKeyIn(BaseModel):
    name: str


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    last_used_at: datetime | None
    created_at: datetime
    revoked_at: datetime | None


class ApiKeyCreated(BaseModel):
    id: uuid.UUID
    name: str
    key: str
    warning: str = "Store this key now — it is shown only once."
