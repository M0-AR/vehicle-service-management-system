from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, require_feature, require_roles
from app.core.config import get_settings
from app.core.security import new_api_key
from app.core.tenancy import set_rls_context
from app.db.session import get_db
from app.models.tenant import DEFAULT_BRAND, Tenant, TenantSettings
from app.models.user import ApiKey
from app.schemas.audit import ApiKeyCreated, ApiKeyIn, ApiKeyOut
from app.schemas.billing import BillingStatusOut, CheckoutRequest, CheckoutResponse, PlanOut
from app.schemas.common import Ok
from app.schemas.tenant import BrandingUpdate, DomainCreate, DomainOut, TenantProfileOut
from app.services import audit, domains
from app.services.billing import apply as billing_apply
from app.services.billing.registry import get_provider

settings = get_settings()
router = APIRouter(prefix="/settings", tags=["settings"])


async def _settings_row(session: AsyncSession, tenant_id: uuid.UUID) -> TenantSettings:
    row = await session.get(TenantSettings, tenant_id)
    if row is None:
        row = TenantSettings(tenant_id=tenant_id)
        session.add(row)
        await session.flush()
    return row


@router.get("/profile", response_model=TenantProfileOut)
async def get_profile(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> TenantProfileOut:
    return TenantProfileOut(**ctx.tenant)


@router.patch("/profile", response_model=Ok)
async def update_profile(
    payload: dict,
    ctx: AuthContext = Depends(require_roles("owner", "admin")),
    session: AsyncSession = Depends(get_db),
) -> Ok:
    tenant = await session.get(Tenant, ctx.tenant_id)
    row = await _settings_row(session, ctx.tenant_id)
    changed: list[str] = []

    if name := payload.get("name"):
        tenant.name = str(name)[:120]
        changed.append("name")
    if currency := payload.get("currency"):
        row.currency = str(currency)[:3].upper()
        changed.append("currency")
    if timezone := payload.get("timezone"):
        row.timezone = str(timezone)[:64]
        changed.append("timezone")
    if locale := payload.get("locale"):
        row.locale = str(locale)[:10]
        changed.append("locale")
    if "booking_enabled" in payload:
        row.booking_enabled = bool(payload["booking_enabled"])
        changed.append("booking_enabled")
    if "business_hours" in payload:
        hours = payload["business_hours"]
        if not isinstance(hours, dict):
            raise HTTPException(status_code=422, detail="business_hours must be an object")
        allowed_days = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
        cleaned: dict = {}
        for day, ranges in hours.items():
            if day not in allowed_days:
                continue
            if not isinstance(ranges, list):
                raise HTTPException(
                    status_code=422, detail=f"business_hours.{day} must be a list"
                )
            cleaned[day] = ranges
        row.business_hours = cleaned
        changed.append("business_hours")
    if "review_url" in payload:
        url = payload["review_url"]
        row.review_url = str(url)[:500] if url else None
        changed.append("review_url")

    if "tax_rate" in payload:
        try:
            rate = float(payload["tax_rate"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="tax_rate must be a number 0..1")
        if not 0 <= rate <= 1:
            raise HTTPException(status_code=422, detail="tax_rate must be between 0 and 1")
        row.tax_rate = rate
        changed.append("tax_rate")

    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="settings.profile_updated",
        entity="tenant_settings",
        entity_id=ctx.tenant_id,
        meta={"fields": changed},
    )
    return Ok(detail=f"Updated: {', '.join(changed) or 'nothing'}")


@router.get("/operations")
async def get_operations(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> dict:
    row = await _settings_row(session, ctx.tenant_id)
    return {
        "booking_enabled": row.booking_enabled,
        "business_hours": row.business_hours or {},
        "review_url": row.review_url,
        "timezone": row.timezone,
    }


@router.get("/branding")
async def get_branding(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> dict:
    row = await _settings_row(session, ctx.tenant_id)
    return {
        "brand": {**DEFAULT_BRAND, **(row.brand or {})},
        "white_label": bool(ctx.plan["features"].get("white_label", False)),
        "currency": row.currency,
        "locale": row.locale,
    }


@router.patch("/branding")
async def update_branding(
    payload: BrandingUpdate,
    ctx: AuthContext = Depends(require_roles("owner", "admin")),
    session: AsyncSession = Depends(get_db),
) -> dict:
    from app.services.entitlements import has_feature

    data = payload.model_dump(exclude_unset=True)
    gated = {"primary_color", "accent_color", "logo_url", "support_email"} & set(data)
    if gated and not has_feature(ctx.plan, "white_label"):
        raise HTTPException(
            status_code=402,
            detail="Custom colors and logo are a Pro feature. Please upgrade.",
        )

    row = await _settings_row(session, ctx.tenant_id)
    if "tax_rate" in data:
        row.tax_rate = data.pop("tax_rate")
    if "currency" in data:
        row.currency = data.pop("currency").upper()
    if "locale" in data:
        row.locale = data.pop("locale")
    if "timezone" in data:
        row.timezone = data.pop("timezone")

    brand = {**DEFAULT_BRAND, **(row.brand or {})}
    for key, value in data.items():
        brand[key] = value
    row.brand = brand
    await session.flush()

    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="settings.branding_updated",
        entity="tenant_settings",
        entity_id=ctx.tenant_id,
        meta={"fields": sorted(data.keys())},
    )
    return {"brand": brand, "ok": True}


# --- custom domains (Pro) ----------------------------------------------------


@router.get("/domains", response_model=list[DomainOut])
async def list_domains(
    ctx: AuthContext = Depends(require_feature("custom_domain")),
    session: AsyncSession = Depends(get_db),
) -> list[DomainOut]:
    return [DomainOut(**d) for d in await domains.list_domains(session, ctx.tenant_id)]


@router.post("/domains", response_model=DomainOut, status_code=201)
async def add_domain(
    payload: DomainCreate,
    ctx: AuthContext = Depends(require_feature("custom_domain")),
    session: AsyncSession = Depends(get_db),
) -> DomainOut:
    out = await domains.add_domain(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id or uuid.uuid4(),
        domain=payload.domain,
    )
    return DomainOut(**out)


@router.post("/domains/{domain}/verify", response_model=DomainOut)
async def verify_domain(
    domain: str,
    ctx: AuthContext = Depends(require_feature("custom_domain")),
    session: AsyncSession = Depends(get_db),
) -> DomainOut:
    out = await domains.verify_domain(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id or uuid.uuid4(),
        domain=domain.strip().lower(),
    )
    return DomainOut(**{k: out.get(k) for k in DomainOut.model_fields})


@router.delete("/domains/{domain}", response_model=Ok)
async def delete_domain(
    domain: str,
    ctx: AuthContext = Depends(require_feature("custom_domain")),
    session: AsyncSession = Depends(get_db),
) -> Ok:
    await domains.remove_domain(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id or uuid.uuid4(),
        domain=domain.strip().lower(),
    )
    return Ok(detail="Domain removed")


# --- API keys (Pro) ----------------------------------------------------------


@router.get("/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(
    ctx: AuthContext = Depends(require_feature("api_access")),
    session: AsyncSession = Depends(get_db),
) -> list[ApiKeyOut]:
    rows = await session.scalars(
        select(ApiKey).where(ApiKey.revoked_at.is_(None)).order_by(ApiKey.created_at)
    )
    return [ApiKeyOut.model_validate(k) for k in rows]


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    payload: ApiKeyIn,
    ctx: AuthContext = Depends(require_feature("api_access")),
    session: AsyncSession = Depends(get_db),
) -> ApiKeyCreated:
    ctx.require_rank("owner", "admin")
    raw, key_hash = new_api_key()
    record = ApiKey(tenant_id=ctx.tenant_id, name=payload.name[:120], key_hash=key_hash)
    session.add(record)
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="apikey.created",
        entity="api_key",
        entity_id=record.id,
        meta={"name": record.name},
    )
    return ApiKeyCreated(id=record.id, name=record.name, key=raw)


