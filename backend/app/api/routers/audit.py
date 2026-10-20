from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_feature, require_roles
from app.db.session import get_db
from app.schemas.audit import AuditOut
from app.schemas.common import Page

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=Page[AuditOut])
async def list_audit(
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    ctx: AuthContext = Depends(require_feature("audit_log")),
    session: AsyncSession = Depends(get_db),
) -> Page[AuditOut]:
    ctx.require_rank("owner", "admin")
    where = ""
    params: dict = {}
    if q:
        where = "WHERE (a.action ILIKE :q OR a.entity ILIKE :q)"
        params["q"] = f"%{q.strip()}%"

    total = await session.execute(
        text(f"SELECT count(*) FROM audit_logs a {where}"), params
    )
    rows = await session.execute(
        text(
            f"""
            SELECT a.id, a.user_id, a.action, a.entity, a.entity_id,
                   a.meta, a.ip, a.created_at, u.name AS user_name
            FROM audit_logs a
            LEFT JOIN users u ON u.id = a.user_id
            {where}
            ORDER BY a.created_at DESC
            OFFSET :offset LIMIT :limit
            """
        ),
        {**params, "offset": (page - 1) * page_size, "limit": page_size},
    )
    return Page[AuditOut](
        items=[AuditOut(**dict(r)) for r in rows.mappings()],
        total=int(total.scalar_one()),
        page=page,
        page_size=page_size,
    )
