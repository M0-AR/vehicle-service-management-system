from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_roles
from app.core.security import hash_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import UserCreate, UserOut, UserUpdate
from app.schemas.common import Ok, Page
from app.services import audit, entitlements

router = APIRouter(prefix="/staff", tags=["staff"])


async def _get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Team member not found")
    return user


@router.get("", response_model=Page[UserOut])
async def list_staff(
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: AuthContext = Depends(require_roles("owner", "admin", "manager")),
    session: AsyncSession = Depends(get_db),
) -> Page[UserOut]:
    base = select(User)
    if q:
        pattern = f"%{q.strip()}%"
        base = base.where(or_(User.name.ilike(pattern), User.email.ilike(pattern)))
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = await session.scalars(
        base.order_by(User.created_at.asc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page[UserOut](
        items=[UserOut.model_validate(u) for u in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=UserOut, status_code=201)
async def create_staff(
    payload: UserCreate,
    ctx: AuthContext = Depends(require_roles("owner", "admin")),
    session: AsyncSession = Depends(get_db),
) -> UserOut:
    try:
        role = payload.validated_role()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if role == "owner" and ctx.role != "owner":
        raise HTTPException(status_code=403, detail="Only an owner can add another owner")

    await entitlements.check_limit(session, ctx.plan, "users", "users")

    user = User(
        tenant_id=ctx.tenant_id,
        email=payload.email.lower(),
        name=payload.name,
        password_hash=hash_password(payload.password),
        role=role,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A team member with this email already exists",
        )
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="staff.created",
        entity="user",
        entity_id=user.id,
        meta={"email": user.email, "role": user.role},
    )
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut)
async def update_staff(
    user_id: uuid.UUID,
    payload: UserUpdate,
    ctx: AuthContext = Depends(require_roles("owner", "admin")),
    session: AsyncSession = Depends(get_db),
) -> UserOut:
    user = await _get_user(session, user_id)
    if user.role == "owner" and ctx.role != "owner":
        raise HTTPException(status_code=403, detail="Only an owner can manage owners")

    data = payload.model_dump(exclude_unset=True)
    if "role" in data and data["role"] not in ("admin", "manager", "mechanic", "viewer"):
        raise HTTPException(status_code=422, detail="Invalid role")
    if "password" in data:
        user.password_hash = hash_password(data.pop("password"))
    for key, value in data.items():
        setattr(user, key, value)
    await session.flush()

    if payload.is_active is False:
        await session.execute(
            text(
                "UPDATE refresh_tokens SET revoked_at = now()"
                " WHERE user_id = :u AND revoked_at IS NULL"
            ),
            {"u": user_id},
        )
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="staff.updated",
        entity="user",
        entity_id=user.id,
        meta={"fields": sorted(data.keys())},
    )
    return UserOut.model_validate(user)


@router.delete("/{user_id}", response_model=Ok)
async def delete_staff(
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(require_roles("owner", "admin")),
    session: AsyncSession = Depends(get_db),
) -> Ok:
    user = await _get_user(session, user_id)
    if user.role == "owner":
        raise HTTPException(
            status_code=409, detail="The workspace owner cannot be removed"
        )
    if user.id == ctx.user_id:
        raise HTTPException(status_code=409, detail="You cannot remove yourself")
    await session.delete(user)
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="staff.deleted",
        entity="user",
        entity_id=user_id,
        meta={"email": user.email},
    )
    return Ok(detail="Team member removed")
