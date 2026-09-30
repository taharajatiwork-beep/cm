from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CommunicationCase, Event, Task


class TimelineService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def for_entity(
        self, entity_type: str, entity_id: UUID, *, organization_id: UUID | None = None
    ) -> list[Event]:
        q = select(Event).where(Event.entity_type == entity_type, Event.entity_id == entity_id)
        if organization_id:
            q = q.where(Event.organization_id == organization_id)
        result = await self.db.execute(q.order_by(Event.created_at))
        return list(result.scalars().all())

    async def for_user_activity(self, user_id: UUID, *, organization_id: UUID | None = None) -> list[Event]:
        q = select(Event).where(Event.actor_id == user_id)
        if organization_id:
            q = q.where(Event.organization_id == organization_id)
        result = await self.db.execute(q.order_by(Event.created_at.desc()))
        return list(result.scalars().all())

    async def for_work_item(self, work_item_id: UUID, *, organization_id: UUID | None = None) -> list[Event]:
        """Include work item events plus related task/case events."""
        task_q = select(Task.id).where(Task.work_item_id == work_item_id)
        case_q = select(CommunicationCase.id).where(CommunicationCase.work_item_id == work_item_id)
        if organization_id:
            task_q = task_q.where(Task.organization_id == organization_id)
            case_q = case_q.where(CommunicationCase.organization_id == organization_id)
        task_ids = (await self.db.execute(task_q)).scalars().all()
        case_ids = (await self.db.execute(case_q)).scalars().all()
        event_filter = (
            ((Event.entity_type == "work_item") & (Event.entity_id == work_item_id))
            | ((Event.entity_type == "task") & (Event.entity_id.in_(list(task_ids) or [work_item_id])))
            | ((Event.entity_type == "case") & (Event.entity_id.in_(list(case_ids) or [work_item_id])))
        )
        q = select(Event).where(event_filter)
        if organization_id:
            q = q.where(Event.organization_id == organization_id)
        result = await self.db.execute(q.order_by(Event.created_at))
        return list(result.scalars().all())
