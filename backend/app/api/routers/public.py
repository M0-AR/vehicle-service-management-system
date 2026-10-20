"""Unauthenticated endpoints: branding, signup, TLS ask, plans, share links.

These are the only routes that read tenant data without a JWT — they expose
public routing/branding data only, and still run under RLS context set for the
resolved tenant. Share-link endpoints resolve the tenant from the token itself
(registry table, no RLS) and then set the same RLS context as any other
tenant-scoped request.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.tenancy import (
    resolve_tenant_id,
    set_rls_context,
    slug_available,
    validate_slug,
)
from app.db.session import get_db
from app.models.estimate import Estimate, EstimateItem
from app.models.inspection import Inspection, InspectionItem
from app.models.service import ServiceItem, ServiceOrder
from app.models.tenant import DEFAULT_BRAND
from app.models.vehicle import Vehicle
from app.schemas.auth import TokenPair, UserOut
from app.schemas.billing import PlanOut
from app.schemas.public import (
    EstimateRespondIn,
    PublicInspectionItem,
    PublicEstimateItem,
    PublicEstimateOut,
    PublicOrderItem,
    PublicOrderOut,
    PublicWorkspace,
)
from app.schemas.tenant import BrandingOut, SignupRequest, SignupResponse, SlugCheck
from app.services import audit, provisioning, tls
from app.services.entitlements import get_effective
from app.services.numbering import next_number

settings = get_settings()
router = APIRouter(tags=["public"])


async def _tenant_from_request(request: Request, session: AsyncSession):
    tenant_id = await resolve_tenant_id(
        session,
        slug=getattr(request.state, "tenant_slug", None),
        domain=getattr(request.state, "host_domain", None),
    )
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unknown workspace"
        )
    await set_rls_context(session, tenant_id)
    return tenant_id


async def _rate_limit(request: Request, bucket: str) -> None:
    ip = request.client.host if request.client else "unknown"
    allowed, retry_after = await limiter.hit(f"rl:pub:{bucket}:{ip}", 60, 60)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests, try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )


async def _load_workspace(
    session: AsyncSession, tenant_id: uuid.UUID
) -> PublicWorkspace:
    row = await session.execute(
        text(
            """
            SELECT t.slug, t.name, s.brand, s.currency
            FROM tenants t
            LEFT JOIN tenant_settings s ON s.tenant_id = t.id
            WHERE t.id = :t
            """
        ),
        {"t": tenant_id},
    )
    record = row.mappings().one()
    brand = {**DEFAULT_BRAND, **(record["brand"] or {})}
    return PublicWorkspace(
        display_name=brand.get("display_name") or record["name"],
        primary_color=brand.get("primary_color") or DEFAULT_BRAND["primary_color"],
        accent_color=brand.get("accent_color") or DEFAULT_BRAND["accent_color"],
        currency=record["currency"] or "USD",
        support_email=brand.get("support_email"),
    )


async def _resolve_link(
    session: AsyncSession, token: str, kind: str
) -> tuple[uuid.UUID, uuid.UUID]:
    row = await session.execute(
        text(
            "SELECT tenant_id, entity_id FROM public_links"
            " WHERE token = :t AND kind = :k AND revoked_at IS NULL"
        ),
        {"t": token, "k": kind},
    )
    record = row.mappings().one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This link is invalid or has expired",
        )
    return record["tenant_id"], record["entity_id"]


@router.get("/public/plans", response_model=list[PlanOut])
async def plans(session: AsyncSession = Depends(get_db)) -> list[PlanOut]:
    """Pricing catalog (registry table, tenant-independent)."""
    rows = await session.execute(
        text(
            "SELECT id, name, price_monthly_usd, features, limits FROM plans"
            " WHERE active = true ORDER BY price_monthly_usd, id"
        )
    )
    return [PlanOut(**dict(r)) for r in rows.mappings()]


@router.get("/public/branding", response_model=BrandingOut)
async def branding(
    request: Request, session: AsyncSession = Depends(get_db)
) -> BrandingOut:
    tenant_id = await _tenant_from_request(request, session)
    row = await session.execute(
        text(
            """
            SELECT t.slug, t.name, s.brand, s.currency, s.locale
            FROM tenants t
            LEFT JOIN tenant_settings s ON s.tenant_id = t.id
            WHERE t.id = :t
            """
        ),
        {"t": tenant_id},
    )
    record = row.mappings().one()
    brand = {**DEFAULT_BRAND, **(record["brand"] or {})}
    return BrandingOut(
        slug=record["slug"],
        display_name=brand.get("display_name") or record["name"],
        primary_color=brand.get("primary_color") or DEFAULT_BRAND["primary_color"],
        accent_color=brand.get("accent_color") or DEFAULT_BRAND["accent_color"],
        logo_url=brand.get("logo_url"),
        support_email=brand.get("support_email"),
        currency=record["currency"] or "USD",
        locale=record["locale"] or "en",
    )


@router.get("/public/orders/{token}", response_model=PublicOrderOut)
async def public_order(
    token: str, request: Request, session: AsyncSession = Depends(get_db)
) -> PublicOrderOut:
    """Customer status page payload for a shared service order."""
    await _rate_limit(request, "order")
    tenant_id, order_id = await _resolve_link(session, token, "order")
    await set_rls_context(session, tenant_id)

    order = await session.get(ServiceOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    vehicle = await session.get(Vehicle, order.vehicle_id)
    rows = await session.scalars(
        select(ServiceItem)
        .where(ServiceItem.order_id == order_id)
        .order_by(ServiceItem.created_at)
    )
    inspection = await session.scalar(
        select(Inspection).where(Inspection.order_id == order_id)
    )
    inspection_items: list[PublicInspectionItem] = []
    if inspection is not None:
        rows = await session.scalars(
            select(InspectionItem)
            .where(InspectionItem.inspection_id == inspection.id)
            .order_by(InspectionItem.sort_order, InspectionItem.created_at)
        )
        inspection_items = [
            PublicInspectionItem(
                label=i.label,
                status=i.status,
                note=i.note,
                photos=[
                    f"/api/v1/public/orders/{token}/photos/{p['path']}"
                    for p in (i.photos or [])
                ],
            )
            for i in rows
        ]

    return PublicOrderOut(
        workspace=await _load_workspace(session, tenant_id),
        number=order.number,
        status=order.status,
        description=order.description,
        vehicle={
            "plate_number": vehicle.plate_number if vehicle else None,
            "make": vehicle.make if vehicle else None,
            "model": vehicle.model if vehicle else None,
            "year": vehicle.year if vehicle else None,
        },
        scheduled_at=order.scheduled_at,
        completed_at=order.completed_at,
        updated_at=order.updated_at,
        items=[
            PublicOrderItem(kind=i.kind, description=i.description) for i in rows
        ],
        inspection=inspection_items,
        inspection_completed=bool(inspection and inspection.status == "completed"),
    )


async def _public_estimate_payload(
    session: AsyncSession, tenant_id: uuid.UUID, estimate_id: uuid.UUID
) -> PublicEstimateOut:
    estimate = await session.get(Estimate, estimate_id)
    if estimate is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    vehicle = await session.get(Vehicle, estimate.vehicle_id)
    rows = list(
        await session.scalars(
            select(EstimateItem)
            .where(EstimateItem.estimate_id == estimate_id)
            .order_by(EstimateItem.created_at)
        )
    )
    labor = sum(
        (Decimal(i.quantity) * Decimal(i.unit_price) for i in rows if i.kind == "labor"),
        Decimal("0"),
    )
    parts = sum(
        (Decimal(i.quantity) * Decimal(i.unit_price) for i in rows if i.kind == "part"),
        Decimal("0"),
    )
    order_number = None
    if estimate.converted_order_id:
        order_number = await session.scalar(
            select(ServiceOrder.number).where(
                ServiceOrder.id == estimate.converted_order_id
            )
        )
    return PublicEstimateOut(
        workspace=await _load_workspace(session, tenant_id),
        number=estimate.number,
        status=estimate.status,
        description=estimate.description,
        vehicle={
            "plate_number": vehicle.plate_number if vehicle else None,
            "make": vehicle.make if vehicle else None,
            "model": vehicle.model if vehicle else None,
            "year": vehicle.year if vehicle else None,
        },
        items=[
            PublicEstimateItem(
                kind=i.kind,
                description=i.description,
                quantity=i.quantity,
                unit_price=i.unit_price,
                total=Decimal(i.quantity) * Decimal(i.unit_price),
            )
            for i in rows
        ],
        totals={"labor": str(labor), "parts": str(parts), "total": str(labor + parts)},
        sent_at=estimate.sent_at,
        responded_at=estimate.responded_at,
        responded_by_name=estimate.responded_by_name,
        converted_order_number=order_number,
    )


@router.get("/public/orders/{token}/photos/{photo_path:path}")
async def public_order_photo(
    token: str,
    photo_path: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Token-scoped DVI photo access for the shared status page."""
    from fastapi.responses import FileResponse

    from app.services import photos

    await _rate_limit(request, "photo")
    tenant_id, order_id = await _resolve_link(session, token, "order")
    await set_rls_context(session, tenant_id)
    inspection = await session.scalar(
        select(Inspection).where(Inspection.order_id == order_id)
    )
    if inspection is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    # Only paths listed on an item of this inspection are served.
    items = await session.scalars(
        select(InspectionItem).where(InspectionItem.inspection_id == inspection.id)
    )
    allowed = any(
        entry.get("path") == photo_path
        for item in items
        for entry in (item.photos or [])
    )
    if not allowed:
        raise HTTPException(status_code=404, detail="Photo not found")
    target = photos.resolve_path(tenant_id, photo_path)
    media_type = {
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(target.suffix.lower(), "application/octet-stream")
    return FileResponse(
        target,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/public/estimates/{token}", response_model=PublicEstimateOut)
async def public_estimate(
    token: str, request: Request, session: AsyncSession = Depends(get_db)
) -> PublicEstimateOut:
    await _rate_limit(request, "estimate")
    tenant_id, estimate_id = await _resolve_link(session, token, "estimate")
    await set_rls_context(session, tenant_id)
    estimate = await session.get(Estimate, estimate_id)
    if estimate is None or estimate.status == "draft":
        raise HTTPException(status_code=404, detail="Estimate not found")
    return await _public_estimate_payload(session, tenant_id, estimate_id)


@router.post("/public/estimates/{token}/respond", response_model=PublicEstimateOut)
async def respond_to_estimate(
    token: str,
    payload: EstimateRespondIn,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> PublicEstimateOut:
    """Customer approves or declines the estimate. Approval creates the order."""
    await _rate_limit(request, "estimate")
    tenant_id, estimate_id = await _resolve_link(session, token, "estimate")
    await set_rls_context(session, tenant_id)

    now = datetime.now(timezone.utc)
    new_status = "approved" if payload.decision == "approve" else "declined"
    claimed = await session.execute(
        text(
            """
            UPDATE estimates
            SET status = :status, responded_at = :now,
                responded_by_name = :name, updated_at = :now
            WHERE id = :e AND status = 'sent'
            RETURNING number, vehicle_id, customer_id, description
            """
        ),
        {
            "status": new_status,
            "now": now,
            "name": payload.name,
            "e": estimate_id,
        },
    )
    record = claimed.mappings().one_or_none()
    if record is None:
        raise HTTPException(
            status_code=409, detail="This estimate has already been answered"
        )

    if new_status == "approved":
        order_number = await next_number(
            session, tenant_id, "service_order", "SO"
        )
        order = ServiceOrder(
            tenant_id=tenant_id,
            number=order_number,
            vehicle_id=record["vehicle_id"],
            customer_id=record["customer_id"],
            status="scheduled",
            description=record["description"],
            notes=f"Approved from estimate {record['number']}"
            + (f" by {payload.name}" if payload.name else ""),
        )
        session.add(order)
        await session.flush()

        item_rows = await session.scalars(
            select(EstimateItem)
            .where(EstimateItem.estimate_id == estimate_id)
            .order_by(EstimateItem.created_at)
        )
        for item in item_rows:
            session.add(
                ServiceItem(
                    tenant_id=tenant_id,
                    order_id=order.id,
                    kind=item.kind,
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                )
            )
        await session.execute(
            text("UPDATE estimates SET converted_order_id = :o WHERE id = :e"),
            {"o": order.id, "e": estimate_id},
        )
        await session.flush()

        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=None,
            action="estimate.approved",
            entity="estimate",
            entity_id=estimate_id,
            meta={
                "number": record["number"],
                "name": payload.name,
                "order_number": order_number,
                "via": "public_link",
            },
        )
        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=None,
            action="order.created",
            entity="service_order",
            entity_id=order.id,
            meta={"number": order_number, "from_estimate": record["number"]},
        )
    else:
        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=None,
            action="estimate.declined",
            entity="estimate",
            entity_id=estimate_id,
            meta={"number": record["number"], "name": payload.name, "via": "public_link"},
        )

    return await _public_estimate_payload(session, tenant_id, estimate_id)


