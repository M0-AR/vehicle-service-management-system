from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator


class SlugCheck(BaseModel):
    slug: str
    available: bool
    message: str | None = None


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=3, max_length=40)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    business_name: str | None = Field(default=None, max_length=160)

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, v: str) -> str:
        return v.strip().lower()


class SignupResponse(BaseModel):
    tenant_id: str
    slug: str
    url: str
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class BrandingOut(BaseModel):
    slug: str
    display_name: str
    primary_color: str
    accent_color: str
    logo_url: str | None = None
    support_email: str | None = None
    currency: str = "USD"
    locale: str = "en"


class BrandingUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    primary_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    accent_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    logo_url: str | None = Field(default=None, max_length=500)
    support_email: EmailStr | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    locale: str | None = Field(default=None, max_length=10)
    timezone: str | None = Field(default=None, max_length=64)
    tax_rate: float | None = Field(default=None, ge=0, le=1)


class TenantProfileOut(BaseModel):
    id: str
    slug: str
    name: str
    plan: str
    region: str
    status: str


class DomainCreate(BaseModel):
    domain: str = Field(min_length=4, max_length=255)

    @field_validator("domain")
    @classmethod
    def normalize(cls, v: str) -> str:
        v = v.strip().lower().rstrip(".")
        if "://" in v or "/" in v:
            raise ValueError("Enter a bare hostname, e.g. service.my-garage.com")
        return v


class DomainOut(BaseModel):
    domain: str
    status: str
    verification_token: str
    txt_record: str
    created_at: str | None = None
    verified_at: str | None = None
