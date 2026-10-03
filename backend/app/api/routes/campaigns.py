from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, handle_authz
from app.core.permissions import AuthorizationError, PermissionCode, require_permission
from app.db.session import get_db
from app.models.enums import CampaignStatus, Channel
from app.services.campaign import CampaignService

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class CampaignCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: CampaignStatus = CampaignStatus.DRAFT
    channel: Channel | None = None
    owner_id: UUID | None = None
    vehicle_id: UUID | None = None
    work_item_id: UUID | None = None
    branch_id: UUID | None = None
    team_id: UUID | None = None


class CampaignUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: CampaignStatus | None = None
    channel: Channel | None = None
    owner_id: UUID | None = None
    vehicle_id: UUID | None = None
    work_item_id: UUID | None = None


class CampaignOut(BaseModel):
    id: UUID
    organization_id: UUID
    title: str
    description: str | None
    status: CampaignStatus
    channel: Channel | None
    owner_id: UUID | None
    vehicle_id: UUID | None
    work_item_id: UUID | None
    branch_id: UUID | None
    team_id: UUID | None

    model_config = {"from_attributes": True}


@router.post("", response_model=CampaignOut)
async def create_campaign(
    body: CampaignCreate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await CampaignService(db).create(
            organization_id=ctx.organization_id,
            title=body.title,
            actor_id=ctx.user.id,
            actor_permissions=ctx.permissions,
            description=body.description,
            status=body.status,
            channel=body.channel,
            owner_id=body.owner_id,
            vehicle_id=body.vehicle_id,
            work_item_id=body.work_item_id,
            branch_id=body.branch_id,
            team_id=body.team_id,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e


@router.get("", response_model=list[CampaignOut])
async def list_campaigns(
    q: str | None = None,
    status: CampaignStatus | None = None,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.CAMPAIGN_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return await CampaignService(db).list(ctx.organization_id, q=q, status=status, scope=ctx.scope)


@router.get("/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    campaign_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.CAMPAIGN_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    row = await CampaignService(db).get(campaign_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(404, "Campaign not found")
    from app.core.scope import row_is_visible
    from app.models.campaign import Campaign

    if not await row_is_visible(db, Campaign, campaign_id, ctx.organization_id, ctx.scope):
        raise HTTPException(404, "Campaign not found")
    return row


@router.patch("/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: UUID,
    body: CampaignUpdate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await CampaignService(db).get(campaign_id)
        if not row or row.organization_id != ctx.organization_id:
            raise HTTPException(404, "Campaign not found")
        return await CampaignService(db).update(
            campaign_id=campaign_id,
            actor_permissions=ctx.permissions,
            title=body.title,
            description=body.description,
            status=body.status,
            channel=body.channel,
            owner_id=body.owner_id,
            vehicle_id=body.vehicle_id,
            work_item_id=body.work_item_id,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