@router.get("/public/signup/check", response_model=SlugCheck)
async def signup_check(
    slug: str, session: AsyncSession = Depends(get_db)
) -> SlugCheck:
    normalized = slug.strip().lower()
    error = validate_slug(normalized)
    if error:
        return SlugCheck(slug=normalized, available=False, message=error)
    available = await slug_available(session, normalized)
    return SlugCheck(
        slug=normalized,
        available=available,
        message=None if available else "This subdomain is already taken",
    )


@router.post("/public/signup", response_model=SignupResponse, status_code=201)
async def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> SignupResponse:
    if not settings.signup_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-serve signup is disabled on this instance.",
        )
    ip = request.client.host if request.client else "unknown"
    allowed, retry_after = await limiter.hit(
        f"rl:signup:{ip}", settings.login_rate_per_minute, 3600
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many signup attempts, try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    tenant, owner = await provisioning.provision_tenant(
        session,
        name=payload.name,
        slug=payload.slug,
        email=payload.email,
        password=payload.password,
        business_name=payload.business_name,
    )

    from app.api.routers.auth import issue_session, set_refresh_cookie

    pair, raw_refresh = await issue_session(session, tenant, owner)
    set_refresh_cookie(response, raw_refresh)

    scheme = "http" if settings.env == "dev" else "https"
    base = settings.platform_base_domain
    return SignupResponse(
        tenant_id=str(tenant.id),
        slug=tenant.slug,
        url=f"{scheme}://{tenant.slug}.{base}",
        access_token=pair.access_token,
        expires_in=pair.expires_in,
    )


@router.get("/tls/ask", response_class=PlainTextResponse)
async def tls_ask(domain: str, session: AsyncSession = Depends(get_db)) -> PlainTextResponse:
    allowed = await tls.is_hostname_allowed(session, domain)
    if allowed:
        return PlainTextResponse("allow", status_code=200)
    return PlainTextResponse("deny", status_code=403)
