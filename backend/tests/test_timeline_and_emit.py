"""پوشش TimelineService و مسیرهای کوتاه emit/notify."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationChannel
from app.services import TimelineService, WorkService, emit_event, notify
from app.services.audit import write_audit


@pytest.mark.asyncio
async def test_timeline_for_entity_user_and_work_item(db: AsyncSession, seeded):
    ali = seeded["ali"]
    work = WorkService(db)
    wi = await work.create_work_item(
        organization_id=ali.organization_id,
        title="Timeline WI",
        owner_id=ali.id,
    )
    task = await work.create_task(
        organization_id=ali.organization_id,
        title="Timeline Task",
        owner_id=ali.id,
        work_item_id=wi.id,
        assignee_ids=[ali.id],
    )
    await emit_event(
        db,
        organization_id=ali.organization_id,
        event_type="custom.ping",
        entity_type="task",
        entity_id=task.id,
        actor_id=ali.id,
    )
    tl = TimelineService(db)
    by_entity = await tl.for_entity("task", task.id, organization_id=ali.organization_id)
    assert by_entity
    by_user = await tl.for_user_activity(ali.id, organization_id=ali.organization_id)
    assert by_user
    by_wi = await tl.for_work_item(wi.id, organization_id=ali.organization_id)
    assert by_wi


@pytest.mark.asyncio
async def test_notify_generic_and_write_audit(db: AsyncSession, seeded):
    ali = seeded["ali"]
    n = await notify(
        db,
        organization_id=ali.organization_id,
        user_id=ali.id,
        title="Hello",
        body="World",
        channel=NotificationChannel.WEB,
    )
    assert n.id is not None
    row = await write_audit(
        db,
        organization_id=ali.organization_id,
        action="test.ping",
        entity_type="user",
        entity_id=ali.id,
        actor_id=ali.id,
        details={"ok": True},
    )
    assert row.row_hash
