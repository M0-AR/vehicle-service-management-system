from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_feature
from app.db.session import get_db
from app.models.accounting import (
    DEFAULT_ACCOUNTS,
    AccountingConnection,
    AccountingSyncRun,
)
from app.schemas.accounting import (
    AccountingCallbackIn,
    AccountingConnectOut,
    AccountingConnectionOut,
    AccountingMappingIn,
    AccountingRunOut,
    AccountingStatus,
    AccountingSyncIn,
)
from app.schemas.common import Page
from app.services import accounting, audit

router = APIRouter(prefix="/accounting", tags=["accounting"])

READ_ROLES = ("owner", "admin", "manager")
WRITE_ROLES = ("owner", "admin")


def _connection_out(conn: AccountingConnection) -> AccountingConnectionOut:
    return AccountingConnectionOut(
        provider=conn.provider,
        status=conn.status,
        external_tenant_id=conn.external_tenant_id,
        accounts=accounting.accounts_for(conn),
        last_synced_at=conn.last_synced_at,
    )


async def _get_connection(
    session: AsyncSession, tenant_id: uuid.UUID
) -> AccountingConnection | None:
    return await session.scalar(
        select(AccountingConnection).where(
            AccountingConnection.tenant_id == tenant_id
        )
    )


async def _status(
    session: AsyncSession, tenant_id: uuid.UUID
) -> AccountingStatus:
    conn = await _get_connection(session, tenant_id)
    last = await session.scalar(
        select(AccountingSyncRun)
        .where(AccountingSyncRun.tenant_id == tenant_id)
        .order_by(AccountingSyncRun.created_at.desc())
        .limit(1)
    )
    pending = await accounting.pending_invoices(
        session, tenant_id, conn.id if conn else None
    )
    provider = accounting.provider_name()
    return AccountingStatus(
        provider=provider,
        configured=accounting.provider_configured(provider),
        connection=_connection_out(conn) if conn else None,
        pending_invoices=pending,
        last_run=AccountingRunOut.model_validate(last) if last else None,
    )


@router.get("", response_model=AccountingStatus)
async def status(
    ctx: AuthContext = Depends(require_feature("accounting_sync")),
    session: AsyncSession = Depends(get_db),
) -> AccountingStatus:
    ctx.require_rank(*READ_ROLES)
    return await _status(session, ctx.tenant_id)


@router.post("/connect", response_model=AccountingConnectOut)
async def connect(
    ctx: AuthContext = Depends(require_feature("accounting_sync")),
    session: AsyncSession = Depends(get_db),
) -> AccountingConnectOut:
    ctx.require_rank(*WRITE_ROLES)
    provider = accounting.provider_name()
    try:
        accounting.require_configured(provider)
    except accounting.AccountingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if provider != "stub":
        return AccountingConnectOut(
            connected=False,
            authorize_url=accounting.authorize_url(ctx.tenant_id),
            message="Redirecting to the provider to authorise access.",
        )

    conn = await _get_connection(session, ctx.tenant_id)
    if conn is None:
        conn = AccountingConnection(
            tenant_id=ctx.tenant_id,
            provider="stub",
            settings={"accounts": dict(DEFAULT_ACCOUNTS)},
        )
        session.add(conn)
    conn.provider = "stub"
    conn.status = "connected"
    conn.external_tenant_id = f"stub-{str(ctx.tenant_id)[:8]}"
    conn.access_token_enc = None
    conn.refresh_token_enc = None
    conn.token_expires_at = None
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="accounting.connected",
        entity="accounting_connection",
        entity_id=conn.id,
        meta={"provider": conn.provider},
    )
    return AccountingConnectOut(
        connected=True,
        message="Demo accounting connected. Paid invoices can now be synced.",
    )


@router.post("/callback", response_model=AccountingStatus)
async def callback(
    payload: AccountingCallbackIn,
    ctx: AuthContext = Depends(require_feature("accounting_sync")),
    session: AsyncSession = Depends(get_db),
) -> AccountingStatus:
    ctx.require_rank(*WRITE_ROLES)
    try:
        tenant_id, provider = accounting.read_oauth_state(payload.state)
    except accounting.AccountingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if tenant_id != ctx.tenant_id:
        raise HTTPException(
            status_code=409, detail="This connection link belongs to another workspace."
        )
    try:
        bundle = await accounting.exchange_code(
            provider, payload.code, payload.realm_id
        )
    except accounting.AccountingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not bundle.external_tenant_id:
        raise HTTPException(
            status_code=502,
            detail="The provider did not return a company id. Reconnect and try again.",
        )

    conn = await _get_connection(session, ctx.tenant_id)
    if conn is None:
        conn = AccountingConnection(
            tenant_id=ctx.tenant_id,
            provider=provider,
            settings={"accounts": dict(DEFAULT_ACCOUNTS)},
        )
        session.add(conn)
    conn.provider = provider
    conn.status = "connected"
    conn.external_tenant_id = bundle.external_tenant_id
    conn.access_token_enc = accounting.crypto.encrypt_secret(bundle.access_token)
    conn.refresh_token_enc = (
        accounting.crypto.encrypt_secret(bundle.refresh_token)
        if bundle.refresh_token
        else None
    )
    conn.token_expires_at = bundle.expires_at
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="accounting.connected",
        entity="accounting_connection",
        entity_id=conn.id,
        meta={"provider": provider},
    )
    return await _status(session, ctx.tenant_id)


