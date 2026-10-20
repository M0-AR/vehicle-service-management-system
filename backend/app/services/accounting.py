"""Accounting sync: OAuth connections + journal posting.

One provider per deployment (`ACCOUNTING_PROVIDER`). The stub keeps local dev
and tests keyless; QuickBooks Online and Xero use the standard OAuth 2.0
authorization-code flow. Journals are built from paid invoices — debit the
payment/undeposited-funds account for the total, credit income for the net and
tax payable for the tax. Posting is idempotent per invoice via
`accounting_sync_items`, and the connection row is locked while a run is in
flight.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.config import get_settings
from app.models.accounting import (
    DEFAULT_ACCOUNTS,
    AccountingConnection,
    AccountingSyncItem,
    AccountingSyncRun,
)
from app.models.invoice import Invoice

settings = get_settings()

CENT = Decimal("0.01")
QBO_AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
QBO_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QBO_SCOPE = "com.intuit.quickbooks.accounting"
XERO_AUTH_URL = "https://login.xero.com/identity/connect/authorize"
XERO_TOKEN_URL = "https://identity.xero.com/connect/token"
XERO_CONNECTIONS_URL = "https://api.xero.com/connections"
XERO_API_BASE = "https://api.xero.com/api.xro/2.0"
XERO_SCOPE = "offline_access accounting.transactions"


class AccountingError(Exception):
    """Provider/config error surfaced as a 409/502 by the router."""


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    external_tenant_id: str | None = None


@dataclass
class JournalLine:
    account: str
    description: str
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")


@dataclass
class JournalEntry:
    number: str
    date: date
    currency: str
    description: str
    lines: list[JournalLine]


def provider_name() -> str:
    return settings.accounting_provider.strip().lower()


def redirect_uri(p: str) -> str:
    configured = (
        settings.quickbooks_redirect_uri
        if p == "quickbooks"
        else settings.xero_redirect_uri
    )
    if configured:
        return configured
    base = settings.public_app_url.rstrip("/") or "http://localhost:3100"
    return f"{base}/app/settings?tab=accounting"


def provider_configured(p: str | None = None) -> bool:
    p = p or provider_name()
    if p == "stub":
        return True
    if p == "quickbooks":
        return bool(settings.quickbooks_client_id and settings.quickbooks_client_secret)
    if p == "xero":
        return bool(settings.xero_client_id and settings.xero_client_secret)
    return False


def require_configured(p: str | None = None) -> None:
    p = p or provider_name()
    if p not in ("stub", "quickbooks", "xero"):
        raise AccountingError(f"Unknown accounting provider '{p}'")
    if not provider_configured(p):
        label = "QuickBooks" if p == "quickbooks" else "Xero"
        raise AccountingError(
            f"{label} is not configured on this server. Set the provider client id, "
            "secret and redirect URI, then reconnect."
        )


def accounts_for(conn: AccountingConnection) -> dict[str, str]:
    accounts = dict(DEFAULT_ACCOUNTS)
    stored = (conn.settings or {}).get("accounts") or {}
    for key in accounts:
        value = stored.get(key)
        if isinstance(value, str) and value.strip():
            accounts[key] = value.strip()
    return accounts


def create_oauth_state(tenant_id: uuid.UUID, p: str) -> str:
    payload = {
        "typ": "accounting_oauth",
        "tenant_id": str(tenant_id),
        "provider": p,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def read_oauth_state(state: str) -> tuple[uuid.UUID, str]:
    try:
        payload = jwt.decode(
            state, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.InvalidTokenError as exc:
        raise AccountingError("This connection link is invalid or expired.") from exc
    if payload.get("typ") != "accounting_oauth":
        raise AccountingError("This connection link is invalid or expired.")
    provider = payload.get("provider")
    if provider != provider_name():
        raise AccountingError("This connection link was issued for a different provider.")
    try:
        tenant_id = uuid.UUID(str(payload["tenant_id"]))
    except (KeyError, ValueError) as exc:
        raise AccountingError("This connection link is invalid or expired.") from exc
    return tenant_id, provider


def authorize_url(tenant_id: uuid.UUID) -> str:
    p = provider_name()
    require_configured(p)
    state = create_oauth_state(tenant_id, p)
    uri = redirect_uri(p)
    if p == "quickbooks":
        query = {
            "client_id": settings.quickbooks_client_id,
            "response_type": "code",
            "scope": QBO_SCOPE,
            "redirect_uri": uri,
            "state": state,
        }
        return f"{QBO_AUTH_URL}?{urlencode(query)}"
    query = {
        "client_id": settings.xero_client_id,
        "response_type": "code",
        "scope": XERO_SCOPE,
        "redirect_uri": uri,
        "state": state,
    }
    return f"{XERO_AUTH_URL}?{urlencode(query)}"


def _expiry(seconds: object) -> datetime:
    try:
        value = int(seconds)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        value = 3600
    return datetime.now(timezone.utc) + timedelta(seconds=max(60, value - 30))


async def _post_form(url: str, data: dict, auth: tuple[str, str]) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            url,
            data=data,
            auth=auth,
            headers={"Accept": "application/json"},
        )
    if response.status_code >= 400:
        raise AccountingError(
            f"Token endpoint error ({response.status_code}): {response.text[:300]}"
        )
    return response.json()


async def exchange_code(
    p: str, code: str, realm_id: str | None
) -> TokenBundle:
    require_configured(p)
    if p == "quickbooks":
        payload = await _post_form(
            QBO_TOKEN_URL,
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri(p),
            },
            (settings.quickbooks_client_id, settings.quickbooks_client_secret),
        )
        return TokenBundle(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_at=_expiry(payload.get("expires_in")),
            external_tenant_id=realm_id,
        )

    payload = await _post_form(
        XERO_TOKEN_URL,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(p),
        },
        (settings.xero_client_id, settings.xero_client_secret),
    )
    access = payload["access_token"]
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            XERO_CONNECTIONS_URL, headers={"Authorization": f"Bearer {access}"}
        )
    if response.status_code >= 400:
        raise AccountingError(
            f"Xero connections error ({response.status_code}): {response.text[:300]}"
        )
    connections = response.json()
    if not connections:
        raise AccountingError("No Xero organisation is connected to this login.")
    return TokenBundle(
        access_token=access,
        refresh_token=payload.get("refresh_token"),
        expires_at=_expiry(payload.get("expires_in")),
        external_tenant_id=connections[0].get("tenantId"),
    )


async def _refresh(p: str, refresh_token: str) -> TokenBundle:
    if p == "quickbooks":
        payload = await _post_form(
            QBO_TOKEN_URL,
            {"grant_type": "refresh_token", "refresh_token": refresh_token},
            (settings.quickbooks_client_id, settings.quickbooks_client_secret),
        )
    else:
        payload = await _post_form(
            XERO_TOKEN_URL,
            {"grant_type": "refresh_token", "refresh_token": refresh_token},
            (settings.xero_client_id, settings.xero_client_secret),
        )
    return TokenBundle(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token") or refresh_token,
        expires_at=_expiry(payload.get("expires_in")),
    )


async def ensure_access_token(conn: AccountingConnection) -> str | None:
    """Return a live access token, refreshing + persisting when needed."""
    if conn.provider == "stub":
        return None
    if not conn.access_token_enc:
        raise AccountingError("This accounting connection has no access token. Reconnect.")
    expires = conn.token_expires_at
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires > datetime.now(timezone.utc) + timedelta(seconds=60):
            return crypto.decrypt_secret(conn.access_token_enc)
    if not conn.refresh_token_enc:
        raise AccountingError("This accounting connection expired. Reconnect.")
    bundle = await _refresh(conn.provider, crypto.decrypt_secret(conn.refresh_token_enc))
    conn.access_token_enc = crypto.encrypt_secret(bundle.access_token)
    if bundle.refresh_token:
        conn.refresh_token_enc = crypto.encrypt_secret(bundle.refresh_token)
    conn.token_expires_at = bundle.expires_at
    return bundle.access_token


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def build_entry(invoice: Invoice, accounts: dict[str, str]) -> JournalEntry:
    total = _money(Decimal(invoice.total or 0))
    tax = _money(Decimal(invoice.tax_amount or 0))
    if tax < 0:
        tax = Decimal("0.00")
    income = _money(total - tax)
    paid_on = (
        invoice.paid_at.date()
        if invoice.paid_at
        else (invoice.issued_at.date() if invoice.issued_at else date.today())
    )
    description = f"Invoice {invoice.number}"
    lines = [
        JournalLine(
            account=accounts["payment"],
            description=f"{description} — payment",
            debit=total,
        )
    ]
    if income != 0:
        lines.append(
            JournalLine(
                account=accounts["income"],
                description=f"{description} — service income",
                credit=income,
            )
        )
    if tax != 0:
        lines.append(
            JournalLine(
                account=accounts["tax"],
                description=f"{description} — tax",
                credit=tax,
            )
        )
    return JournalEntry(
        number=invoice.number,
        date=paid_on,
        currency=(invoice.currency or "USD").upper(),
        description=description,
        lines=lines,
    )


def _qbo_payload(entry: JournalEntry) -> dict:
    lines = []
    for line in entry.lines:
        debit = line.debit > 0
        lines.append(
            {
                "Description": line.description,
                "Amount": float(line.debit if debit else line.credit),
                "DetailType": "JournalEntryLineDetail",
                "JournalEntryLineDetail": {
                    "PostingType": "Debit" if debit else "Credit",
                    "AccountRef": {"value": line.account},
                },
            }
        )
    return {
        "DocNumber": entry.number,
        "TxnDate": entry.date.isoformat(),
        "PrivateNote": entry.description,
        "Line": lines,
    }


def _xero_payload(entry: JournalEntry) -> dict:
    return {
        "ManualJournals": [
            {
                "Narration": entry.description,
                "Date": entry.date.isoformat(),
                "Status": "POSTED",
                "JournalLines": [
                    {
                        "Description": line.description,
                        "LineAmount": float(line.debit - line.credit),
                        "AccountCode": line.account,
                    }
                    for line in entry.lines
                ],
            }
        ]
    }


async def post_entry(
    conn: AccountingConnection, entry: JournalEntry
) -> str:
    if conn.provider == "stub":
        return f"STUB-{uuid.uuid4().hex[:12].upper()}"

    access = await ensure_access_token(conn)
    p = conn.provider
    if p == "quickbooks":
        if not conn.external_tenant_id:
            raise AccountingError("QuickBooks company id is missing. Reconnect.")
        host = (
            "https://sandbox-quickbooks.api.intuit.com"
            if settings.quickbooks_environment == "sandbox"
            else "https://quickbooks.api.intuit.com"
        )
        url = (
            f"{host}/v3/company/{conn.external_tenant_id}/journalentry"
            "?minorversion=73"
        )
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                json=_qbo_payload(entry),
                headers={
                    "Authorization": f"Bearer {access}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        if response.status_code >= 400:
            raise AccountingError(
                f"QuickBooks error ({response.status_code}): {response.text[:300]}"
            )
        return str(response.json().get("JournalEntry", {}).get("Id", ""))

    if not conn.external_tenant_id:
        raise AccountingError("Xero organisation id is missing. Reconnect.")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{XERO_API_BASE}/ManualJournals",
            json=_xero_payload(entry),
            headers={
                "Authorization": f"Bearer {access}",
                "xero-tenant-id": conn.external_tenant_id,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    if response.status_code >= 400:
        raise AccountingError(
            f"Xero error ({response.status_code}): {response.text[:300]}"
        )
    journals = response.json().get("ManualJournals") or []
    return str(journals[0].get("ManualJournalID", "")) if journals else ""


def journal_csv(entries: list[JournalEntry]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "date",
            "invoice",
            "description",
            "account_code",
            "debit",
            "credit",
            "currency",
        ]
    )
    for entry in entries:
        for line in entry.lines:
            writer.writerow(
                [
                    entry.date.isoformat(),
                    entry.number,
                    line.description,
                    line.account,
                    f"{line.debit:.2f}",
                    f"{line.credit:.2f}",
                    entry.currency,
                ]
            )
    return buffer.getvalue()


async def pending_invoices(
    session: AsyncSession, tenant_id: uuid.UUID, connection_id: uuid.UUID | None
) -> int:
    if connection_id is None:
        query = select(Invoice.id).where(
            Invoice.tenant_id == tenant_id, Invoice.status == "paid"
        )
    else:
        posted = select(AccountingSyncItem.invoice_id).where(
            AccountingSyncItem.connection_id == connection_id,
            AccountingSyncItem.status == "posted",
            AccountingSyncItem.invoice_id.is_not(None),
        )
        query = select(Invoice.id).where(
            Invoice.tenant_id == tenant_id,
            Invoice.status == "paid",
            Invoice.id.notin_(posted),
        )
    return len((await session.scalars(query)).all())


async def paid_invoices(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    start: date,
    end: date,
    connection_id: uuid.UUID | None,
) -> list[Invoice]:
    start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    query = select(Invoice).where(
        Invoice.tenant_id == tenant_id,
        Invoice.status == "paid",
        Invoice.paid_at.is_not(None),
        Invoice.paid_at >= start_dt,
        Invoice.paid_at < end_dt,
    )
    if connection_id is not None:
        posted = select(AccountingSyncItem.invoice_id).where(
            AccountingSyncItem.connection_id == connection_id,
            AccountingSyncItem.status == "posted",
            AccountingSyncItem.invoice_id.is_not(None),
        )
        query = query.where(Invoice.id.notin_(posted))
    return list((await session.scalars(query.order_by(Invoice.paid_at))).all())


async def run_sync(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    start: date,
    end: date,
) -> AccountingSyncRun:
    if end < start:
        raise AccountingError("The end date must be on or after the start date.")
    conn = await session.scalar(
        select(AccountingConnection)
        .where(AccountingConnection.tenant_id == tenant_id)
        .with_for_update()
    )
    if conn is None or conn.status != "connected":
        raise AccountingError("Connect an accounting provider before syncing.")

    invoices = await paid_invoices(session, tenant_id, start, end, conn.id)
    run = AccountingSyncRun(
        tenant_id=tenant_id,
        connection_id=conn.id,
        provider=conn.provider,
        period_start=start,
        period_end=end,
        status="pending",
    )
    session.add(run)
    await session.flush()

    accounts = accounts_for(conn)
    posted = 0
    total = Decimal("0")
    currency = "USD"
    for invoice in invoices:
        entry = build_entry(invoice, accounts)
        if entry.currency:
            currency = entry.currency
        try:
            external_id = await post_entry(conn, entry)
        except Exception as exc:  # noqa: BLE001 — recorded on the run/item
            session.add(
                AccountingSyncItem(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    connection_id=conn.id,
                    invoice_id=invoice.id,
                    invoice_number=invoice.number,
                    status="failed",
                    amount=Decimal(invoice.total or 0),
                    error=str(exc)[:500],
                )
            )
            run.status = "failed"
            run.detail = str(exc)[:500]
            break
        session.add(
            AccountingSyncItem(
                tenant_id=tenant_id,
                run_id=run.id,
                connection_id=conn.id,
                invoice_id=invoice.id,
                invoice_number=invoice.number,
                status="posted",
                amount=Decimal(invoice.total or 0),
                external_id=external_id,
            )
        )
        posted += 1
        total += Decimal(invoice.total or 0)

    if run.status != "failed":
        run.status = "succeeded"
    run.invoices_count = posted
    run.total_amount = _money(total)
    run.currency = currency
    run.completed_at = datetime.now(timezone.utc)
    if posted:
        conn.last_synced_at = run.completed_at
    await session.flush()
    return run
