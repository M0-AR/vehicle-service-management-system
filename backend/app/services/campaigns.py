"""Marketing campaigns over the existing customer + service history.

Segments are computed with two aggregate subqueries (last order, last
completed service) and delivery reuses `queue_notification`, so a deployment
without SMS/email credentials records `skipped` recipients instead of failing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import (
    DEFAULT_LOOKBACK_DAYS,
    MAX_CAMPAIGN_RECIPIENTS,
    Campaign,
    CampaignRecipient,
)
from app.models.customer import Customer
from app.models.service import ServiceOrder
from app.models.tenant import Tenant
from app.services.notifications import queue_notification


@dataclass
class Recipient:
    customer_id: uuid.UUID
    name: str
    address: str


def default_lookback(segment: str) -> int:
    return DEFAULT_LOOKBACK_DAYS.get(segment, 90)


async def _segment_customers(
    session: AsyncSession, *, segment: str, lookback_days: int
) -> list[Customer]:
    stmt = select(Customer)
    if segment == "inactive":
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        last_order = (
            select(
                ServiceOrder.customer_id.label("customer_id"),
                func.max(ServiceOrder.created_at).label("last_at"),
            )
            .group_by(ServiceOrder.customer_id)
            .subquery()
        )
        stmt = stmt.outerjoin(last_order, last_order.c.customer_id == Customer.id).where(
            or_(last_order.c.last_at.is_(None), last_order.c.last_at <= cutoff)
        )
    elif segment == "due_service":
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        last_service = (
            select(
                ServiceOrder.customer_id.label("customer_id"),
                func.max(ServiceOrder.completed_at).label("last_at"),
            )
            .where(ServiceOrder.status.in_(("completed", "invoiced")))
            .group_by(ServiceOrder.customer_id)
            .subquery()
        )
        stmt = stmt.join(last_service, last_service.c.customer_id == Customer.id).where(
            last_service.c.last_at.is_not(None), last_service.c.last_at <= cutoff
        )
    stmt = stmt.order_by(Customer.name)
    return list((await session.execute(stmt)).scalars())


def _address(customer: Customer, channel: str) -> str | None:
    value = customer.phone if channel == "sms" else customer.email
    if value is None:
        return None
    value = value.strip()
    return value or None


async def audience(
    session: AsyncSession, *, channel: str, segment: str, lookback_days: int
) -> tuple[int, list[Recipient]]:
    customers = await _segment_customers(
        session, segment=segment, lookback_days=lookback_days
    )
    recipients = []
    for customer in customers:
        address = _address(customer, channel)
        if address:
            recipients.append(
                Recipient(customer_id=customer.id, name=customer.name, address=address)
            )
    return len(customers), recipients


async def preview(
    session: AsyncSession, *, channel: str, segment: str, lookback_days: int
) -> dict:
    customers_count, recipients = await audience(
        session, channel=channel, segment=segment, lookback_days=lookback_days
    )
    return {"customers_count": customers_count, "recipients_count": len(recipients)}


def render_body(body: str, *, name: str, shop: str) -> str:
    return body.replace("{name}", name).replace("{shop}", shop)


async def send(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    campaign: Campaign,
) -> Campaign:
    if campaign.status != "draft":
        raise HTTPException(status_code=409, detail="This campaign has already been sent.")

    _, recipients = await audience(
        session,
        channel=campaign.channel,
        segment=campaign.segment,
        lookback_days=campaign.lookback_days,
    )
    if not recipients:
        raise HTTPException(
            status_code=422,
            detail="No reachable customers in this segment — widen the lookback or pick another segment.",
        )
    if len(recipients) > MAX_CAMPAIGN_RECIPIENTS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"This segment reaches {len(recipients)} customers; the limit is "
                f"{MAX_CAMPAIGN_RECIPIENTS} per campaign. Narrow the lookback days."
            ),
        )

    tenant = await session.get(Tenant, tenant_id)
    shop = tenant.name if tenant else "your workshop"

    sent = skipped = failed = 0
    for item in recipients:
        row = CampaignRecipient(
            tenant_id=tenant_id,
            campaign_id=campaign.id,
            customer_id=item.customer_id,
            recipient=item.address,
            status="pending",
        )
        session.add(row)
        await session.flush()

        notification = await queue_notification(
            session,
            tenant_id=tenant_id,
            channel=campaign.channel,
            recipient=item.address,
            template="campaign",
            body=render_body(campaign.body, name=item.name, shop=shop),
            entity_type="campaign",
            entity_id=campaign.id,
        )
        row.notification_id = notification.id
        row.status = notification.status
        row.error = notification.error
        if notification.status == "sent":
            sent += 1
        elif notification.status == "skipped":
            skipped += 1
        else:
            failed += 1

    campaign.status = "sent"
    campaign.recipients_count = len(recipients)
    campaign.sent_count = sent
    campaign.skipped_count = skipped
    campaign.failed_count = failed
    campaign.sent_at = datetime.now(timezone.utc)
    await session.flush()
    return campaign
