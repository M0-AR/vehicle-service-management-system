"""Self-serve tenant provisioning.

Runs as the app role. Registry tables (tenants/tenant_domains/billing_accounts)
are RLS-free; the very first write into an RLS table (the owner user) happens
after `set_rls_context` switches the transaction to the new tenant — verifying
the RLS path on the happy path, not just in tests.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.config import get_settings
from app.core.security import hash_password
from app.core.tenancy import random_suffix, set_rls_context, slug_available, slugify, validate_slug
from app.models.location import Location
from app.models.tenant import DEFAULT_BRAND, Tenant, TenantKey, TenantSettings
from app.models.user import User
from app.services import audit

settings = get_settings()


async def generate_slug(session: AsyncSession, name: str) -> str:
    base = slugify(name) or "garage"
    if len(base) < 3:
        base = base + random_suffix(2)
    candidate = base[:34]
    if validate_slug(candidate) is None and await slug_available(session, candidate):
        return candidate
    for _ in range(10):
        candidate = f"{base[:33]}-{random_suffix(3)}"
        if validate_slug(candidate) is None and await slug_available(session, candidate):
            return candidate
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Could not allocate a subdomain, please choose one manually",
    )


async def provision_tenant(
    session: AsyncSession,
    *,
    name: str,
    slug: str,
    email: str,
    password: str,
    business_name: str | None = None,
) -> tuple[Tenant, User]:
    slug = slug.strip().lower()
    error = validate_slug(slug)
    if error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error)
    if not await slug_available(session, slug):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This subdomain is already taken",
        )

    encryption_mode = "platform"
    dek_b64: str | None = None
    if settings.master_kek_b64:
        try:
            dek_b64 = crypto.generate_dek()
            crypto.wrap_dek(dek_b64)  # fail fast if the master key is unusable
            encryption_mode = "envelope"
        except ValueError:
            dek_b64 = None

    tenant = Tenant(
        name=name,
        slug=slug,
        plan="free",
        region=settings.default_region,
        isolation_tier="pool",
        encryption_mode=encryption_mode,
    )
    session.add(tenant)
    await session.flush()  # tenant.id

    session.add(
        TenantSettings(
            tenant_id=tenant.id,
            brand={**DEFAULT_BRAND, "display_name": business_name or name},
        )
    )
    if dek_b64:
        session.add(
            TenantKey(tenant_id=tenant.id, dek_wrapped=crypto.wrap_dek(dek_b64))
        )

    await session.execute(
        text(
            """
            INSERT INTO billing_accounts (tenant_id, provider, plan, status)
            VALUES (:t, :p, 'free', 'active')
            ON CONFLICT (tenant_id) DO NOTHING
            """
        ),
        {"t": tenant.id, "p": settings.billing_provider},
    )

    await set_rls_context(session, tenant.id)

    session.add(Location(tenant_id=tenant.id, name="Main location", is_default=True))

    owner = User(
        tenant_id=tenant.id,
        email=email.lower(),
        name=name,
        password_hash=hash_password(password),
        role="owner",
    )
    session.add(owner)
    await session.flush()

    await audit.record(
        session,
        tenant_id=tenant.id,
        user_id=owner.id,
        action="tenant.created",
        entity="tenant",
        entity_id=tenant.id,
        meta={"slug": slug, "plan": "free"},
    )
    return tenant, owner
