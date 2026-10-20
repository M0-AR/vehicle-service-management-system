"""Public online booking endpoints.

The booking page is tenant-resolved (subdomain / X-Tenant-Slug / domain) and
entitlement-gated by `online_booking`. Submission is rate-limited, honeypot
checked, and converts directly into a scheduled service order plus a customer
and vehicle when they do not exist yet.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.tenancy import resolve_tenant_id, set_rls_context
from app.db.session import get_db
from app.models.booking import BookingRequest
from app.models.customer import Customer
from app.models.service import ServiceOrder
from app.models.tenant import DEFAULT_BRAND, TenantSettings
from app.models.vehicle import Vehicle
from app.schemas.features import (
    BookingRequestIn,
    PublicBookingOut,
    PublicBookingResult,
)
from app.services import audit, booking as booking_service, notifications, push
from app.services.entitlements import get_effective
from app.services.numbering import next_number

settings = get_settings()
router = APIRouter(prefix="/public/booking", tags=["public"])


async def _tenant(request: Request, session: AsyncSession) -> uuid.UUID:
    tenant_id = await resolve_tenant_id(
        session,
        slug=getattr(request.state, "tenant_slug", None),
        domain=getattr(request.state, "host_domain", None),
    )
    if tenant_id is None:
        raise HTTPException(status_code=404, detail="Unknown workspace")
    await set_rls_context(session, tenant_id)
    return tenant_id


async def _workspace(session: AsyncSession, tenant_id: uuid.UUID) -> dict:
    row = await session.execute(
        text(
            """
            SELECT t.name, s.brand, s.currency, s.timezone
              FROM tenants t
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
        "currency": record["currency"] or "USD",
        "support_email": brand.get("support_email"),
    }


async def _public_entitlement(session: AsyncSession, tenant_id: uuid.UUID) -> dict:
    tenant = await session.execute(
        text("SELECT plan FROM tenants WHERE id = :t"), {"t": tenant_id}
    )
    plan_id = tenant.scalar_one()
    return await get_effective(session, tenant_id, plan_id)


async def _rate_limit(request: Request, bucket: str, limit: int = 60) -> None:
    ip = request.client.host if request.client else "unknown"
    allowed, retry_after = await limiter.hit(f"rl:pub:{bucket}:{ip}", limit, 60)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests, try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )


async def _settings(session: AsyncSession, tenant_id: uuid.UUID) -> TenantSettings | None:
    return await session.get(TenantSettings, tenant_id)


@router.get("/{slug}", response_model=PublicBookingOut)
async def booking_page(
    slug: str, request: Request, session: AsyncSession = Depends(get_db)
) -> PublicBookingOut:
    await _rate_limit(request, "booking")
    tenant_id = await resolve_tenant_id(session, slug=slug)
    if tenant_id is None:
        raise HTTPException(status_code=404, detail="Unknown workspace")
    await set_rls_context(session, tenant_id)
    plan = await _public_entitlement(session, tenant_id)
    if not plan["features"].get("online_booking"):
        raise HTTPException(
            status_code=402,
            detail="Online booking is not enabled for this workshop.",
        )
    row = await _settings(session, tenant_id)
    enabled = bool(row and row.booking_enabled)
    if not enabled:
        raise HTTPException(
            status_code=404, detail="Online booking is not available for this workshop"
        )
    slots = await booking_service.available_slots(
        session,
        tenant_id,
        timezone_name=row.timezone if row else "UTC",
        business_hours=row.business_hours if row else None,
    )
    return PublicBookingOut(
        workspace=await _workspace(session, tenant_id),
        booking_enabled=enabled,
        timezone=row.timezone if row else "UTC",
        slots=[
            {
                "start": s["start"],
                "label": s["label"],
                "available": s["available"],
            }
            for s in slots
        ],
        review_url=row.review_url if row else None,
    )


