"""Authentication / authorization dependencies.

Trust boundary: for authenticated requests the JWT `tenant` claim is
authoritative; the routing hint (subdomain/header) is only used to locate the
tenant for unauthenticated lookups (login, signup, API keys). Every path ends
with `set_rls_context`, so all subsequent queries in the request transaction
are RLS-filtered by the database itself.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.security import decode_access_token, hash_refresh_token  # noqa: F401
from app.core.tenancy import resolve_tenant_id, set_rls_context
from app.db.session import get_db
from app.services import entitlements

settings = get_settings()

ROLE_RANK = {"owner": 0, "admin": 1, "manager": 2, "mechanic": 3, "viewer": 4, "api": 5}


@dataclass
class AuthContext:
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None
    role: str
    tenant: dict
    plan: dict
    via: str

    def require_rank(self, *roles: str) -> None:
        if self.role == "api":
            return
        if self.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your role does not allow this action",
            )


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def _load_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> dict:
    row = await session.execute(
        text("SELECT id, slug, name, plan, status, region FROM tenants WHERE id = :t"),
        {"t": tenant_id},
    )
    record = row.mappings().one_or_none()
    if record is None or record["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Workspace unavailable"
        )
    return dict(record)


async def get_auth_context(
    request: Request, session: AsyncSession = Depends(get_db)
) -> AuthContext:
    tenant_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    role: str | None = None
    via = ""

    auth_header = request.headers.get("authorization", "")
    api_key = request.headers.get("x-api-key")

    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        try:
            payload = decode_access_token(token)
            tenant_id = uuid.UUID(payload["tenant"])
            user_id = uuid.UUID(payload["sub"])
        except (jwt.InvalidTokenError, KeyError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        via = "jwt"
    elif api_key:
        via = "api_key"
        tenant_id = await resolve_tenant_id(
            session,
            slug=getattr(request.state, "tenant_slug", None),
            domain=getattr(request.state, "host_domain", None),
        )
        if tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key requests must include a workspace (subdomain or X-Tenant-Slug)",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tenant = await _load_tenant(session, tenant_id)

    await set_rls_context(session, tenant_id, user_id)

    if via == "jwt":
        row = await session.execute(
            text(
                "SELECT id, role, is_active FROM users WHERE id = :u AND tenant_id = :t"
            ),
            {"u": user_id, "t": tenant_id},
        )
        record = row.mappings().one_or_none()
        if record is None or not record["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Account disabled"
            )
        role = record["role"]  # fresh role from DB, not the token
    else:
        row = await session.execute(
            text(
                "SELECT id FROM api_keys WHERE key_hash = :h"
                " AND revoked_at IS NULL AND tenant_id = :t"
            ),
            {"h": hash_refresh_token(api_key), "t": tenant_id},
        )
        record = row.scalar_one_or_none()
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
            )
        await session.execute(
            text("UPDATE api_keys SET last_used_at = now() WHERE id = :i"),
            {"i": record},
        )
        role = "api"

    # Authenticated, per-plan throttling (noisy-neighbor protection).
    allowed, retry_after = await limiter.hit(
        f"rl:tenant:{tenant_id}", settings.plan_rate_limit(tenant["plan"])
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You are sending requests too quickly for your plan. Please retry shortly.",
            headers={"Retry-After": str(retry_after)},
        )

    plan = await entitlements.get_effective(session, tenant_id, tenant["plan"])

    request.state.tenant_id = str(tenant_id)
    request.state.user_id = str(user_id) if user_id else None

    return AuthContext(
        tenant_id=tenant_id,
        user_id=user_id,
        role=role or "viewer",
        tenant=tenant,
        plan=plan,
        via=via,
    )


def require_roles(*roles: str):
    async def dependency(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        ctx.require_rank(*roles)
        return ctx

    return dependency


def require_feature(feature: str):
    async def dependency(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        entitlements.require_feature(ctx.plan, feature)
        return ctx

    return dependency
