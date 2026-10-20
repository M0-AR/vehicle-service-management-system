"""SMS delivery (Twilio-compatible REST API) + notification outbox.

Config-gated: with no credentials, `send_sms` returns ("skipped", None) and the
outbox row records the intent without contacting a provider. Delivery is
best-effort from request handlers — a provider failure must never roll back
the business transaction, so callers use `queue_notification` which swallows
transport errors into the row's status/error columns.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
import uuid
from email.message import EmailMessage
from email.utils import formatdate

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.notification import Notification

log = logging.getLogger("vsms.notifications")
settings = get_settings()


def sms_configured() -> bool:
    return bool(
        settings.sms_account_sid
        and settings.sms_auth_token
        and settings.sms_from_number
    )


_SUBJECTS = {
    "order_ready": "Your vehicle is ready",
    "booking_received": "Booking received",
    "invoice_paid": "Payment received",
    "review_request": "How did we do?",
    "test": "Test message",
}


def email_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


def email_subject(template: str) -> str:
    return _SUBJECTS.get(template, "Workshop notification")


def _smtp_send(message: EmailMessage) -> None:
    mode = (settings.smtp_security or "starttls").strip().lower()
    timeout = settings.smtp_timeout
    context = ssl.create_default_context()
    if mode == "ssl":
        client = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=timeout, context=context
        )
    elif mode in {"starttls", "none"}:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)
    else:
        raise ValueError(
            f"SMTP_SECURITY must be starttls, ssl or none (got {mode!r})"
        )
    with client as smtp:
        smtp.ehlo()
        if mode == "starttls":
            smtp.starttls(context=context)
            smtp.ehlo()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


async def send_email(recipient: str, subject: str, body: str) -> tuple[str, str | None]:
    """Returns (status, error). status is sent | failed | skipped."""
    if not email_configured():
        return "skipped", "Email provider is not configured"
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=False)
    message.set_content(body)
    try:
        await asyncio.to_thread(_smtp_send, message)
    except (smtplib.SMTPException, OSError, ValueError) as exc:
        return "failed", str(exc)[:500]
    return "sent", None


async def send_sms(recipient: str, body: str) -> tuple[str, str | None]:
    """Returns (status, error). status is sent | failed | skipped."""
    if not sms_configured():
        return "skipped", "SMS provider is not configured"
    url = (
        f"{settings.sms_api_base.rstrip('/')}/2010-04-01/Accounts/"
        f"{settings.sms_account_sid}/Messages.json"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                url,
                data={
                    "To": recipient,
                    "From": settings.sms_from_number,
                    "Body": body,
                },
                auth=(settings.sms_account_sid, settings.sms_auth_token),
            )
    except httpx.HTTPError as exc:  # network/DNS/timeout
        return "failed", str(exc)[:500]
    if response.status_code >= 400:
        return "failed", response.text[:500]
    return "sent", None


async def queue_notification(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    channel: str,
    recipient: str,
    template: str,
    body: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    meta: dict | None = None,
) -> Notification:
    """Record + attempt delivery. Never raises on provider failure."""
    row = Notification(
        tenant_id=tenant_id,
        channel=channel,
        recipient=recipient,
        template=template,
        body=body,
        status="pending",
        entity_type=entity_type,
        entity_id=entity_id,
        meta=meta or {},
    )
    session.add(row)
    await session.flush()

    if channel == "sms":
        status, error = await send_sms(recipient, body)
        row.provider = settings.sms_provider if status != "skipped" else None
    elif channel == "email":
        status, error = await send_email(
            recipient, email_subject(template), body
        )
        row.provider = "smtp" if status != "skipped" else None
    else:
        status, error = "skipped", f"Unsupported channel '{channel}'"
    row.status = status
    row.error = error
    if status == "sent":
        from datetime import datetime, timezone

        row.sent_at = datetime.now(timezone.utc)

    await session.flush()
    return row


def render(template: str, **values: object) -> str:
    texts = {
        "order_ready": (
            "Hi {name}, your vehicle {plate} is ready for pickup at {shop}."
            " Reply if you have questions."
        ),
        "booking_received": (
            "Hi {name}, we received your booking request for {when} at {shop}."
            " We will confirm shortly."
        ),
        "invoice_paid": (
            "Thanks {name}! We received your payment of {amount} for invoice"
            " {number} at {shop}."
        ),
        "review_request": (
            "Thanks for visiting {shop}, {name}. How did we do? {url}"
        ),
        "test": "This is a test message from {shop}. SMS notifications are working.",
    }
    return texts.get(template, "{body}").format(body=values.get("body", ""), **values)
