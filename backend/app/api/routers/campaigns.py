from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_feature
from app.db.session import get_db
from app.models.campaign import Campaign, CampaignRecipient
from app.schemas.campaign import (
    CampaignCreate,
    CampaignDetailOut,
    CampaignOut,
    CampaignPreviewIn,
    CampaignPreviewOut,
    CampaignRecipientOut,
)
from app.schemas.common import Page
from app.services import audit, campaigns

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

READ_ROLES = ("owner", "admin", "manager")
WRITE_ROLES = ("owner", "admin")


async def _get_campaign(
    session: AsyncSession, tenant_id: uuid.UUID, campaign_id: uuid.UUID
) -> Campaign:
    campaign = await session.scalar(
        select(Campaign).where(
            Campaign.tenant_id == tenant_id, Campaign.id == campaign_id
        )
    )
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return campaign


@router.get("", response_model=Page[CampaignOut])
async def list_campaigns(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: AuthContext = Depends(require_feature("marketing")),
    session: AsyncSession = Depends(get_db),
) -> Page[CampaignOut]:
    ctx.require_rank(*READ_ROLES)
    base = select(Campaign).where(Campaign.tenant_id == ctx.tenant_id)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = await session.scalars(
        base.order_by(Campaign.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page[CampaignOut](
        items=[CampaignOut.model_validate(row) for row in rows],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.post("/preview", response_model=CampaignPreviewOut)
async def preview_audience(
    payload: CampaignPreviewIn,
    ctx: AuthContext = Depends(require_feature("marketing")),
    session: AsyncSession = Depends(get_db),
) -> CampaignPreviewOut:
    ctx.require_rank(*READ_ROLES)
    counts = await campaigns.preview(
        session,
        channel=payload.channel,
        segment=payload.segment,
        lookback_days=payload.lookback_days,
    )
    return CampaignPreviewOut(**counts)


@router.post("", response_model=CampaignOut, status_code=201)
async def create_campaign(
    payload: CampaignCreate,
    ctx: AuthContext = Depends(require_feature("marketing")),
    session: AsyncSession = Depends(get_db),
) -> CampaignOut:
    ctx.require_rank(*WRITE_ROLES)
    campaign = Campaign(
        tenant_id=ctx.tenant_id,
        name=payload.name.strip(),
        channel=payload.channel,
        segment=payload.segment,
        lookback_days=payload.lookback_days,
        body=payload.body.strip(),
        created_by=ctx.user_id,
    )
    session.add(campaign)
    await session.flush()
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="campaign.created",
        entity="campaign",
        entity_id=campaign.id,
        meta={"segment": campaign.segment, "channel": campaign.channel},
    )
    return CampaignOut.model_validate(campaign)


@router.get("/{campaign_id}", response_model=CampaignDetailOut)
async def get_campaign(
    campaign_id: uuid.UUID,
    ctx: AuthContext = Depends(require_feature("marketing")),
    session: AsyncSession = Depends(get_db),
) -> CampaignDetailOut:
    ctx.require_rank(*READ_ROLES)
    campaign = await _get_campaign(session, ctx.tenant_id, campaign_id)
    recipients = await session.scalars(
        select(CampaignRecipient)
        .where(CampaignRecipient.campaign_id == campaign.id)
        .order_by(CampaignRecipient.created_at.asc())
        .limit(500)
    )
    detail = CampaignDetailOut.model_validate(campaign)
    detail.recipients = [
        CampaignRecipientOut.model_validate(row) for row in recipients
    ]
    return detail


@router.post("/{campaign_id}/send", response_model=CampaignOut)
async def send_campaign(
    campaign_id: uuid.UUID,
    ctx: AuthContext = Depends(require_feature("marketing")),
    session: AsyncSession = Depends(get_db),
) -> CampaignOut:
    ctx.require_rank(*WRITE_ROLES)
    campaign = await _get_campaign(session, ctx.tenant_id, campaign_id)
    campaign = await campaigns.send(
        session, tenant_id=ctx.tenant_id, campaign=campaign
    )
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="campaign.sent",
        entity="campaign",
        entity_id=campaign.id,
        meta={
            "recipients": campaign.recipients_count,
            "sent": campaign.sent_count,
            "skipped": campaign.skipped_count,
            "failed": campaign.failed_count,
        },
    )
    return CampaignOut.model_validate(campaign)


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: uuid.UUID,
    ctx: AuthContext = Depends(require_feature("marketing")),
    session: AsyncSession = Depends(get_db),
) -> Response:
    ctx.require_rank(*WRITE_ROLES)
    campaign = await _get_campaign(session, ctx.tenant_id, campaign_id)
    if campaign.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="Sent campaigns are kept for history and cannot be deleted.",
        )
    await session.delete(campaign)
    await audit.record(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        action="campaign.deleted",
        entity="campaign",
        entity_id=campaign_id,
        meta={"name": campaign.name},
    )
    return Response(status_code=204)
