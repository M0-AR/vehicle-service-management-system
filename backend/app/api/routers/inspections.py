"""Digital vehicle inspections (DVI) with photo attachments.

Entitlement: `dvi`. Photos are validated by magic bytes, capped at
`UPLOAD_MAX_BYTES`, stored tenant-scoped on disk, and served through
authenticated endpoints only (the public status page exposes a summary).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, require_feature, require_roles
from app.db.session import get_db
from app.models.inspection import Inspection, InspectionItem
from app.models.service import ServiceOrder
from app.schemas.features import (
    InspectionCreate,
    InspectionItemIn,
    InspectionItemOut,
    InspectionItemUpdate,
    InspectionOut,
    InspectionUpdate,
)
from app.services import audit, photos

router = APIRouter(prefix="/inspections", tags=["inspections"])

EDIT_ROLES = ("owner", "admin", "manager", "mechanic")


async def _load(session: AsyncSession, inspection_id: uuid.UUID) -> Inspection:
    inspection = await session.get(Inspection, inspection_id)
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return inspection


async def _items(session: AsyncSession, inspection_id: uuid.UUID) -> list[InspectionItem]:
    rows = await session.scalars(
        select(InspectionItem)
        .where(InspectionItem.inspection_id == inspection_id)
        .order_by(InspectionItem.sort_order, InspectionItem.created_at)
    )
    return list(rows)


async def _serialize(session: AsyncSession, inspection: Inspection) -> InspectionOut:
    out = InspectionOut.model_validate(inspection)
    out.items = [InspectionItemOut.model_validate(i) for i in await _items(session, inspection.id)]
    return out


@router.get("/by-order/{order_id}", response_model=InspectionOut | None)
async def get_by_order(
    order_id: uuid.UUID,
    ctx: AuthContext = Depends(require_feature("dvi")),
    session: AsyncSession = Depends(get_db),
) -> InspectionOut | None:
    row = await session.scalar(
        select(Inspection).where(Inspection.order_id == order_id)
    )
    return await _serialize(session, row) if row else None


@router.post("/by-order/{order_id}", response_model=InspectionOut, status_code=201)
async def create_for_order(
    order_id: uuid.UUID,
    payload: InspectionCreate,
    ctx: AuthContext = Depends(require_feature("dvi")),
    session: AsyncSession = Depends(get_db),
) -> InspectionOut:
    ctx.require_rank(*EDIT_ROLES)
    order = await session.get(ServiceOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Service order not found")
    existing = await session.scalar(
        select(Inspection).where(Inspection.order_id == order_id)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="This order already has an inspection")

    inspection = Inspection(
        tenant_id=ctx.tenant_id, order_id=order_id, notes=payload.notes
    )
    session.add(inspection)
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="inspection.created",
        entity="inspection",
        entity_id=inspection.id,
        meta={"order": order.number},
    )
    return await _serialize(session, inspection)


@router.get("/{inspection_id}", response_model=InspectionOut)
async def get_inspection(
    inspection_id: uuid.UUID,
    ctx: AuthContext = Depends(require_feature("dvi")),
    session: AsyncSession = Depends(get_db),
) -> InspectionOut:
    return await _serialize(session, await _load(session, inspection_id))


@router.patch("/{inspection_id}", response_model=InspectionOut)
async def update_inspection(
    inspection_id: uuid.UUID,
    payload: InspectionUpdate,
    ctx: AuthContext = Depends(require_feature("dvi")),
    session: AsyncSession = Depends(get_db),
) -> InspectionOut:
    ctx.require_rank(*EDIT_ROLES)
    inspection = await _load(session, inspection_id)
    if inspection.status == "completed":
        raise HTTPException(status_code=409, detail="This inspection is completed")

    if payload.notes is not None:
        inspection.notes = payload.notes
    if payload.status is not None:
        if payload.status not in ("draft", "completed"):
            raise HTTPException(status_code=422, detail="status must be draft or completed")
        inspection.status = payload.status
        if payload.status == "completed":
            inspection.completed_at = datetime.now(timezone.utc)
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="inspection.updated",
        entity="inspection",
        entity_id=inspection.id,
        meta={"status": inspection.status},
    )
    return await _serialize(session, inspection)


@router.post("/{inspection_id}/items", response_model=InspectionOut, status_code=201)
async def add_item(
    inspection_id: uuid.UUID,
    payload: InspectionItemIn,
    ctx: AuthContext = Depends(require_feature("dvi")),
    session: AsyncSession = Depends(get_db),
) -> InspectionOut:
    ctx.require_rank(*EDIT_ROLES)
    inspection = await _load(session, inspection_id)
    if inspection.status == "completed":
        raise HTTPException(status_code=409, detail="This inspection is completed")
    try:
        status = payload.validated_status()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    session.add(
        InspectionItem(
            tenant_id=ctx.tenant_id,
            inspection_id=inspection_id,
            label=payload.label,
            status=status,
            note=payload.note,
            sort_order=payload.sort_order,
        )
    )
    await session.flush()
    return await _serialize(session, inspection)


async def _item(session: AsyncSession, inspection_id: uuid.UUID, item_id: uuid.UUID) -> InspectionItem:
    row = await session.get(InspectionItem, item_id)
    if row is None or row.inspection_id != inspection_id:
        raise HTTPException(status_code=404, detail="Inspection item not found")
    return row


@router.patch("/{inspection_id}/items/{item_id}", response_model=InspectionOut)
async def update_item(
    inspection_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: InspectionItemUpdate,
    ctx: AuthContext = Depends(require_feature("dvi")),
    session: AsyncSession = Depends(get_db),
) -> InspectionOut:
    ctx.require_rank(*EDIT_ROLES)
    inspection = await _load(session, inspection_id)
    if inspection.status == "completed":
        raise HTTPException(status_code=409, detail="This inspection is completed")
    item = await _item(session, inspection_id, item_id)

    if payload.label is not None:
        item.label = payload.label
    if payload.status is not None:
        from app.models.inspection import INSPECTION_ITEM_STATUSES

        if payload.status not in INSPECTION_ITEM_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"status must be one of {INSPECTION_ITEM_STATUSES}",
            )
        item.status = payload.status
    if payload.note is not None:
        item.note = payload.note
    if payload.sort_order is not None:
        item.sort_order = payload.sort_order
    await session.flush()
    return await _serialize(session, inspection)


@router.delete("/{inspection_id}/items/{item_id}", response_model=InspectionOut)
async def delete_item(
    inspection_id: uuid.UUID,
    item_id: uuid.UUID,
    ctx: AuthContext = Depends(require_feature("dvi")),
    session: AsyncSession = Depends(get_db),
) -> InspectionOut:
    ctx.require_rank(*EDIT_ROLES)
    inspection = await _load(session, inspection_id)
    if inspection.status == "completed":
        raise HTTPException(status_code=409, detail="This inspection is completed")
    item = await _item(session, inspection_id, item_id)
    for photo in item.photos or []:
        photos.delete_path(photo.get("path", ""))
    await session.delete(item)
    await session.flush()
    return await _serialize(session, inspection)


@router.post("/{inspection_id}/items/{item_id}/photos", response_model=InspectionOut)
async def upload_photo(
    inspection_id: uuid.UUID,
    item_id: uuid.UUID,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_feature("dvi")),
    session: AsyncSession = Depends(get_db),
) -> InspectionOut:
    ctx.require_rank(*EDIT_ROLES)
    inspection = await _load(session, inspection_id)
    if inspection.status == "completed":
        raise HTTPException(status_code=409, detail="This inspection is completed")
    item = await _item(session, inspection_id, item_id)

    metadata = await photos.save_photo(ctx.tenant_id, inspection_id, file)
    item.photos = [*(item.photos or []), metadata]
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="inspection.photo_added",
        entity="inspection_item",
        entity_id=item.id,
        meta={"size": metadata["size"], "mime": metadata["mime"]},
    )
    return await _serialize(session, inspection)


@router.get("/photos/{photo_path:path}")
async def get_photo(
    photo_path: str,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
):
    # Path is `<tenant>/<inspection>/<file>`; RLS + the tenant prefix both
    # constrain access. The file response is private (no public cache).
    target = photos.resolve_path(ctx.tenant_id, photo_path)
    media_type = {
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(target.suffix.lower(), "application/octet-stream")
    return FileResponse(
        target,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.delete("/{inspection_id}/items/{item_id}/photos/{index}", response_model=InspectionOut)
async def delete_photo(
    inspection_id: uuid.UUID,
    item_id: uuid.UUID,
    index: int,
    ctx: AuthContext = Depends(require_feature("dvi")),
    session: AsyncSession = Depends(get_db),
) -> InspectionOut:
    ctx.require_rank(*EDIT_ROLES)
    inspection = await _load(session, inspection_id)
    if inspection.status == "completed":
        raise HTTPException(status_code=409, detail="This inspection is completed")
    item = await _item(session, inspection_id, item_id)
    entries = list(item.photos or [])
    if index < 0 or index >= len(entries):
        raise HTTPException(status_code=404, detail="Photo not found")
    removed = entries.pop(index)
    photos.delete_path(removed.get("path", ""))
    item.photos = entries
    await session.flush()
    return await _serialize(session, inspection)
