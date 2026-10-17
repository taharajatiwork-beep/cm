"""Aggregate work, marketing, and Mizito items for the calendar range."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext
from app.calendar.models import CalendarEntry, CalendarEntryAttendee
from app.calendar.recurrence import iter_recurrence_dates
from app.calendar.entry_out import entry_out
from app.core.permissions import PermissionCode
from app.models import Task, TaskAssignee, User, WorkItem
from app.perf.models import PmCampaign, PmPage, PmSmsSend, PmStory
from app.requests.models import Shoot, WorkProject, WorkRequest
from app.requests.project_access import apply_project_visibility, base_visible_projects

DONE = {"done", "COMPLETED", "CANCELLED", "sent"}


def _calendar_read_only(ctx: AuthContext) -> bool:
    if PermissionCode.ORG_ADMIN in ctx.permissions:
        return False
    if PermissionCode.REQUEST_TRIAGE in ctx.permissions:
        return False
    if PermissionCode.REQUEST_MANAGE in ctx.permissions:
        return False
    if PermissionCode.PERF_WRITE in ctx.permissions:
        return False
    return PermissionCode.CALENDAR_READ in ctx.permissions


def _team_ids(ctx: AuthContext) -> set[UUID]:
    ids: set[UUID] = set()
    if ctx.scope.team_id:
        ids.add(ctx.scope.team_id)
    ids.update(ctx.scope.team_ids or ())
    return ids


def _day(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.date().isoformat()


def _status(value) -> str:
    return value.value if hasattr(value, "value") else str(value or "")


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    start_at = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_at = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return start_at, end_at


def _late(day: str | None, status: str) -> bool:
    if not day:
        return False
    return day < date.today().isoformat() and status not in DONE


def _layer_ok(layers: set[str] | None, layer: str) -> bool:
    if not layers:
        return True
    return layer in layers


async def expand_entries(
    db: AsyncSession,
    rows: list[CalendarEntry],
    start: date,
    end: date,
    names: dict[UUID, str],
    attendee_map: dict[UUID, list[UUID]],
) -> list[dict]:
    covered: set[tuple[UUID, date]] = set()
    out: list[dict] = []
    for row in rows:
        if not row.recurrence_parent_id:
            continue
        if start <= row.on_date <= end:
            covered.add((row.recurrence_parent_id, row.on_date))
            out.append(entry_out(row, names, attendee_map.get(row.id, [])))
    for row in rows:
        if row.recurrence_parent_id:
            continue
        for on in iter_recurrence_dates(row, start, end):
            if (row.id, on) in covered:
                continue
            occ = on if row.recurrence != "none" and row.recur_until else None
            out.append(entry_out(row, names, attendee_map.get(row.id, []), occurrence_date=occ))
    return out


async def gather_work_events(
    db: AsyncSession,
    org: UUID,
    start: date,
    end: date,
    names: dict[UUID, str],
    ctx: AuthContext,
    layers: set[str] | None,
    mine: bool,
) -> tuple[list[dict], dict[tuple[str, str], int]]:
    events: list[dict] = []
    load: dict[tuple[str, str], int] = defaultdict(int)
    if not _layer_ok(layers, "work"):
        return events, load
    start_at, end_at = _bounds(start, end)
    read_only = _calendar_read_only(ctx)
    team_ids = _team_ids(ctx)
    user_id = ctx.user.id

    tasks = (
        await db.scalars(
            select(Task).where(
                Task.organization_id == org,
                Task.deadline.is_not(None),
                Task.deadline >= start_at,
                Task.deadline < end_at,
            )
        )
    ).all()
    task_ids = [row.id for row in tasks]
    assignee_ids: dict[UUID, list[UUID]] = {}
    if task_ids:
        links = (await db.scalars(select(TaskAssignee).where(TaskAssignee.task_id.in_(task_ids)))).all()
        for link in links:
            assignee_ids.setdefault(link.task_id, []).append(link.user_id)
    if read_only:
        project_teams: dict[UUID, UUID | None] = {}
        project_ids = {row.project_id for row in tasks if row.project_id}
        if project_ids:
            for project in (await db.scalars(select(WorkProject).where(WorkProject.id.in_(project_ids)))).all():
                project_teams[project.id] = project.team_id
        visible = []
        for row in tasks:
            if mine and row.owner_id != user_id and user_id not in assignee_ids.get(row.id, []):
                continue
            if row.owner_id == user_id or user_id in assignee_ids.get(row.id, []):
                visible.append(row)
                continue
            team_id = project_teams.get(row.project_id) if row.project_id else None
            if team_id and team_id in team_ids:
                visible.append(row)
        tasks = visible
    elif mine:
        tasks = [r for r in tasks if r.owner_id == user_id or user_id in assignee_ids.get(r.id, [])]

    for row in tasks:
        people = [row.owner_id, *assignee_ids.get(row.id, [])]
        person_id = people[0] if people else None
        label = "، ".join(dict.fromkeys(names.get(uid, "") for uid in people if names.get(uid)))
        day = _day(row.deadline)
        events.append(
            {
                "kind": "task",
                "date": day,
                "title": row.title,
                "person": label,
                "person_id": str(person_id) if person_id else None,
                "link": f"/projects/{row.project_id}" if row.project_id else "/my-work",
                "status": _status(row.status),
                "id": str(row.id),
                "color_key": "work",
                "late": _late(day, _status(row.status)),
            }
        )
        if person_id and day:
            load[(str(person_id), day)] += 1

    items = (
        await db.scalars(
            select(WorkItem).where(
                WorkItem.organization_id == org,
                WorkItem.deadline.is_not(None),
                WorkItem.deadline >= start_at,
                WorkItem.deadline < end_at,
            )
        )
    ).all()
    for row in items:
        if mine and row.owner_id != user_id:
            continue
        day = _day(row.deadline)
        events.append(
            {
                "kind": "work",
                "date": day,
                "title": row.title,
                "person": names.get(row.owner_id, ""),
                "person_id": str(row.owner_id),
                "link": "/projects",
                "status": _status(row.status),
                "id": str(row.id),
                "color_key": "work",
                "late": _late(day, _status(row.status)),
            }
        )
        if row.owner_id and day:
            load[(str(row.owner_id), day)] += 1

    q = select(WorkProject).where(
        WorkProject.organization_id == org,
        WorkProject.due_date.is_not(None),
        WorkProject.due_date >= start,
        WorkProject.due_date <= end,
    )
    if read_only or not (PermissionCode.ORG_ADMIN in ctx.permissions or ctx.scope.is_org_wide):
        q = await apply_project_visibility(q, db, ctx)
    projects = (await db.scalars(q)).all()
    for row in projects:
        if mine and row.lead_user_id != user_id:
            continue
        day = row.due_date.isoformat() if row.due_date else None
        events.append(
            {
                "kind": "project",
                "date": day,
                "title": row.title,
                "person": names.get(row.lead_user_id, "") if row.lead_user_id else "",
                "person_id": str(row.lead_user_id) if row.lead_user_id else None,
                "link": f"/projects/{row.id}",
                "status": row.status,
                "id": str(row.id),
                "color_key": "work",
                "late": _late(day, row.status),
            }
        )

    requests = (
        await db.scalars(
            select(WorkRequest).where(
                WorkRequest.organization_id == org,
                WorkRequest.due_date.is_not(None),
                WorkRequest.due_date >= start,
                WorkRequest.due_date <= end,
            )
        )
    ).all()
    for row in requests:
        if read_only and row.requested_by != user_id:
            continue
        if mine and row.requested_by != user_id:
            continue
        day = row.due_date.isoformat() if row.due_date else None
        events.append(
            {
                "kind": "request",
                "date": day,
                "title": row.title,
                "person": names.get(row.requested_by, "") if row.requested_by else "",
                "person_id": str(row.requested_by) if row.requested_by else None,
                "link": "/requests",
                "status": row.status,
                "id": str(row.id),
                "color_key": "work",
                "late": _late(day, row.status),
            }
        )

    return events, load


async def gather_mizito_events(
    db: AsyncSession,
    org: UUID,
    start: date,
    end: date,
    names: dict[UUID, str],
    ctx: AuthContext,
    layers: set[str] | None,
    mine: bool,
) -> list[dict]:
    if not _layer_ok(layers, "mizito"):
        return []
    q = base_visible_projects(org).where(
        WorkProject.mizito_deadline.is_not(None),
        WorkProject.mizito_deadline >= datetime.combine(start, time.min, tzinfo=timezone.utc),
        WorkProject.mizito_deadline <= datetime.combine(end, time.max, tzinfo=timezone.utc),
    )
    q = await apply_project_visibility(q, db, ctx)
    rows = (await db.scalars(q)).all()
    out = []
    for row in rows:
        if mine and row.lead_user_id != ctx.user.id:
            continue
        dl = row.mizito_deadline
        day = dl.date().isoformat() if dl else None
        out.append(
            {
                "kind": "mizito",
                "date": day,
                "title": f"{row.mizito_code or row.code} — {row.title}",
                "person": names.get(row.lead_user_id, "") if row.lead_user_id else "",
                "person_id": str(row.lead_user_id) if row.lead_user_id else None,
                "link": f"/projects/{row.id}",
                "status": row.mizito_status or row.status,
                "id": f"mizito-{row.id}",
                "color_key": "mizito",
                "late": _late(day, row.mizito_status or ""),
            }
        )
    return out


async def gather_marketing_events(
    db: AsyncSession,
    org: UUID,
    start: date,
    end: date,
    names: dict[UUID, str],
    ctx: AuthContext,
    layers: set[str] | None,
    mine: bool,
) -> list[dict]:
    if not _layer_ok(layers, "marketing"):
        return []
    events: list[dict] = []
    start_at, end_at = _bounds(start, end)
    read_only = _calendar_read_only(ctx)
    user_id = ctx.user.id

    shoots = (
        await db.scalars(
            select(Shoot).where(
                Shoot.organization_id == org,
                Shoot.shoot_date.is_not(None),
                Shoot.shoot_date >= start,
                Shoot.shoot_date <= end,
            )
        )
    ).all()
    for row in shoots:
        events.append(
            {
                "kind": "shoot",
                "date": row.shoot_date.isoformat() if row.shoot_date else None,
                "title": row.title,
                "person": row.people,
                "person_id": None,
                "link": f"/projects/{row.project_id}",
                "status": row.status,
                "id": str(row.id),
                "color_key": "marketing",
                "late": False,
            }
        )

    campaigns = (
        await db.scalars(
            select(PmCampaign).where(
                PmCampaign.organization_id == org,
                (
                    (PmCampaign.starts_on.is_not(None) & (PmCampaign.starts_on >= start) & (PmCampaign.starts_on <= end))
                    | (PmCampaign.ends_on.is_not(None) & (PmCampaign.ends_on >= start) & (PmCampaign.ends_on <= end))
                ),
            )
        )
    ).all()
    for row in campaigns:
        if read_only and row.created_by != user_id:
            continue
        if mine and row.created_by != user_id:
            continue
        person = names.get(row.created_by, "") if row.created_by else ""
        person_id = str(row.created_by) if row.created_by else None
        if row.starts_on and start <= row.starts_on <= end:
            events.append(
                {
                    "kind": "campaign",
                    "date": row.starts_on.isoformat(),
                    "title": f"شروع {row.code} — {row.title}",
                    "person": person,
                    "person_id": person_id,
                    "link": f"/perf/campaigns/{row.id}",
                    "status": row.status,
                    "id": f"{row.id}-start",
                    "color_key": "marketing",
                    "late": False,
                }
            )
        if row.ends_on and start <= row.ends_on <= end and row.ends_on != row.starts_on:
            events.append(
                {
                    "kind": "campaign",
                    "date": row.ends_on.isoformat(),
                    "title": f"پایان {row.code} — {row.title}",
                    "person": person,
                    "person_id": person_id,
                    "link": f"/perf/campaigns/{row.id}",
                    "status": row.status,
                    "id": f"{row.id}-end",
                    "color_key": "marketing",
                    "late": False,
                }
            )

    stories = (
        await db.execute(
            select(PmStory, PmPage.name)
            .outerjoin(PmPage, PmStory.page_id == PmPage.id)
            .where(
                PmStory.organization_id == org,
                PmStory.published_on.is_not(None),
                PmStory.published_on >= start,
                PmStory.published_on <= end,
            )
        )
    ).all()
    for row, page_name in stories:
        events.append(
            {
                "kind": "story",
                "date": row.published_on.isoformat() if row.published_on else None,
                "title": f"{row.kind} — {page_name}" if page_name else row.kind,
                "person": names.get(row.created_by, "") if row.created_by else "",
                "person_id": str(row.created_by) if row.created_by else None,
                "link": f"/perf/campaigns/{row.campaign_id}" if row.campaign_id else "/perf/social",
                "status": row.status,
                "id": str(row.id),
                "color_key": "marketing",
                "late": False,
            }
        )

    sends = (
        await db.scalars(
            select(PmSmsSend).where(
                PmSmsSend.organization_id == org,
                PmSmsSend.sent_at.is_not(None),
                PmSmsSend.sent_at >= start_at,
                PmSmsSend.sent_at < end_at,
            )
        )
    ).all()
    for row in sends:
        text = (row.body or "پیامک").strip().replace("\n", " ")
        events.append(
            {
                "kind": "sms",
                "date": _day(row.sent_at),
                "title": text[:80],
                "person": names.get(row.created_by, "") if row.created_by else "",
                "person_id": str(row.created_by) if row.created_by else None,
                "link": "/perf/sms",
                "status": "sent",
                "id": str(row.id),
                "color_key": "marketing",
                "late": False,
            }
        )

    events.sort(key=lambda item: (item["date"] or "", item["kind"], item["title"]))
    return events


async def attendee_map_for(db: AsyncSession, entry_ids: list[UUID]) -> dict[UUID, list[UUID]]:
    if not entry_ids:
        return {}
    links = (await db.scalars(select(CalendarEntryAttendee).where(CalendarEntryAttendee.entry_id.in_(entry_ids)))).all()
    out: dict[UUID, list[UUID]] = {}
    for link in links:
        out.setdefault(link.entry_id, []).append(link.user_id)
    return out


def mark_conflicts(entries: list[dict]) -> None:
    """Set conflicts[] on timed event entries that share an attendee and overlap."""
    timed = [e for e in entries if e.get("entry_type") == "event" and not e.get("all_day")]
    for i, a in enumerate(timed):
        conflicts = []
        for b in timed[i + 1 :]:
            if a.get("on_date") != b.get("on_date"):
                continue
            shared = set(a.get("attendee_ids") or []) & set(b.get("attendee_ids") or [])
            if not shared:
                continue
            if a.get("start_time") and b.get("start_time") and a.get("end_time") and b.get("end_time"):
                if a["start_time"] < b["end_time"] and b["start_time"] < a["end_time"]:
                    conflicts.append(b["entry_id"])
        a["conflicts"] = conflicts
