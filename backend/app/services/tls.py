"""On-demand TLS policy for Caddy (`/api/v1/tls/ask`).

Caddy asks us before requesting a certificate for a hostname. We answer only
for hostnames that demonstrably belong to a tenant — this prevents drive-by
certificate issuance against our server (verified pattern, docs/RESEARCH.md).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

settings = get_settings()


async def is_hostname_allowed(session: AsyncSession, hostname: str) -> bool:
    host = hostname.strip().lower().split(":")[0].rstrip(".")
    if not host:
        return False

    base = settings.platform_base_domain.lower()
    if base and host.endswith("." + base):
        slug = host[: -(len(base) + 1)].split(".")[0]
        row = await session.execute(
            text("SELECT 1 FROM tenants WHERE slug = :s AND status = 'active'"),
            {"s": slug},
        )
        return row.scalar_one_or_none() is not None

    if host in ("localhost", "127.0.0.1"):
        return settings.env == "dev"

    row = await session.execute(
        text("SELECT 1 FROM tenant_domains WHERE domain = :d AND status = 'verified'"),
        {"d": host},
    )
    return row.scalar_one_or_none() is not None
