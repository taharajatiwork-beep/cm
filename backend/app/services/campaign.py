"""Campaign service — marketing entities linked to conversations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import PermissionCode, require_permission
from app.models.campaign import Campaign
from app.models.enums import CampaignStatus, Channel


class CampaignService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        organization_id: UUID,
        title: str,
        actor_id: UUID,
        actor_permissions: set[str],
        description: str | None = None,
        status: CampaignStatus = CampaignStatus.DRAFT,
        channel: Channel | None = None,
        owner_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        work_item_id: UUID | None = None,
        branch_id: UUID | None = None,
        team_id: UUID | None = None,
    ) -> Campaign:
        require_permission(actor_permissions, PermissionCode.CAMPAIGN_WRITE)
        row = Campaign(
            organization_id=organization_id,
            title=title.strip(),
            description=description,
            status=status,
            channel=channel,
            owner_id=owner_id or actor_id,
            vehicle_id=vehicle_id,
            work_item_id=work_item_id,
            branch_id=branch_id,
            team_id=team_id,
            created_by=actor_id,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def get(self, campaign_id: UUID) -> Campaign | None:
        return await self.db.get(Campaign, campaign_id)

    async def list(
        self,
        organization_id: UUID,
        *,
        q: str | None = None,
        status: CampaignStatus | None = None,
        limit: int = 50,
        scope=None,
    ) -> list[Campaign]:
        from app.core.scope import apply_scope

        query = apply_scope(
            select(Campaign).where(Campaign.organization_id == organization_id), Campaign, scope
        )
        if status:
            query = query.where(Campaign.status == status)
        if q:
            like = f"%{q}%"
            query = query.where(
                or_(Campaign.title.ilike(like), Campaign.description.ilike(like))
            )
        result = await self.db.execute(query.order_by(Campaign.created_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def update(
        self,
        *,
        campaign_id: UUID,
        actor_permissions: set[str],
        title: str | None = None,
        description: str | None = None,
        status: CampaignStatus | None = None,
        channel: Channel | None = None,
        owner_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        work_item_id: UUID | None = None,
    ) -> Campaign:
        require_permission(actor_permissions, PermissionCode.CAMPAIGN_WRITE)
        row = await self.get(campaign_id)
        if not row:
            raise ValueError("Campaign not found")
        if title is not None:
            row.title = title.strip()
        if description is not None:
            row.description = description
        if status is not None:
            row.status = status
        if channel is not None:
            row.channel = channel
        if owner_id is not None:
            row.owner_id = owner_id
        if vehicle_id is not None:
            row.vehicle_id = vehicle_id
        if work_item_id is not None:
            row.work_item_id = work_item_id
        await self.db.flush()
        return row
