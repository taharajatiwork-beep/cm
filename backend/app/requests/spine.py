"""اتصال وظیفه، گفتگو و پیوست به پروژه و درخواست. از پرفورمنس import نمی‌کند."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import as_utc
from app.models import Conversation, ConversationParticipant, Message, Task, User
from app.models.enums import Channel, MessageType, ParticipantRole, TaskStatus
from app.requests.models import DesignDeliverable, Shoot, WorkAttachment, WorkProject, WorkRequest
from app.services import notify

TEMPLATES: dict[str, list[str]] = {
    "طراحی": ["بریف", "طرح اولیه", "بازبینی", "تحویل"],
    "فیلم‌برداری": ["هماهنگی لوکیشن", "فیلم‌برداری", "تحویل فایل"],
    "تولید محتوا": ["متن", "بازبینی", "انتشار"],
    "عمومی": ["شروع", "انجام", "تحویل"],
    "پرفورمنس": ["هماهنگی", "تصمیم"],
}

KIND_HINT = {
    "قیمت و پست‌ها": "operational",
    "تبلیغات": "project",
    "عمومی": "project",
}


def template_for(kind: str) -> list[str]:
    return list(TEMPLATES.get(kind, TEMPLATES["عمومی"]))


async def ensure_thread(
    db: AsyncSession,
    *,
    organization_id: UUID,
    actor_id: UUID,
    project_id: UUID | None = None,
    request_id: UUID | None = None,
    topic: str = "",
) -> Conversation:
    query = select(Conversation).where(Conversation.organization_id == organization_id)
    if project_id:
        query = query.where(Conversation.project_id == project_id)
    else:
        query = query.where(Conversation.request_id == request_id, Conversation.project_id.is_(None))
    row = await db.scalar(query)
    if row is None:
        row = Conversation(
            organization_id=organization_id,
            channel=Channel.WEB,
            topic=topic or "گفتگوی کار",
            project_id=project_id,
            request_id=request_id,
        )
        db.add(row)
        await db.flush()
    member = await db.scalar(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == row.id,
            ConversationParticipant.user_id == actor_id,
        )
    )
    if member is None:
        db.add(
            ConversationParticipant(
                conversation_id=row.id, user_id=actor_id, role=ParticipantRole.MEMBER
            )
        )
        await db.flush()
    return row


async def system_message(
    db: AsyncSession,
    conversation: Conversation,
    text: str,
    *,
    task_id: UUID | None = None,
) -> None:
    db.add(
        Message(
            organization_id=conversation.organization_id,
            conversation_id=conversation.id,
            channel=Channel.SYSTEM,
            text=text,
            message_type=MessageType.SYSTEM,
            task_id=task_id,
        )
    )
    await db.flush()


def progress(tasks: list[Task]) -> dict:
    total = len(tasks)
    done = len([row for row in tasks if row.status == TaskStatus.COMPLETED])
    return {"total": total, "done": done, "ratio": (done / total) if total else 0}


def ready_to_close(request: WorkRequest, tasks: list[Task]) -> bool:
    if request.status != "converted":
        return False
    if not tasks:
        return False
    return all(row.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED) for row in tasks)


async def tasks_for(
    db: AsyncSession,
    organization_id: UUID,
    *,
    project_id: UUID | None = None,
    request_id: UUID | None = None,
) -> list[Task]:
    query = select(Task).where(Task.organization_id == organization_id)
    if project_id:
        query = query.where(Task.project_id == project_id)
    if request_id:
        query = query.where(Task.request_id == request_id)
    return list((await db.scalars(query)).all())


def bucket(task: Task, *, viewer_id: UUID, assignee_ids: set[UUID], now: datetime) -> str:
    open_status = task.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)
    waiting_on_other = viewer_id == task.owner_id and assignee_ids and viewer_id not in assignee_ids
    if open_status and waiting_on_other:
        return "waiting"
    if not open_status:
        return "done"
    # SQLite ددلاین را naive برمی‌گرداند؛ بدون as_utc، مقایسه با now (آگاه) TypeError می‌دهد
    deadline = as_utc(task.deadline)
    if deadline and deadline < now:
        return "overdue"
    if deadline and deadline.date() == now.date():
        return "today"
    return "later"


async def my_work(db: AsyncSession, organization_id: UUID, user_id: UUID) -> dict:
    from app.models import TaskAssignee

    rows = list(
        (await db.scalars(select(Task).where(Task.organization_id == organization_id))).all()
    )
    links = list((await db.scalars(select(TaskAssignee))).all())
    by_task: dict[UUID, set[UUID]] = {}
    for link in links:
        by_task.setdefault(link.task_id, set()).add(link.user_id)
    now = datetime.now(UTC)
    groups = {"overdue": [], "today": [], "later": [], "waiting": []}
    for task in rows:
        people = by_task.get(task.id, set())
        if user_id != task.owner_id and user_id not in people:
            continue
        name = bucket(task, viewer_id=user_id, assignee_ids=people, now=now)
        if name == "done":
            continue
        origin = "project" if task.project_id else "request" if task.request_id else "work"
        groups[name].append(
            {
                "id": str(task.id),
                "title": task.title,
                "status": task.status.value if hasattr(task.status, "value") else str(task.status),
                "deadline": task.deadline.isoformat() if task.deadline else None,
                "origin": origin,
                "project_id": str(task.project_id) if task.project_id else None,
                "request_id": str(task.request_id) if task.request_id else None,
            }
        )
    projects = list(
        (await db.scalars(select(WorkProject).where(WorkProject.organization_id == organization_id))).all()
    )
    busy = {task.project_id for task in rows if task.project_id}
    groups["projects_without_tasks"] = [
        {"id": str(project.id), "title": project.title, "code": project.code}
        for project in projects
        if project.id not in busy and project.status != "done"
    ]
    return groups


async def team_load(db: AsyncSession, organization_id: UUID, team_ids: list[UUID]) -> list[dict]:
    if not team_ids:
        return []
    users = list(
        (
            await db.scalars(
                select(User).where(User.organization_id == organization_id, User.team_id.in_(team_ids))
            )
        ).all()
    )
    tasks = list((await db.scalars(select(Task).where(Task.organization_id == organization_id))).all())
    now = datetime.now(UTC)
    out = []
    for user in users:
        mine = [row for row in tasks if row.owner_id == user.id and row.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)]
        overdue = [row for row in mine if (dl := as_utc(row.deadline)) is not None and dl < now]
        out.append(
            {
                "user_id": str(user.id),
                "name": user.full_name,
                "team_id": str(user.team_id) if user.team_id else None,
                "active": len(mine),
                "overdue": len(overdue),
            }
        )
    return out


async def child_team_ids(db: AsyncSession, root_ids: list[UUID]) -> list[UUID]:
    from app.models import Team

    found = list(root_ids)
    frontier = list(root_ids)
    while frontier:
        rows = list((await db.scalars(select(Team).where(Team.parent_team_id.in_(frontier)))).all())
        frontier = [row.id for row in rows if row.id not in found]
        found.extend(frontier)
    return found


async def assert_visible(db: AsyncSession, organization_id: UUID, kind: str, entity_id: UUID) -> None:
    if kind == "project":
        row = await db.get(WorkProject, entity_id)
    elif kind == "request":
        row = await db.get(WorkRequest, entity_id)
    else:
        row = None
    if row is None or row.organization_id != organization_id:
        raise LookupError(kind)


def deliverable_out(row: DesignDeliverable) -> dict:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "title": row.title,
        "version": row.version,
        "url": row.url,
        "status": row.status,
    }


def shoot_out(row: Shoot) -> dict:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "title": row.title,
        "shoot_date": row.shoot_date.isoformat() if row.shoot_date else None,
        "location": row.location,
        "people": row.people,
        "status": row.status,
        "delivery_url": row.delivery_url,
    }


def attachment_out(row: WorkAttachment) -> dict:
    return {
        "id": str(row.id),
        "title": row.title,
        "url": row.url,
        "kind": row.kind,
        "project_id": str(row.project_id) if row.project_id else None,
        "request_id": str(row.request_id) if row.request_id else None,
    }


async def ping(db: AsyncSession, organization_id: UUID, user_id: UUID | None, title: str, body: str, entity_id: UUID) -> None:
    if not user_id:
        return
    await notify(
        db,
        organization_id=organization_id,
        user_id=user_id,
        title=title,
        body=body,
        entity_type="work_project",
        entity_id=entity_id,
    )