@router.post("/{slug}", response_model=PublicBookingResult, status_code=201)
async def submit_booking(
    slug: str,
    payload: BookingRequestIn,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> PublicBookingResult:
    await _rate_limit(request, "booking_submit", limit=10)
    if payload.company:
        # Honeypot: pretend success, create nothing.
        raise HTTPException(status_code=201, detail="Booking received")

    tenant_id = await resolve_tenant_id(session, slug=slug)
    if tenant_id is None:
        raise HTTPException(status_code=404, detail="Unknown workspace")
    await set_rls_context(session, tenant_id)

    plan = await _public_entitlement(session, tenant_id)
    if not plan["features"].get("online_booking"):
        raise HTTPException(
            status_code=402,
            detail="Online booking is not enabled for this workshop.",
        )
    row = await _settings(session, tenant_id)
    if row is None or not row.booking_enabled:
        raise HTTPException(
            status_code=404, detail="Online booking is not available for this workshop"
        )

    slot = booking_service.parse_slot(payload.preferred_at, row.timezone)
    if slot < datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Choose a time in the future")
    if not await booking_service.slot_is_available(session, tenant_id, slot):
        raise HTTPException(
            status_code=409, detail="That time slot is no longer available"
        )

    # Find or create the customer (email first, then phone).
    customer = None
    if payload.email:
        customer = await session.scalar(
            select(Customer).where(Customer.email == payload.email)
        )
    if customer is None:
        customer = await session.scalar(
            select(Customer).where(Customer.phone == payload.phone)
        )
    if customer is None:
        customer = Customer(
            tenant_id=tenant_id,
            name=payload.name,
            email=payload.email,
            phone=payload.phone,
        )
        session.add(customer)
        await session.flush()

    plate = payload.plate_number.strip().upper()
    vehicle = await session.scalar(
        select(Vehicle).where(Vehicle.plate_number == plate)
    )
    if vehicle is None:
        vehicle = Vehicle(
            tenant_id=tenant_id,
            customer_id=customer.id,
            plate_number=plate,
            make=payload.make or "Unknown",
            model=payload.model or "Unknown",
            year=payload.year,
        )
        session.add(vehicle)
        await session.flush()
    elif vehicle.customer_id is None:
        vehicle.customer_id = customer.id

    number = await next_number(session, tenant_id, "service_order", "SO")
    order = ServiceOrder(
        tenant_id=tenant_id,
        number=number,
        vehicle_id=vehicle.id,
        customer_id=customer.id,
        status="scheduled",
        description=payload.service_description,
        scheduled_at=slot,
        notes=f"Online booking by {payload.name} ({payload.phone})",
    )
    session.add(order)
    await session.flush()

    session.add(
        BookingRequest(
            tenant_id=tenant_id,
            name=payload.name,
            email=payload.email,
            phone=payload.phone,
            plate_number=plate,
            make=payload.make,
            model=payload.model,
            year=payload.year,
            service_description=payload.service_description,
            preferred_at=slot,
            status="converted",
            order_id=order.id,
        )
    )
    await session.flush()

    await audit.record(
        session,
        tenant_id=tenant_id,
        user_id=None,
        action="booking.created",
        entity="service_order",
        entity_id=order.id,
        meta={"number": number, "name": payload.name, "via": "public_booking"},
    )

    vehicle_label = " ".join(part for part in [payload.make, payload.model] if part) or plate
    await push.notify_staff(
        session,
        tenant_id=tenant_id,
        roles=("owner", "admin", "manager"),
        title="New booking request",
        body=f"{payload.name} · {vehicle_label} · {number}",
        url=f"/app/orders/{order.id}",
    )

    shop = (await _workspace(session, tenant_id))["display_name"]
    if payload.phone:
        body = notifications.render(
            "booking_received",
            name=payload.name.split(" ")[0],
            when=booking_service.slot_label(
                slot.astimezone(booking_service._zone(row.timezone))
            ),
            shop=shop,
        )
        await notifications.queue_notification(
            session,
            tenant_id=tenant_id,
            channel="sms",
            recipient=payload.phone,
            template="booking_received",
            body=body,
            entity_type="service_order",
            entity_id=order.id,
        )

    return PublicBookingResult(
        number=number,
        scheduled_at=slot,
        message=(
            f"Thanks {payload.name.split(' ')[0]}! Your request is booked for "
            f"{slot.astimezone(booking_service._zone(row.timezone)).strftime('%a %d %b')}"
            f", {slot.astimezone(booking_service._zone(row.timezone)).strftime('%I:%M %p').lstrip('0')}."
            " We will confirm by phone if anything changes."
        ),
    )
