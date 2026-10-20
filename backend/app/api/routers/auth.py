from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, client_ip, get_auth_context
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.security import (
    create_access_token,
    hash_password,
    new_refresh_token,
    refresh_token_expiry,
    verify_password,
)
from app.core.tenancy import resolve_tenant_id, set_rls_context
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    PasswordChange,
    TokenPair,
    UserOut,
)
from app.schemas.common import Ok
from app.services import audit

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "vsms_refresh"
COOKIE_PATH = f"{settings.api_v1_prefix}/auth"


def set_refresh_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.env != "dev",
        path=COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE, path=COOKIE_PATH)


async def issue_session(
    session: AsyncSession, tenant, user
) -> tuple[TokenPair, str]:
    """Create access token + opaque refresh token row. Returns (pair, raw_refresh)."""
    raw, token_hash = new_refresh_token()
    await session.execute(
        text(
            """
            INSERT INTO refresh_tokens (tenant_id, user_id, token_hash, expires_at)
            VALUES (:t, :u, :h, :exp)
            """
        ),
        {
            "t": tenant.id,
            "u": user.id,
            "h": token_hash,
            "exp": refresh_token_expiry(),
        },
    )
    pair = TokenPair(
        access_token=create_access_token(
            user_id=user.id, tenant_id=tenant.id, role=user.role, email=user.email
        ),
        expires_in=settings.access_token_minutes * 60,
    )
    return pair, raw


@router.post("/login", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> TokenPair:
    tenant_id = await resolve_tenant_id(
        session,
        slug=getattr(request.state, "tenant_slug", None),
        domain=getattr(request.state, "host_domain", None),
    )
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown workspace. Please check the address and try again.",
        )

    ip = client_ip(request) or "unknown"
    allowed, retry_after = await limiter.hit(
        f"rl:login:{tenant_id}:{ip}", settings.login_rate_per_minute
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait a minute and try again.",
            headers={"Retry-After": str(retry_after)},
        )

    await set_rls_context(session, tenant_id)
    row = await session.execute(
        text(
            "SELECT id, tenant_id, email, name, role, password_hash, is_active,"
            " created_at, last_login_at"
            " FROM users WHERE email = :e AND tenant_id = :t"
        ),
        {"e": payload.email.lower(), "t": tenant_id},
    )
    user = row.mappings().one_or_none()

    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled"
        )

    await session.execute(
        text("UPDATE users SET last_login_at = now() WHERE id = :u"), {"u": user["id"]}
    )

    tenant_row = await session.execute(
        text("SELECT id, slug, name, plan, status, region FROM tenants WHERE id = :t"),
        {"t": tenant_id},
    )
    tenant = tenant_row.mappings().one()

    pair, raw = await issue_session(session, tenant, user)
    set_refresh_cookie(response, raw)

    await audit.record(
        session,
        tenant_id=tenant_id,
        user_id=user["id"],
        action="auth.login",
        entity="user",
        entity_id=user["id"],
        ip=ip,
    )
    return pair


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> TokenPair:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    from app.core.security import hash_refresh_token

    tenant_id = await resolve_tenant_id(
        session,
        slug=getattr(request.state, "tenant_slug", None),
        domain=getattr(request.state, "host_domain", None),
    )
    if tenant_id is None:
        raise HTTPException(status_code=401, detail="Unknown workspace")

    await set_rls_context(session, tenant_id)
    row = await session.execute(
        text(
            """
            SELECT rt.id, rt.user_id, rt.expires_at, rt.revoked_at,
                   u.email, u.role, u.is_active
            FROM refresh_tokens rt
            JOIN users u ON u.id = rt.user_id
            WHERE rt.token_hash = :h AND rt.tenant_id = :t
            """
        ),
        {"h": hash_refresh_token(raw), "t": tenant_id},
    )
    token = row.mappings().one_or_none()
    now = datetime.now(timezone.utc)
    if (
        token is None
        or token["revoked_at"] is not None
        or token["expires_at"] < now
        or not token["is_active"]
    ):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Rotation: revoke the used token, issue a fresh pair.
    await session.execute(
        text("UPDATE refresh_tokens SET revoked_at = now() WHERE id = :i"),
        {"i": token["id"]},
    )
    tenant_row = await session.execute(
        text("SELECT id, slug, name, plan, status, region FROM tenants WHERE id = :t"),
        {"t": tenant_id},
    )
    tenant = tenant_row.mappings().one()
    user = SimpleNamespace(
        id=token["user_id"], email=token["email"], role=token["role"]
    )
    pair, new_raw = await issue_session(session, tenant, user)
    set_refresh_cookie(response, new_raw)
    return pair


@router.post("/logout", response_model=Ok)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> Ok:
    raw = request.cookies.get(REFRESH_COOKIE)
    tenant_id = await resolve_tenant_id(
        session,
        slug=getattr(request.state, "tenant_slug", None),
        domain=getattr(request.state, "host_domain", None),
    )
    if raw and tenant_id:
        from app.core.security import hash_refresh_token

        await set_rls_context(session, tenant_id)
        await session.execute(
            text(
                "UPDATE refresh_tokens SET revoked_at = now()"
                " WHERE token_hash = :h AND revoked_at IS NULL"
            ),
            {"h": hash_refresh_token(raw)},
        )
    clear_refresh_cookie(response)
    return Ok()


@router.get("/me", response_model=MeResponse)
async def me(ctx: AuthContext = Depends(get_auth_context), session: AsyncSession = Depends(get_db)) -> MeResponse:
    row = await session.execute(
        text(
            "SELECT id, email, name, role, is_active, created_at, last_login_at"
            " FROM users WHERE id = :u"
        ),
        {"u": ctx.user_id},
    )
    record = row.mappings().one_or_none()
    if record is None:
        raise HTTPException(status_code=401, detail="Account not found")
    return MeResponse(
        user=UserOut(**dict(record)),
        tenant=ctx.tenant,
        entitlements={"plan": ctx.plan["id"], "features": ctx.plan["features"], "limits": ctx.plan["limits"]},
    )


@router.post("/password", response_model=Ok)
async def change_password(
    payload: PasswordChange,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> Ok:
    if ctx.user_id is None:
        raise HTTPException(status_code=403, detail="API keys cannot change passwords")
    row = await session.execute(
        text("SELECT password_hash FROM users WHERE id = :u"), {"u": ctx.user_id}
    )
    current = row.scalar_one()
    if not verify_password(payload.current_password, current):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    await session.execute(
        text("UPDATE users SET password_hash = :h, updated_at = now() WHERE id = :u"),
        {"h": hash_password(payload.new_password), "u": ctx.user_id},
    )
    # Security: all other sessions die with the old password.
    await session.execute(
        text(
            "UPDATE refresh_tokens SET revoked_at = now()"
            " WHERE user_id = :u AND revoked_at IS NULL"
        ),
        {"u": ctx.user_id},
    )
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="auth.password_changed",
        entity="user",
        entity_id=ctx.user_id,
        ip=client_ip(request),
    )
    return Ok(detail="Password changed. Sign in again on your other devices.")
