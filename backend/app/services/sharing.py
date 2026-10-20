"""Public share links (status pages, estimate approvals).

Registry-table based: a link row maps an unguessable token to
(tenant_id, kind, entity_id). Creating a link rotates any previous active link
for the same entity, so "send again" always invalidates the old URL.
"""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.public import ShareOut

PATH_PREFIX = {"order": "status", "estimate": "estimate", "review": "review"}


async def create_link(
    session: AsyncSession, tenant_id: uuid.UUID, kind: str, entity_id: uuid.UUID
) -> ShareOut:
    token = secrets.token_urlsafe(24)
    await session.execute(
        text(
            "UPDATE public_links SET revoked_at = now()"
            " WHERE kind = :kind AND entity_id = :entity AND revoked_at IS NULL"
        ),
        {"kind": kind, "entity": entity_id},
    )
    await session.execute(
        text(
            """
            INSERT INTO public_links (token, tenant_id, kind, entity_id)
            VALUES (:token, :tenant_id, :kind, :entity)
            """
        ),
        {
            "token": token,
            "tenant_id": tenant_id,
            "kind": kind,
            "entity": entity_id,
        },
    )
    return ShareOut(
        token=token, url_path=f"/{PATH_PREFIX[kind]}/{token}", kind=kind
    )


async def revoke_links(
    session: AsyncSession, kind: str, entity_id: uuid.UUID
) -> None:
    await session.execute(
        text(
            "UPDATE public_links SET revoked_at = now()"
            " WHERE kind = :kind AND entity_id = :entity AND revoked_at IS NULL"
        ),
        {"kind": kind, "entity": entity_id},
    )
