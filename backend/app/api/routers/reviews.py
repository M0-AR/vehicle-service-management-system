"""Review requests: staff sends a tokenized link, customer rates the visit.

The token is a `public_links` row of kind `review`, so rotation/revocation
semantics are shared with status and estimate links.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, require_feature, require_roles
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.tenancy import set_rls_context
from app.db.session import get_db
from app.models.customer import Customer
from app.models.review import ReviewRequest
from app.models.service import ServiceOrder
from app.models.tenant import DEFAULT_BRAND, TenantSettings
from app.schemas.features import (
    PublicReviewOut,
    ReviewRequestOut,
    ReviewSubmitIn,
)
from app.services import audit, notifications, sharing

router = APIRouter(tags=["reviews"])

STAFF_ROLES = ("owner", "admin", "manager")


async def _workspace(session: AsyncSession, tenant_id: uuid.UUID) -> dict:
    row = await session.execute(
        text(
            """
            SELECT t.name, s.brand FROM tenants t
              LEFT JOIN tenant_settings s ON s.tenant_id = t.id
             WHERE t.id = :t
            """
        ),
        {"t": tenant_id},
    )
    record = row.mappings().one()
    brand = {**DEFAULT_BRAND, **(record["brand"] or {})}
    return {
        "display_name": brand.get("display_name") or record["name"],
        "primary_color": brand.get("primary_color") or DEFAULT_BRAND["primary_color"],
        "accent_color": brand.get("accent_color") or DEFAULT_BRAND["accent_color"],
        "support_email": brand.get("support_email"),
    }


async def _public_token(session: AsyncSession, token: str) -> tuple[uuid.UUID, uuid.UUID]:
    row = await session.execute(
        text(
            "SELECT tenant_id, entity_id FROM public_links"
            " WHERE token = :t AND kind = 'review' AND revoked_at IS NULL"
        ),
        {"t": token},
    )
    record = row.mappings().one_or_none()
    if record is None:
        raise HTTPException(
            status_code=404, detail="This link is invalid or has expired"
        )
    return record["tenant_id"], record["entity_id"]


# --- staff -----------------------------------------------------------------


async def _queue_review_sms(
    session: AsyncSession,
    ctx: AuthContext,
    order: ServiceOrder,
    request_id: uuid.UUID,
    url_path: str,
) -> None:
    if not order.customer_id:
        return
    customer = await session.get(Customer, order.customer_id)
    if not customer or not customer.phone:
        return
    shop = (await _workspace(session, ctx.tenant_id))["display_name"]
    base = get_settings().public_app_url
    review_url = f"{base.rstrip('/')}{url_path}" if base else url_path
    body = notifications.render(
        "review_request",
        name=customer.name.split(" ")[0],
        shop=shop,
        url=review_url,
    )
    await notifications.queue_notification(
        session,
        tenant_id=ctx.tenant_id,
        channel="sms",
        recipient=customer.phone,
        template="review_request",
        body=body,
        entity_type="review_request",
        entity_id=request_id,
    )


@router.post(
    "/service-orders/{order_id}/review-request",
    response_model=ReviewRequestOut,
    status_code=201,
)
async def create_review_request(
    order_id: uuid.UUID,
    ctx: AuthContext = Depends(require_feature("review_requests")),
    session: AsyncSession = Depends(get_db),
) -> ReviewRequestOut:
    ctx.require_rank(*STAFF_ROLES)
    order = await session.get(ServiceOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Service order not found")
    if order.status not in ("completed", "invoiced"):
        raise HTTPException(
            status_code=409,
            detail="Review requests are only available for completed orders",
        )
    existing = await session.scalar(
        select(ReviewRequest).where(ReviewRequest.order_id == order_id)
    )
    if existing is not None:
        link = await sharing.create_link(
            session, ctx.tenant_id, "review", existing.id
        )
        await _queue_review_sms(session, ctx, order, existing.id, link.url_path)
        out = ReviewRequestOut.model_validate(existing)
        out.url_path = link.url_path
        out.order_number = order.number
        return out

    request_row = ReviewRequest(
        tenant_id=ctx.tenant_id,
        order_id=order_id,
        customer_id=order.customer_id,
        status="pending",
    )
    session.add(request_row)
    await session.flush()

    link = await sharing.create_link(session, ctx.tenant_id, "review", request_row.id)
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="review.requested",
        entity="review_request",
        entity_id=request_row.id,
        meta={"order": order.number},
    )

    await _queue_review_sms(session, ctx, order, request_row.id, link.url_path)

    out = ReviewRequestOut.model_validate(request_row)
    out.url_path = link.url_path
    out.order_number = order.number
    return out


@router.get("/service-orders/{order_id}/review-request", response_model=ReviewRequestOut | None)
async def get_review_request(
    order_id: uuid.UUID,
    ctx: AuthContext = Depends(require_feature("review_requests")),
    session: AsyncSession = Depends(get_db),
) -> ReviewRequestOut | None:
    row = await session.scalar(
        select(ReviewRequest).where(ReviewRequest.order_id == order_id)
    )
    if row is None:
        return None
    order = await session.get(ServiceOrder, order_id)
    out = ReviewRequestOut.model_validate(row)
    out.order_number = order.number if order else None
    return out


# --- public ----------------------------------------------------------------


@router.get("/public/reviews/{token}", response_model=PublicReviewOut)
async def public_review(
    token: str, request: Request, session: AsyncSession = Depends(get_db)
) -> PublicReviewOut:
    ip = request.client.host if request.client else "unknown"
    allowed, retry_after = await limiter.hit(f"rl:pub:review:{ip}", 60, 60)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests, try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )
    tenant_id, request_id = await _public_token(session, token)
    await set_rls_context(session, tenant_id)
    row = await session.get(ReviewRequest, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Review request not found")
    order = await session.get(ServiceOrder, row.order_id)
    settings_row = await session.get(TenantSettings, tenant_id)
    return PublicReviewOut(
        workspace=await _workspace(session, tenant_id),
        order_number=order.number if order else "",
        status=row.status,
        rating=row.rating,
        comment=row.comment,
        submitted_at=row.submitted_at,
        review_url=settings_row.review_url if settings_row else None,
    )


@router.post("/public/reviews/{token}", response_model=PublicReviewOut)
async def submit_review(
    token: str,
    payload: ReviewSubmitIn,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> PublicReviewOut:
    ip = request.client.host if request.client else "unknown"
    allowed, retry_after = await limiter.hit(f"rl:pub:review:{ip}", 20, 60)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests, try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )
    tenant_id, request_id = await _public_token(session, token)
    await set_rls_context(session, tenant_id)
    row = await session.get(ReviewRequest, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Review request not found")
    if row.status == "submitted":
        raise HTTPException(status_code=409, detail="This review was already submitted")

    row.status = "submitted"
    row.rating = payload.rating
    row.comment = payload.comment
    row.submitted_at = datetime.now(timezone.utc)
    await session.flush()

    await audit.record(
        session,
        tenant_id=tenant_id,
        user_id=None,
        action="review.submitted",
        entity="review_request",
        entity_id=row.id,
        meta={"rating": payload.rating, "via": "public_link"},
    )

    order = await session.get(ServiceOrder, row.order_id)
    settings_row = await session.get(TenantSettings, tenant_id)
    return PublicReviewOut(
        workspace=await _workspace(session, tenant_id),
        order_number=order.number if order else "",
        status=row.status,
        rating=row.rating,
        comment=row.comment,
        submitted_at=row.submitted_at,
        review_url=settings_row.review_url if settings_row else None,
    )
