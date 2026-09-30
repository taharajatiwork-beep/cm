"""پوشش بیشتر WorkService: progress، workload، delegate، dependency."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import PermissionCode
from app.models.enums import CaseType, ParticipantRole, Priority, TaskRole, TaskStatus
from app.services import UNSET, WorkService


@pytest.mark.asyncio
async def test_work_progress_workload_delegate_deps(db: AsyncSession, seeded):
    ali, reza = seeded["ali"], seeded["reza"]
    work = WorkService(db)
    wi = await work.create_work_item(
        organization_id=ali.organization_id,
        title="Cover WI",
        owner_id=ali.id,
        participant_ids=[reza.id],
        deadline=datetime.now(UTC) + timedelta(days=2),
        priority=Priority.HIGH,
    )
    t1 = await work.create_task(
        organization_id=ali.organization_id,
        title="Prereq",
        owner_id=ali.id,
        work_item_id=wi.id,
        assignee_ids=[ali.id],
        deadline=datetime.now(UTC) - timedelta(hours=1),
        actor_permissions={PermissionCode.TASK_WRITE.value},
    )
    t2 = await work.create_task(
        organization_id=ali.organization_id,
        title="Blocked dep",
        owner_id=ali.id,
        work_item_id=wi.id,
        assignee_ids=[reza.id],
    )
    await work.add_dependency(t2.id, t1.id, actor_id=ali.id)
    await db.refresh(t2)
    assert t2.status == TaskStatus.BLOCKED

    await work.complete_task(t1.id, ali.id)
    await db.refresh(t2)
    assert t2.status == TaskStatus.ASSIGNED

    progress = await work.work_item_progress(wi.id)
    assert progress["total_tasks"] == 2
    assert progress["completed_tasks"] == 1
    assert progress["overdue_tasks"] >= 0

    load = await work.user_workload(reza.id, organization_id=ali.organization_id)
    assert load["open_tasks"] >= 1

    await work.delegate_task(
        task_id=t2.id,
        actor_id=ali.id,
        actor_permissions={PermissionCode.TASK_DELEGATE.value},
        to_user_id=ali.id,
    )
    sara = seeded["sara"]
    await work.add_work_item_participant(
        work_item_id=wi.id, user_id=sara.id, role=ParticipantRole.MEMBER, actor_id=ali.id
    )
    await work.add_task_participant(
        task_id=t2.id, user_id=sara.id, role=TaskRole.FOLLOWER, actor_id=ali.id
    )

    items = await work.list_work_items(ali.organization_id, owner_id=ali.id)
    assert any(i.id == wi.id for i in items)
    tasks = await work.list_tasks(ali.organization_id, assignee_id=reza.id, overdue_only=False)
    assert tasks
    overdue = await work.list_tasks(ali.organization_id, overdue_only=True)
    assert isinstance(overdue, list)

    case = await work.create_case(
        organization_id=ali.organization_id,
        subject="Cover case",
        case_type=CaseType.FOLLOW_UP,
        created_by=ali.id,
        work_item_id=wi.id,
        owner_id=reza.id,
        priority=Priority.MEDIUM,
    )
    updated = await work.update_case(
        organization_id=ali.organization_id,
        case_id=case.id,
        actor_id=ali.id,
        owner_id=ali.id,
    )
    assert updated.owner_id == ali.id
    same = await work.update_case(
        organization_id=ali.organization_id,
        case_id=case.id,
        actor_id=ali.id,
        owner_id=UNSET,
    )
    assert same.owner_id == ali.id

    cases = await work.list_cases(ali.organization_id, owner_id=ali.id)
    assert any(c.id == case.id for c in cases)

    await work.complete_task(t2.id, ali.id)
    await work._refresh_work_item_status(wi.id)
    await db.refresh(wi)
