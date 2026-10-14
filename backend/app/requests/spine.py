"""اتصال وظیفه، گفتگو و پیوست به پروژه و درخواست. از پرفورمنس import نمی‌کند."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    pm_campaign_id: UUID | None = None,
    topic: str = "",
) -> Conversation:
    query = select(Conversation).where(Conversation.organization_id == organization_id)
    if pm_campaign_id:
        query = query.where(Conversation.pm_campaign_id == pm_campaign_id)
    elif project_id:
        query = query.where(Conversation.project_id == project_id, Conversation.pm_campaign_id.is_(None))
    else:
        query = query.where(
            Conversation.request_id == request_id,
            Conversation.project_id.is_(None),
            Conversation.pm_campaign_id.is_(None),
        )
    row = await db.scalar(query)
    if row is None:
        row = Conversation(
            organization_id=organization_id,
            channel=Channel.WEB,
            topic=topic or "گفتگوی کار",
            project_id=project_id,
            request_id=request_id,
            pm_campaign_id=pm_campaign_id,
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


_TASK_CLOSED = (TaskStatus.COMPLETED, TaskStatus.CANCELLED)


def progress(tasks: list[Task]) -> dict:
    """Progress for UI bars: cancelled tasks are excluded from the denominator."""
    active = [row for row in tasks if row.status != TaskStatus.CANCELLED]
    total = len(active)
    done = len([row for row in active if row.status == TaskStatus.COMPLETED])
    now_utc = datetime.now(UTC)
    overdue_active = 0
    for row in active:
        if row.status in _TASK_CLOSED or not row.deadline:
            continue
        deadline = row.deadline.replace(tzinfo=UTC) if row.deadline.tzinfo is None else row.deadline
        if deadline < now_utc:
            overdue_active += 1
    return {
        "total": total,
        "done": done,
        "ratio": (done / total) if total else 0,
        "overdue": overdue_active,
    }


async def advance_project_from_tasks(db: AsyncSession, project_id: UUID) -> None:
    """اولین تیک پروژه را «در جریان» می‌کند؛ وقتی همهٔ وظایف تمام یا لغو شدند، «تمام»."""
    project = await db.get(WorkProject, project_id)
    if not project:
        return
    tasks = list((await db.scalars(select(Task).where(Task.project_id == project_id))).all())
    if not tasks:
        return
    all_closed = all(task.status in _TASK_CLOSED for task in tasks)
    any_done = any(task.status == TaskStatus.COMPLETED for task in tasks)
    if all_closed and project.status != "done":
        project.status = "done"
        project.updated_at = datetime.now(UTC)
    elif any_done and project.status == "new":
        project.status = "in_progress"
        project.updated_at = datetime.now(UTC)
    if project.request_id:
        await close_request_if_projects_done(db, project.request_id)


async def close_request_if_projects_done(db: AsyncSession, request_id: UUID) -> None:
    """درخواست تبدیل‌شده وقتی تمام پروژه‌هایش تمام شوند، تمام می‌شود."""
    request = await db.get(WorkRequest, request_id)
    if not request or request.status != "converted":
        return
    projects = list((await db.scalars(select(WorkProject).where(WorkProject.request_id == request_id))).all())
    if projects and all(row.status == "done" for row in projects):
        request.status = "done"
        request.updated_at = datetime.now(UTC)


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
    query = select(Task).options(selectinload(Task.assignees)).where(Task.organization_id == organization_id)
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
    projects = list(
        (await db.scalars(select(WorkProject).where(WorkProject.organization_id == organization_id))).all()
    )
    requests = list(
        (await db.scalars(select(WorkRequest).where(WorkRequest.organization_id == organization_id))).all()
    )
    project_by_id = {row.id: row for row in projects}
    request_by_id = {row.id: row for row in requests}

    def parent_meta(task: Task) -> dict[str, str | None]:
        out: dict[str, str | None] = {
            "project_code": None,
            "project_title": None,
            "request_code": None,
            "request_title": None,
        }
        if task.project_id:
            project = project_by_id.get(task.project_id)
            if project:
                out["project_code"] = project.code
                out["project_title"] = project.title
                if project.request_id:
                    request = request_by_id.get(project.request_id)
                    if request:
                        out["request_id"] = str(request.id)
                        out["request_code"] = request.code
                        out["request_title"] = request.title
        elif task.request_id:
            request = request_by_id.get(task.request_id)
            if request:
                out["request_code"] = request.code
                out["request_title"] = request.title
        return out

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
                "kind": "task",
                "id": str(task.id),
                "title": task.title,
                "status": task.status.value if hasattr(task.status, "value") else str(task.status),
                "deadline": task.deadline.isoformat() if task.deadline else None,
                "origin": origin,
                "owner_id": str(task.owner_id),
                "assignee_ids": [str(uid) for uid in sorted(people)],
                "project_id": str(task.project_id) if task.project_id else None,
                "request_id": str(task.request_id) if task.request_id else None,
                **parent_meta(task),
            }
        )
    busy = {task.project_id for task in rows if task.project_id}
    groups["projects_without_tasks"] = []
    for project in projects:
        if project.id in busy or project.status == "done":
            continue
        entry: dict[str, str | None] = {
            "kind": "project",
            "id": str(project.id),
            "title": project.title,
            "code": project.code,
            "project_id": str(project.id),
            "project_code": project.code,
            "project_title": project.title,
            "request_id": str(project.request_id) if project.request_id else None,
            "request_code": None,
            "request_title": None,
        }
        if project.request_id:
            request = request_by_id.get(project.request_id)
            if request:
                entry["request_code"] = request.code
                entry["request_title"] = request.title
        groups["projects_without_tasks"].append(entry)
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


def _spine_at(value: datetime | date | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return value.isoformat()


def _task_spine_node(task: Task) -> dict:
    return {
        "at": _spine_at(task.created_at),
        "kind": "task",
        "id": str(task.id),
        "label": task.title,
        "status": task.status.value if hasattr(task.status, "value") else str(task.status),
    }


def _payment_spine_node(row) -> dict:
    return {
        "at": _spine_at(row.created_at),
        "kind": "payment_request",
        "id": str(row.id),
        "label": f"درخواست پرداخت {row.amount_toman:,} تومان",
        "status": row.status,
    }


def _campaign_spine_node(row) -> dict:
    return {
        "at": _spine_at(row.created_at),
        "kind": "perf_campaign",
        "id": str(row.id),
        "code": row.code,
        "label": row.title or row.code,
        "status": row.status,
    }


async def build_spine_timeline(
    db: AsyncSession,
    organization_id: UUID,
    *,
    request_id: UUID | None = None,
    project_id: UUID | None = None,
) -> list[dict]:
    """خط زمین مفهومی: درخواست کار، پروژه، وظیفه، پرداخت، کمپین پرفورمنس — بدون ادغام جدول."""
    from app.perf.models import PmCampaign, PmPaymentRequest

    items: list[dict] = []
    if request_id:
        req = await db.get(WorkRequest, request_id)
        if req and req.organization_id == organization_id:
            items.append(
                {
                    "at": _spine_at(req.created_at),
                    "kind": "work_request",
                    "id": str(req.id),
                    "code": req.code,
                    "label": req.title,
                    "status": req.status,
                }
            )
        for project in (await db.scalars(select(WorkProject).where(WorkProject.request_id == request_id))).all():
            items.append(
                {
                    "at": _spine_at(project.created_at),
                    "kind": "work_project",
                    "id": str(project.id),
                    "code": project.code,
                    "label": project.title,
                    "status": project.status,
                }
            )
        for task in await tasks_for(db, organization_id, request_id=request_id):
            items.append(_task_spine_node(task))
        for pay in (
            await db.scalars(
                select(PmPaymentRequest).where(
                    PmPaymentRequest.organization_id == organization_id,
                    PmPaymentRequest.request_id == request_id,
                )
            )
        ).all():
            items.append(_payment_spine_node(pay))
    if project_id:
        project = await db.get(WorkProject, project_id)
        if project and project.organization_id == organization_id:
            if not request_id:
                items.append(
                    {
                        "at": _spine_at(project.created_at),
                        "kind": "work_project",
                        "id": str(project.id),
                        "code": project.code,
                        "label": project.title,
                        "status": project.status,
                    }
                )
            for task in await tasks_for(db, organization_id, project_id=project_id):
                items.append(_task_spine_node(task))
            for pay in (
                await db.scalars(
                    select(PmPaymentRequest).where(
                        PmPaymentRequest.organization_id == organization_id,
                        PmPaymentRequest.project_id == project_id,
                    )
                )
            ).all():
                items.append(_payment_spine_node(pay))
            for camp in (
                await db.scalars(
                    select(PmCampaign).where(
                        PmCampaign.organization_id == organization_id,
                        PmCampaign.project_id == project_id,
                    )
                )
            ).all():
                items.append(_campaign_spine_node(camp))
    items.sort(key=lambda row: row.get("at") or "")
    return items


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
