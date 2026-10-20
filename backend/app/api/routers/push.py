"""Staff Web Push: VAPID config, per-device subscriptions and a test send."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.models.push import PushSubscription
from app.schemas.common import Ok
from app.schemas.push import (
    PushConfigOut,
    PushSubscriptionIn,
    PushSubscriptionOut,
    PushTestOut,
)
from app.services import push

router = APIRouter(prefix="/push", tags=["push"])

MANAGE_ROLES = ("owner", "admin")


@router.get("/config", response_model=PushConfigOut)
async def push_config(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> PushConfigOut:
    config_row = await push.config(session)
    if config_row is None:
        return PushConfigOut(enabled=False, public_key=None)
    return PushConfigOut(enabled=True, public_key=config_row[0])


@router.get("/subscriptions", response_model=list[PushSubscriptionOut])
async def list_push_subscriptions(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> list[PushSubscriptionOut]:
    owner_view = ctx.role in MANAGE_ROLES
    rows = await push.list_subscriptions(
        session,
        tenant_id=ctx.tenant_id,
        user_id=None if owner_view else ctx.user_id,
    )
    return [PushSubscriptionOut.model_validate(row) for row in rows]


@router.post("/subscriptions", response_model=PushSubscriptionOut, status_code=201)
async def create_push_subscription(
    payload: PushSubscriptionIn,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> PushSubscriptionOut:
    if ctx.user_id is None:
        raise HTTPException(status_code=403, detail="Sign in as a user to register a device")
    subscription = await push.subscribe(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
        user_agent=payload.user_agent
        or (request.headers.get("user-agent") or "")[:255]
        or None,
    )
    return PushSubscriptionOut.model_validate(subscription)


@router.delete("/subscriptions/{subscription_id}", response_model=Ok)
async def delete_push_subscription(
    subscription_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> Ok:
    subscription = await session.get(PushSubscription, subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if subscription.user_id != ctx.user_id and ctx.role not in MANAGE_ROLES:
        raise HTTPException(status_code=404, detail="Subscription not found")
    await session.delete(subscription)
    await session.flush()
    return Ok(detail="Push subscription removed")


@router.post("/test", response_model=PushTestOut)
async def send_test_push(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> PushTestOut:
    if ctx.user_id is None:
        raise HTTPException(status_code=403, detail="Sign in as a user to receive a test")
    sent, failed = await push.send_to_users(
        session,
        tenant_id=ctx.tenant_id,
        user_ids=[ctx.user_id],
        title="Test notification",
        body="Push notifications are working on this device.",
        url="/app/settings?tab=notifications",
    )
    return PushTestOut(sent=sent, failed=failed)
