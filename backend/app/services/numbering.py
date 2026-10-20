from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def next_number(
    session: AsyncSession, tenant_id: uuid.UUID, kind: str, prefix: str
) -> str:
    """Atomic per-tenant sequence (race-safe under concurrent inserts).

    Runs inside the request transaction with RLS context already set, so the
    counter row belongs to the caller's tenant and `WITH CHECK` passes.
    """
    row = await session.execute(
        text(
            """
            INSERT INTO counters (tenant_id, kind, value)
            VALUES (:tenant_id, :kind, 1)
            ON CONFLICT (tenant_id, kind)
            DO UPDATE SET value = counters.value + 1
            RETURNING value
            """
        ),
        {"tenant_id": tenant_id, "kind": kind},
    )
    value = row.scalar_one()
    return f"{prefix}-{value:05d}"
