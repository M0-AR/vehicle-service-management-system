"""Custom domain lifecycle: add -> DNS TXT verification -> Caddy on-demand TLS.

DNS proof-of-control is a `_vsms-verify.<domain>` TXT record containing the
tenant-unique token (same mechanism as verified production multi-tenant CRMs);
certificates are only requested after verification (see tls.ask).
"""

from __future__ import annotations

import re
import secrets
import uuid

import dns.asyncresolver
import dns.exception
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services import audit

settings = get_settings()

HOSTNAME_RE = re.compile(
    r"^(?=.{4,255}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$"
)
TXT_PREFIX = "_vsms-verify"


def _validate_hostname(domain: str) -> None:
    if not HOSTNAME_RE.match(domain):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter a valid hostname, e.g. service.my-garage.com",
        )
    base = settings.platform_base_domain.lower()
    if base and (domain == base or domain.endswith("." + base)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"*.{base} subdomains are assigned automatically",
        )


def txt_record_name(domain: str) -> str:
    return f"{TXT_PREFIX}.{domain}"


async def add_domain(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, domain: str
) -> dict:
    _validate_hostname(domain)
    existing = await session.execute(
        text("SELECT tenant_id, status FROM tenant_domains WHERE domain = :d"),
        {"d": domain},
    )
    row = existing.mappings().one_or_none()
    if row and str(row["tenant_id"]) != str(tenant_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This domain is already registered to another workspace",
        )
    token = secrets.token_hex(16) if not row else None
    if not row:
        await session.execute(
            text(
                """
                INSERT INTO tenant_domains (domain, tenant_id, status, verification_token)
                VALUES (:d, :t, 'pending', :tok)
                """
            ),
            {"d": domain, "t": tenant_id, "tok": token},
        )
        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="domain.added",
            entity="tenant_domain",
            entity_id=domain,
        )
    result = await session.execute(
        text(
            "SELECT domain, status, verification_token, created_at, verified_at"
            " FROM tenant_domains WHERE domain = :d"
        ),
        {"d": domain},
    )
    return _row_to_out(result.mappings().one())


async def list_domains(session: AsyncSession, tenant_id: uuid.UUID) -> list[dict]:
    result = await session.execute(
        text(
            "SELECT domain, status, verification_token, created_at, verified_at"
            " FROM tenant_domains WHERE tenant_id = :t ORDER BY created_at"
        ),
        {"t": tenant_id},
    )
    return [_row_to_out(r) for r in result.mappings().all()]


async def verify_domain(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, domain: str
) -> dict:
    result = await session.execute(
        text(
            "SELECT domain, status, verification_token, created_at, verified_at"
            " FROM tenant_domains WHERE domain = :d AND tenant_id = :t"
        ),
        {"d": domain, "t": tenant_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    if row["status"] == "verified":
        return _row_to_out(row)

    try:
        answers = await dns.asyncresolver.resolve(txt_record_name(domain), "TXT")
        values = [b"".join(rdata.strings).decode("utf-8", "ignore") for rdata in answers]
    except (dns.exception.DNSException, Exception):  # noqa: BLE001
        values = []

    if row["verification_token"] not in values:
        return _row_to_out(row) | {
            "message": (
                f"TXT record not found yet. Create a TXT record for"
                f" {txt_record_name(domain)} with value {row['verification_token']},"
                f" then try again (DNS can take a few minutes)."
            )
        }

    await session.execute(
        text(
            "UPDATE tenant_domains SET status = 'verified', verified_at = now()"
            " WHERE domain = :d"
        ),
        {"d": domain},
    )
    await audit.record(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        action="domain.verified",
        entity="tenant_domain",
        entity_id=domain,
    )
    result = await session.execute(
        text(
            "SELECT domain, status, verification_token, created_at, verified_at"
            " FROM tenant_domains WHERE domain = :d"
        ),
        {"d": domain},
    )
    return _row_to_out(result.mappings().one())


async def remove_domain(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, domain: str
) -> None:
    result = await session.execute(
        text("DELETE FROM tenant_domains WHERE domain = :d AND tenant_id = :t"),
        {"d": domain, "t": tenant_id},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Domain not found")
    await audit.record(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        action="domain.removed",
        entity="tenant_domain",
        entity_id=domain,
    )


def _row_to_out(row) -> dict:
    return {
        "domain": row["domain"],
        "status": row["status"],
        "verification_token": row["verification_token"],
        "txt_record": txt_record_name(row["domain"]),
        "created_at": str(row["created_at"]) if row["created_at"] else None,
        "verified_at": str(row["verified_at"]) if row["verified_at"] else None,
    }
