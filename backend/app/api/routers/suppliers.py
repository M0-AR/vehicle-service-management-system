from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_feature
from app.db.session import get_db
from app.models.supplier import SupplierCatalogItem, SupplierConnection
from app.schemas.supplier import (
    CatalogImportResult,
    OfferImportIn,
    OfferImportOut,
    OfferOut,
    SupplierIn,
    SupplierOut,
)
from app.services import audit, suppliers

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

WRITE_ROLES = ("owner", "admin")


async def _get_connection(
    session: AsyncSession, connection_id: uuid.UUID
) -> SupplierConnection:
    connection = await session.get(SupplierConnection, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return connection


@router.get("", response_model=list[SupplierOut])
async def list_suppliers(
    ctx: AuthContext = Depends(require_feature("suppliers")),
    session: AsyncSession = Depends(get_db),
) -> list[SupplierOut]:
    connections = (
        await session.scalars(
            select(SupplierConnection).order_by(SupplierConnection.name)
        )
    ).all()
    counts = dict(
        (
            await session.execute(
                select(
                    SupplierCatalogItem.connection_id,
                    func.count(SupplierCatalogItem.id),
                ).group_by(SupplierCatalogItem.connection_id)
            )
        ).all()
    )
    return [
        SupplierOut(
            id=connection.id,
            name=connection.name,
            provider=connection.provider,
            portal_url=connection.portal_url,
            catalog_size=int(counts.get(connection.id, 0)),
            created_at=connection.created_at,
        )
        for connection in connections
    ]


@router.post("", response_model=SupplierOut, status_code=201)
async def create_supplier(
    payload: SupplierIn,
    ctx: AuthContext = Depends(require_feature("suppliers")),
    session: AsyncSession = Depends(get_db),
) -> SupplierOut:
    ctx.require_rank(*WRITE_ROLES)
    connection = SupplierConnection(
        tenant_id=ctx.tenant_id,
        name=payload.name.strip(),
        provider=payload.provider,
        portal_url=payload.portal_url,
    )
    session.add(connection)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        if "uq_supplier_connections_tenant_name" in str(exc.orig):
            raise HTTPException(
                status_code=409, detail="A supplier with that name already exists"
            ) from exc
        raise
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="supplier.created",
        entity="supplier_connection",
        entity_id=str(connection.id),
        meta={"name": connection.name, "provider": connection.provider},
    )
    await session.commit()
    return SupplierOut(
        id=connection.id,
        name=connection.name,
        provider=connection.provider,
        portal_url=connection.portal_url,
        catalog_size=0,
        created_at=connection.created_at,
    )


@router.delete("/{connection_id}")
async def delete_supplier(
    connection_id: uuid.UUID,
    ctx: AuthContext = Depends(require_feature("suppliers")),
    session: AsyncSession = Depends(get_db),
):
    ctx.require_rank(*WRITE_ROLES)
    connection = await _get_connection(session, connection_id)
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="supplier.deleted",
        entity="supplier_connection",
        entity_id=str(connection.id),
        meta={"name": connection.name},
    )
    await session.delete(connection)
    await session.commit()
    return {"ok": True}


@router.post("/{connection_id}/catalog", response_model=CatalogImportResult)
async def import_catalog(
    connection_id: uuid.UUID,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_feature("suppliers")),
    session: AsyncSession = Depends(get_db),
) -> CatalogImportResult:
    ctx.require_rank(*WRITE_ROLES)
    connection = await _get_connection(session, connection_id)
    if connection.provider != "csv":
        raise HTTPException(
            status_code=400,
            detail="Only CSV suppliers accept a catalog upload",
        )
    raw = await file.read(suppliers.MAX_CATALOG_BYTES + 1)
    if len(raw) > suppliers.MAX_CATALOG_BYTES:
        raise HTTPException(status_code=413, detail="CSV exceeds the 2 MB limit")
    try:
        rows, skipped = suppliers.parse_catalog_csv(raw)
    except suppliers.CatalogCsvError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not rows:
        raise HTTPException(
            status_code=400, detail="CSV contains no valid catalog rows"
        )
    result = await suppliers.import_catalog(session, connection, rows)
    result.skipped = skipped
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="supplier.catalog_imported",
        entity="supplier_connection",
        entity_id=str(connection.id),
        meta={
            "imported": result.imported,
            "updated": result.updated,
            "skipped": result.skipped,
        },
    )
    await session.commit()
    return result


@router.get("/search", response_model=list[OfferOut])
async def search_offers(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    ctx: AuthContext = Depends(require_feature("suppliers")),
    session: AsyncSession = Depends(get_db),
) -> list[OfferOut]:
    connections = (
        await session.scalars(
            select(SupplierConnection).order_by(SupplierConnection.name)
        )
    ).all()
    return await suppliers.search(session, list(connections), q, limit)


@router.post("/import", response_model=OfferImportOut)
async def import_offer(
    payload: OfferImportIn,
    ctx: AuthContext = Depends(require_feature("suppliers")),
    session: AsyncSession = Depends(get_db),
) -> OfferImportOut:
    connection = await _get_connection(session, payload.connection_id)
    offer = await suppliers.resolve_offer(session, connection, payload.sku)
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    part, created = await suppliers.import_offer(session, connection, offer)
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="supplier.part_imported",
        entity="part",
        entity_id=str(part.id),
        meta={
            "supplier": connection.name,
            "sku": offer.sku,
            "created": created,
        },
    )
    await session.commit()
    return OfferImportOut(part_id=part.id, created=created)
