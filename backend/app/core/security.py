"""Password hashing (bcrypt) + JWT / opaque refresh-token helpers.

Verified decisions (docs/RESEARCH.md):
- PyJWT over python-jose (CVE history).
- Access tokens short-lived; refresh tokens opaque, hashed at rest, rotated.
- JWT `sub` claim is a string per RFC 7519.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings

settings = get_settings()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    *, user_id: uuid.UUID, tenant_id: uuid.UUID, role: str, email: str
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tenant": str(tenant_id),
        "role": role,
        "email": email,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(
            (now + timedelta(minutes=settings.access_token_minutes)).timestamp()
        ),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Raises jwt.InvalidTokenError on any problem."""
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def new_refresh_token() -> tuple[str, str]:
    """Returns (raw_token, sha256_hex). Only the hash is stored."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days)


def new_api_key() -> tuple[str, str]:
    """Returns (raw_key, sha256_hex) for tenant API keys (api_access feature)."""
    raw = "vsm_" + secrets.token_urlsafe(36)
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()
