from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user import ROLES
from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(ORMModel):
    id: uuid.UUID
    email: EmailStr
    name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class MeResponse(BaseModel):
    user: UserOut
    tenant: dict
    entitlements: dict


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="mechanic")

    def validated_role(self) -> str:
        if self.role not in ROLES or self.role == "owner":
            raise ValueError(f"role must be one of {ROLES[1:]}")
        return self.role


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
