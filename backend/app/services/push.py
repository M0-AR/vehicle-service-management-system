"""Web Push delivery for staff devices.

Config-gated like the SMS channel: the deployment's VAPID keypair comes from
env when present, otherwise it is generated once and stored (private key
encrypted with the master KEK) so keyless dev deployments still work. The
`pywebpush` package is optional at import time — `available()` reports whether
delivery is possible and `GET /push/config` mirrors that to the UI.

Delivery is best-effort: `send_to_users` never raises, counts sent/failed, and
deletes subscriptions the push service says are gone (404/410), so a bounced
notification can never fail the business request that triggered it.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.config import get_settings
from app.models.push import PushConfig, PushSubscription
from app.models.user import User

try:  # pragma: no cover - exercised only when the package is missing
    from py_vapid import Vapid
    from pywebpush import WebPushException, webpush
except ImportError:  # pragma: no cover
    webpush = None
    WebPushException = None  # type: ignore[assignment,misc]
    Vapid = None  # type: ignore[assignment,misc]

log = logging.getLogger("vsms.push")
settings = get_settings()

PUSH_TTL_SECONDS = 12 * 3600


def available() -> bool:
    return webpush is not None


def _generate_keypair() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_raw = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    public_b64 = base64.urlsafe_b64encode(public_raw).rstrip(b"=").decode()
    return public_b64, private_pem


async def config(session: AsyncSession) -> tuple[str, str, str] | None:
    """Returns (public_key, private_pem, subject) or None when unavailable."""
    if not available():
        return None
    subject = settings.vapid_subject or "mailto:push@example.com"
    if settings.vapid_public_key and settings.vapid_private_key:
        return settings.vapid_public_key, settings.vapid_private_key, subject

    row = await session.get(PushConfig, 1)
    if row is None:
        public_b64, private_pem = _generate_keypair()
        try:
            encrypted = crypto.encrypt_secret(private_pem)
        except ValueError:
            log.warning("push disabled: MASTER_KEK_B64 is not configured")
            return None
        row = PushConfig(
            id=1,
            public_key=public_b64,
            private_key=encrypted,
            subject=subject,
        )
        session.add(row)
        try:
            await session.flush()
        except Exception:
            # Racing workers both generate: first writer wins, reuse theirs.
            await session.rollback()
            row = await session.get(PushConfig, 1)
            if row is None:
                raise
    return row.public_key, crypto.decrypt_secret(row.private_key), row.subject


async def subscribe(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None,
) -> PushSubscription:
    statement = (
        pg_insert(PushSubscription)
        .values(
            tenant_id=tenant_id,
            user_id=user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=user_agent,
        )
        .on_conflict_do_update(
            constraint="uq_push_subscriptions_tenant_endpoint",
            set_={
                "user_id": user_id,
                "p256dh": p256dh,
                "auth": auth,
                "user_agent": user_agent,
            },
        )
    )
    await session.execute(statement)
    await session.flush()
    result = await session.execute(
        select(PushSubscription).where(
            PushSubscription.tenant_id == tenant_id,
            PushSubscription.endpoint == endpoint,
        )
    )
    return result.scalar_one()


async def list_subscriptions(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> list[PushSubscription]:
    statement = select(PushSubscription).where(PushSubscription.tenant_id == tenant_id)
    if user_id is not None:
        statement = statement.where(PushSubscription.user_id == user_id)
    result = await session.execute(statement.order_by(PushSubscription.created_at))
    return list(result.scalars())


async def send_to_users(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_ids: list[uuid.UUID],
    title: str,
    body: str,
    url: str | None = None,
) -> tuple[int, int]:
    """Best-effort fan-out to the users' devices. Returns (sent, failed)."""
    if not available() or not user_ids:
        return 0, 0
    config_row = await config(session)
    if config_row is None:
        return 0, 0
    public_key, private_pem, subject = config_row

    result = await session.execute(
        select(PushSubscription).where(
            PushSubscription.tenant_id == tenant_id,
            PushSubscription.user_id.in_(user_ids),
        )
    )
    subscriptions = list(result.scalars())
    if not subscriptions:
        return 0, 0

    # pywebpush's from_string treats the argument as base64 DER, so a PEM blob
    # must be handed over as a Vapid instance instead of a bare string.
    try:
        vapid = Vapid.from_pem(private_pem.encode())
    except Exception:  # noqa: BLE001 - a corrupt stored key must not raise
        log.warning("push disabled: stored VAPID key could not be parsed")
        return 0, 0
    payload = json.dumps({"title": title, "body": body, "url": url or "/app"})
    claims = {
        "sub": subject,
        "exp": int(time.time()) + PUSH_TTL_SECONDS,
    }
    sent = 0
    failed = 0
    dead: list[uuid.UUID] = []
    for subscription in subscriptions:
        info = {
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        }
        try:
            await asyncio.to_thread(
                webpush,
                subscription_info=info,
                data=payload,
                vapid_private_key=vapid,
                vapid_claims=dict(claims),
                timeout=10,
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001 - never fail the caller
            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)
            if status_code in (404, 410):
                dead.append(subscription.id)
            failed += 1
            log.info(
                "push failed tenant=%s endpoint_prefix=%s status=%s",
                tenant_id,
                subscription.endpoint[:48],
                status_code,
            )
    if dead:
        await session.execute(delete(PushSubscription).where(PushSubscription.id.in_(dead)))
        await session.flush()
    return sent, failed


async def notify_staff(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    roles: tuple[str, ...],
    title: str,
    body: str,
    url: str | None = None,
) -> tuple[int, int]:
    result = await session.execute(
        select(User.id).where(
            User.tenant_id == tenant_id,
            User.role.in_(roles),
            User.is_active.is_(True),
        )
    )
    user_ids = [row[0] for row in result.all()]
    return await send_to_users(
        session, tenant_id=tenant_id, user_ids=user_ids, title=title, body=body, url=url
    )


async def notify_user(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    title: str,
    body: str,
    url: str | None = None,
) -> tuple[int, int]:
    return await send_to_users(
        session, tenant_id=tenant_id, user_ids=[user_id], title=title, body=body, url=url
    )