@router.delete("/api-keys/{key_id}", response_model=Ok)
async def revoke_api_key(
    key_id: uuid.UUID,
    ctx: AuthContext = Depends(require_feature("api_access")),
    session: AsyncSession = Depends(get_db),
) -> Ok:
    ctx.require_rank("owner", "admin")
    record = await session.get(ApiKey, key_id)
    if record is None:
        raise HTTPException(status_code=404, detail="API key not found")
    record.revoked_at = datetime.now(timezone.utc)
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="apikey.revoked",
        entity="api_key",
        entity_id=key_id,
        meta={"name": record.name},
    )
    return Ok(detail="API key revoked")


# --- plans & billing ---------------------------------------------------------


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> list[PlanOut]:
    rows = await session.execute(
        text(
            "SELECT id, name, price_monthly_usd, features, limits"
            " FROM plans WHERE active ORDER BY price_monthly_usd"
        )
    )
    return [
        PlanOut(
            id=r["id"],
            name=r["name"],
            price_monthly_usd=float(r["price_monthly_usd"]),
            features=r["features"],
            limits=r["limits"],
        )
        for r in rows.mappings()
    ]


@router.get("/billing", response_model=BillingStatusOut)
async def billing_status(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> BillingStatusOut:
    row = await session.execute(
        text(
            "SELECT provider, plan, status, currency, current_period_end"
            " FROM billing_accounts WHERE tenant_id = :t"
        ),
        {"t": ctx.tenant_id},
    )
    account = row.mappings().one_or_none()
    provider = get_provider()
    return BillingStatusOut(
        plan=account["plan"] if account else ctx.tenant["plan"],
        status=account["status"] if account else "active",
        provider=account["provider"] if account else provider.name,
        currency=account["currency"] if account else "USD",
        current_period_end=str(account["current_period_end"])
        if account and account["current_period_end"]
        else None,
        checkout_available=provider.name != "stub",
        portal_available=False,
    )


@router.post("/billing/checkout", response_model=CheckoutResponse)
async def billing_checkout(
    payload: CheckoutRequest,
    ctx: AuthContext = Depends(require_roles("owner", "admin")),
    session: AsyncSession = Depends(get_db),
) -> CheckoutResponse:
    plan_row = await session.execute(
        text("SELECT id FROM plans WHERE id = :p AND active"), {"p": payload.plan}
    )
    if plan_row.scalar_one_or_none() is None:
        raise HTTPException(status_code=422, detail="Unknown plan")
    if payload.plan == "free":
        raise HTTPException(
            status_code=422,
            detail="To downgrade to Free, cancel your subscription in the billing portal.",
        )

    provider = get_provider()
    url, message = await provider.create_checkout(
        tenant_id=ctx.tenant_id,
        plan=payload.plan,
        currency="USD",
        success_url=payload.success_url,
        cancel_url=payload.cancel_url,
    )

    if provider.name == "stub":
        # Dev/demo: apply immediately so the upgrade flow is testable keyless.
        await billing_apply.apply_plan_change(
            session, tenant_id=ctx.tenant_id, plan=payload.plan, status="active"
        )
        await audit.record(
            session,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            action="billing.plan_changed_stub",
            entity="billing_account",
            entity_id=ctx.tenant_id,
            meta={"plan": payload.plan},
        )

    return CheckoutResponse(url=url, message=message)


# --- CSV export --------------------------------------------------------------


EXPORTS = {
    "vehicles": (
        "SELECT plate_number, make, model, year, fuel_type, mileage, status, created_at"
        " FROM vehicles ORDER BY created_at"
    ),
    "customers": (
        "SELECT name, email, phone, address, created_at FROM customers ORDER BY created_at"
    ),
    "orders": (
        "SELECT number, status, priority, description, estimated_cost, created_at"
        " FROM service_orders ORDER BY created_at"
    ),
    "invoices": (
        "SELECT number, status, subtotal, tax_amount, total, currency, issued_at,"
        " due_at, paid_at FROM invoices ORDER BY created_at"
    ),
}


@router.get("/export/{resource}")
async def export_csv(
    resource: str,
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager")),
    session: AsyncSession = Depends(get_db),
) -> Response:
    sql = EXPORTS.get(resource)
    if sql is None:
        raise HTTPException(status_code=404, detail=f"Unknown export '{resource}'")
    result = await session.execute(text(sql))
    rows = result.mappings().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    if rows:
        writer.writerow(rows[0].keys())
        for row in rows:
            writer.writerow(list(row.values()))
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{resource}.csv"'},
    )
