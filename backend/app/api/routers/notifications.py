"""Staff-facing notification log + SMS/email test endpoint.

Notifications are written to an outbox by business events (order ready,
booking received, review request) and campaigns. This router exposes the log
and a test send so a workshop can verify its Twilio or SMTP configuration
before relying on it.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, require_roles
from app.db.session import get_db
from app.models.notification import Notification
from app.models.tenant import Tenant
from app.schemas.common import Page
from app.schemas.features import NotificationOut, NotificationTestIn
from app.services import entitlements, notifications

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=Page[NotificationOut])
async def list_notifications(
    notification_status: str | None = Query(default=None, alias="status"),
    channel: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> Page[NotificationOut]:
    where = []
    params: dict = {}
    if notification_status:
        where.append("status = :status")
        params["status"] = notification_status
    if channel:
        where.append("channel = :channel")
        params["channel"] = channel
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total = await session.scalar(
        text(f"SELECT count(*) FROM notifications {where_sql}"), params
    )
    rows = await session.scalars(
        select(Notification)
        .where(
            *(
                [Notification.status == notification_status]
                if notification_status
                else []
            ),
            *([Notification.channel == channel] if channel else []),
        )
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page[NotificationOut](
        items=[NotificationOut.model_validate(r) for r in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.post("/test", response_model=NotificationOut)
async def send_test(
    payload: NotificationTestIn,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> NotificationOut:
    ctx.require_rank("owner", "admin", "manager")
    if payload.channel == "sms":
        entitlements.require_feature(ctx.plan, "sms_notifications")
    tenant = await session.get(Tenant, ctx.tenant_id)
    body = notifications.render(
        "test", shop=tenant.name if tenant else "your workshop"
    )
    if payload.message:
        body = payload.message
    row = await notifications.queue_notification(
        session,
        tenant_id=ctx.tenant_id,
        channel=payload.channel,
        recipient=payload.to,
        template="test",
        body=body,
    )
    if row.status == "skipped":
        if payload.channel == "sms":
            detail = (
                "SMS is not configured on this server. Set SMS_ACCOUNT_SID,"
                " SMS_AUTH_TOKEN and SMS_FROM_NUMBER."
            )
        else:
            detail = (
                "Email is not configured on this server. Set SMTP_HOST and"
                " SMTP_FROM (optionally SMTP_USERNAME/SMTP_PASSWORD)."
            )
        raise HTTPException(status_code=409, detail=detail)
    return NotificationOut.model_validate(row)