@router.patch("/connection", response_model=AccountingStatus)
async def update_mapping(
    payload: AccountingMappingIn,
    ctx: AuthContext = Depends(require_feature("accounting_sync")),
    session: AsyncSession = Depends(get_db),
) -> AccountingStatus:
    ctx.require_rank(*WRITE_ROLES)
    conn = await _get_connection(session, ctx.tenant_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="No accounting connection")
    conn.settings = {
        **(conn.settings or {}),
        "accounts": {
            "payment": payload.payment.strip(),
            "income": payload.income.strip(),
            "tax": payload.tax.strip(),
        },
    }
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="accounting.mapping_updated",
        entity="accounting_connection",
        entity_id=conn.id,
        meta={"accounts": conn.settings["accounts"]},
    )
    return await _status(session, ctx.tenant_id)


@router.delete("/connection", status_code=204)
async def disconnect(
    ctx: AuthContext = Depends(require_feature("accounting_sync")),
    session: AsyncSession = Depends(get_db),
) -> Response:
    ctx.require_rank(*WRITE_ROLES)
    conn = await _get_connection(session, ctx.tenant_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="No accounting connection")
    conn_id = conn.id
    provider = conn.provider
    await session.delete(conn)
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="accounting.disconnected",
        entity="accounting_connection",
        entity_id=conn_id,
        meta={"provider": provider},
    )
    return Response(status_code=204)


@router.post("/sync", response_model=AccountingRunOut, status_code=201)
async def sync(
    payload: AccountingSyncIn,
    ctx: AuthContext = Depends(require_feature("accounting_sync")),
    session: AsyncSession = Depends(get_db),
) -> AccountingRunOut:
    ctx.require_rank(*WRITE_ROLES)
    try:
        run = await accounting.run_sync(
            session,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            start=payload.period_start,
            end=payload.period_end,
        )
    except accounting.AccountingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="accounting.synced" if run.status == "succeeded" else "accounting.sync_failed",
        entity="accounting_sync_run",
        entity_id=run.id,
        meta={
            "provider": run.provider,
            "invoices": run.invoices_count,
            "period_start": str(run.period_start),
            "period_end": str(run.period_end),
            "detail": run.detail,
        },
    )
    return AccountingRunOut.model_validate(run)


@router.get("/runs", response_model=Page[AccountingRunOut])
async def runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ctx: AuthContext = Depends(require_feature("accounting_sync")),
    session: AsyncSession = Depends(get_db),
) -> Page[AccountingRunOut]:
    ctx.require_rank(*READ_ROLES)
    total = await session.scalar(
        select(func.count())
        .select_from(AccountingSyncRun)
        .where(AccountingSyncRun.tenant_id == ctx.tenant_id)
    )
    rows = (
        await session.scalars(
            select(AccountingSyncRun)
            .where(AccountingSyncRun.tenant_id == ctx.tenant_id)
            .order_by(AccountingSyncRun.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return Page[AccountingRunOut](
        items=[AccountingRunOut.model_validate(row) for row in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.get("/export")
async def export(
    period_start: date = Query(alias="period_start"),
    period_end: date = Query(alias="period_end"),
    ctx: AuthContext = Depends(require_feature("accounting_sync")),
    session: AsyncSession = Depends(get_db),
) -> Response:
    ctx.require_rank(*READ_ROLES)
    if period_end < period_start:
        raise HTTPException(
            status_code=422, detail="The end date must be on or after the start date."
        )
    conn = await _get_connection(session, ctx.tenant_id)
    accounts = (
        accounting.accounts_for(conn) if conn else dict(DEFAULT_ACCOUNTS)
    )
    invoices = await accounting.paid_invoices(
        session, ctx.tenant_id, period_start, period_end, None
    )
    entries = [accounting.build_entry(invoice, accounts) for invoice in invoices]
    body = accounting.journal_csv(entries)
    return Response(
        content=body,
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="accounting-journal-{period_start}-{period_end}.csv"'
            )
        },
    )
