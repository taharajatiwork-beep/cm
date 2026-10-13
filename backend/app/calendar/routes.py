"""خواندن و نوشتن تقویم محتوا — org.admin یا سرپرست/پرفورمنس با اسکوپ تیم."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.ai.llm import get_llm_client
from app.api.deps import AuthContext, get_current_user, handle_authz
from app.core.permissions import AuthorizationError, PermissionCode, require_any_permission, require_permission
from app.calendar.dates import jalali_month_length, jalali_to_gregorian
from app.calendar.models import CalendarEntry, CalendarMonth
from app.db.session import get_db
from app.models import Task, TaskAssignee, User, WorkItem
from app.perf.models import PmCampaign, PmPage, PmSmsSend, PmStory
from app.requests.models import Shoot, WorkProject, WorkRequest

router = APIRouter(prefix="/calendar", tags=["calendar"])

TIERS = ("long", "mid", "short", "reactive")
STATUSES = ("todo", "doing", "done")


def _is_calendar_admin(ctx: AuthContext) -> bool:
    return PermissionCode.ORG_ADMIN in ctx.permissions


def _require_calendar_read(ctx: AuthContext) -> None:
    if _is_calendar_admin(ctx):
        return
    try:
        require_any_permission(
            ctx.permissions,
            PermissionCode.REQUEST_TRIAGE,
            PermissionCode.REQUEST_MANAGE,
            PermissionCode.PERF_WRITE,
        )
    except AuthorizationError as exc:
        raise handle_authz(exc) from exc


def _require_calendar_write(ctx: AuthContext) -> None:
    _require_calendar_read(ctx)


def _team_ids_for_calendar(ctx: AuthContext) -> set[UUID]:
    ids: set[UUID] = set()
    if ctx.scope.team_id:
        ids.add(ctx.scope.team_id)
    ids.update(ctx.scope.team_ids or ())
    return ids


def _scoped_entries_stmt(org: UUID, start: date, end: date, ctx: AuthContext):
    stmt = (
        select(CalendarEntry)
        .where(CalendarEntry.organization_id == org, CalendarEntry.on_date >= start, CalendarEntry.on_date <= end)
        .order_by(CalendarEntry.on_date, CalendarEntry.created_at)
    )
    if _is_calendar_admin(ctx) or ctx.scope.is_org_wide or ctx.scope.level == "organization":
        return stmt
    team_ids = _team_ids_for_calendar(ctx)
    if not team_ids:
        return stmt.where(CalendarEntry.created_by == ctx.user.id)
    assignee = aliased(User)
    project = aliased(WorkProject)
    return (
        stmt.outerjoin(assignee, CalendarEntry.assignee_id == assignee.id)
        .outerjoin(project, CalendarEntry.project_id == project.id)
        .where(
            or_(
                CalendarEntry.created_by == ctx.user.id,
                assignee.team_id.in_(team_ids),
                project.team_id.in_(team_ids),
            )
        )
    )


async def _entry_in_scope(db: AsyncSession, row: CalendarEntry, ctx: AuthContext) -> bool:
    if row.organization_id != ctx.organization_id:
        return False
    if _is_calendar_admin(ctx) or ctx.scope.is_org_wide or ctx.scope.level == "organization":
        return True
    if row.created_by == ctx.user.id:
        return True
    team_ids = _team_ids_for_calendar(ctx)
    if not team_ids:
        return False
    if row.assignee_id:
        user = await db.get(User, row.assignee_id)
        if user and user.team_id in team_ids:
            return True
    if row.project_id:
        project = await db.get(WorkProject, row.project_id)
        if project and project.team_id in team_ids:
            return True
    return False


def _require_site_admin(ctx: AuthContext) -> None:
    """اکسل ماه و پیشنهاد LLM — فقط ادمین سایت."""
    try:
        require_permission(ctx.permissions, PermissionCode.ORG_ADMIN)
    except AuthorizationError as exc:
        raise handle_authz(exc) from exc


def _parse_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{label} تاریخ معتبر نیست") from exc


def _uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="شناسه نامعتبر است") from exc


class EntryIn(BaseModel):
    on_date: str
    tier: str = "long"
    format: str = ""
    channel: str = ""
    topic: str
    cta: str = ""
    kpi: str = ""
    status: str = "todo"
    campaign_id: str | None = None
    assignee_id: str | None = None
    project_id: str | None = None


class EntryPatch(BaseModel):
    on_date: str | None = None
    tier: str | None = None
    format: str | None = None
    channel: str | None = None
    topic: str | None = None
    cta: str | None = None
    kpi: str | None = None
    status: str | None = None
    campaign_id: str | None = None
    assignee_id: str | None = None
    project_id: str | None = None


class BulkIn(BaseModel):
    entries: list[EntryIn] = Field(default_factory=list)


class MonthIn(BaseModel):
    title: str = ""
    goal: str = ""
    logic: list[str] = Field(default_factory=list)
    weeks: list[dict] = Field(default_factory=list)
    mix: list[dict] = Field(default_factory=list)
    kpis: list[dict] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)


def _check(tier: str, status: str, topic: str) -> None:
    if tier not in TIERS:
        raise HTTPException(status_code=422, detail="نوع کمپین نامعتبر است")
    if status not in STATUSES:
        raise HTTPException(status_code=422, detail="وضعیت نامعتبر است")
    if not topic.strip():
        raise HTTPException(status_code=422, detail="موضوع لازم است")


def _entry_out(row: CalendarEntry, names: dict[UUID, str]) -> dict:
    return {
        "id": str(row.id),
        "on_date": row.on_date.isoformat(),
        "tier": row.tier,
        "format": row.format,
        "channel": row.channel,
        "topic": row.topic,
        "cta": row.cta,
        "kpi": row.kpi,
        "status": row.status,
        "campaign_id": str(row.campaign_id) if row.campaign_id else None,
        "assignee_id": str(row.assignee_id) if row.assignee_id else None,
        "assignee_name": names.get(row.assignee_id, "") if row.assignee_id else "",
        "project_id": str(row.project_id) if row.project_id else None,
    }


def _month_out(row: CalendarMonth | None) -> dict | None:
    if row is None:
        return None
    try:
        payload = json.loads(row.payload) if row.payload else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "year": row.jalali_year,
        "month": row.jalali_month,
        "title": row.title,
        "goal": payload.get("goal") or "",
        "logic": payload.get("logic") or [],
        "weeks": payload.get("weeks") or [],
        "mix": payload.get("mix") or [],
        "kpis": payload.get("kpis") or [],
        "rules": payload.get("rules") or [],
    }


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    start_at = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_at = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return start_at, end_at


def _day(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.date().isoformat()


def _status(value) -> str:
    return value.value if hasattr(value, "value") else str(value or "")


@router.get("")
async def calendar_range(
    date_from: str = Query(alias="from"),
    date_to: str = Query(alias="to"),
    year: int = Query(0),
    month: int = Query(0),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_calendar_read(ctx)
    start = _parse_date(date_from, "از")
    end = _parse_date(date_to, "تا")
    if end < start or (end - start).days > 62:
        raise HTTPException(status_code=422, detail="بازه باید حداکثر دو ماه باشد")
    org = ctx.organization_id
    names = {
        row.id: row.full_name
        for row in (await db.scalars(select(User).where(User.organization_id == org))).all()
    }
    entries = (await db.scalars(_scoped_entries_stmt(org, start, end, ctx))).all()
    header = None
    if 1300 <= year <= 1500 and 1 <= month <= 12:
        header = await db.scalar(
            select(CalendarMonth).where(
                CalendarMonth.organization_id == org,
                CalendarMonth.jalali_year == year,
                CalendarMonth.jalali_month == month,
            )
        )
    return {
        "entries": [_entry_out(row, names) for row in entries],
        "month": _month_out(header),
        "events": await _events(db, org, start, end, names),
    }


async def _events(db: AsyncSession, org: UUID, start: date, end: date, names: dict[UUID, str]) -> list[dict]:
    events: list[dict] = []
    start_at, end_at = _bounds(start, end)

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
    for row in tasks:
        people = [row.owner_id, *assignee_ids.get(row.id, [])]
        person_id = people[0] if people else None
        label = "، ".join(dict.fromkeys(names.get(uid, "") for uid in people if names.get(uid)))
        events.append(
            {
                "kind": "task",
                "date": _day(row.deadline),
                "title": row.title,
                "person": label,
                "person_id": str(person_id) if person_id else None,
                "link": f"/projects/{row.project_id}" if row.project_id else "/my-work",
                "status": _status(row.status),
                "id": str(row.id),
            }
        )

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
        events.append(
            {
                "kind": "work",
                "date": _day(row.deadline),
                "title": row.title,
                "person": names.get(row.owner_id, ""),
                "person_id": str(row.owner_id),
                "link": "/projects",
                "status": _status(row.status),
                "id": str(row.id),
            }
        )

    projects = (
        await db.scalars(
            select(WorkProject).where(
                WorkProject.organization_id == org,
                WorkProject.due_date.is_not(None),
                WorkProject.due_date >= start,
                WorkProject.due_date <= end,
            )
        )
    ).all()
    for row in projects:
        events.append(
            {
                "kind": "project",
                "date": row.due_date.isoformat() if row.due_date else None,
                "title": row.title,
                "person": names.get(row.lead_user_id, "") if row.lead_user_id else "",
                "person_id": str(row.lead_user_id) if row.lead_user_id else None,
                "link": f"/projects/{row.id}",
                "status": row.status,
                "id": str(row.id),
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
        events.append(
            {
                "kind": "request",
                "date": row.due_date.isoformat() if row.due_date else None,
                "title": row.title,
                "person": names.get(row.requested_by, "") if row.requested_by else "",
                "person_id": str(row.requested_by) if row.requested_by else None,
                "link": "/requests",
                "status": row.status,
                "id": str(row.id),
            }
        )

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
            }
        )

    events.sort(key=lambda item: (item["date"] or "", item["kind"], item["title"]))
    return events


def _apply(row: CalendarEntry, body: EntryIn | EntryPatch, partial: bool) -> None:
    data = body.model_dump(exclude_unset=partial)
    if "on_date" in data and data["on_date"] is not None:
        row.on_date = _parse_date(data["on_date"], "تاریخ")
    if "topic" in data and data["topic"] is not None:
        row.topic = data["topic"].strip()
    for key in ("tier", "format", "channel", "cta", "kpi", "status"):
        if key in data and data[key] is not None:
            setattr(row, key, data[key].strip() if isinstance(data[key], str) else data[key])
    for key in ("campaign_id", "assignee_id", "project_id"):
        if key in data:
            setattr(row, key, _uuid(data[key]))
    _check(row.tier, row.status, row.topic)


@router.post("/entries", status_code=201)
async def create_entry(
    body: EntryIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_calendar_write(ctx)
    row = CalendarEntry(organization_id=ctx.organization_id, on_date=date.today(), topic="", created_by=ctx.user.id)
    _apply(row, body, partial=False)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    names = {}
    if row.assignee_id:
        user = await db.get(User, row.assignee_id)
        if user:
            names[user.id] = user.full_name
    return _entry_out(row, names)


@router.post("/entries/bulk", status_code=201)
async def create_entries(
    body: BulkIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_calendar_write(ctx)
    if len(body.entries) > 40:
        raise HTTPException(status_code=422, detail="حداکثر ۴۰ ردیف در یک بار")
    org = ctx.organization_id
    existing = set(
        (
            await db.scalars(select(CalendarEntry.on_date).where(CalendarEntry.organization_id == org))
        ).all()
    )
    added = 0
    for item in body.entries:
        on_date = _parse_date(item.on_date, "تاریخ")
        if on_date in existing:
            continue
        row = CalendarEntry(organization_id=org, on_date=on_date, topic="", created_by=ctx.user.id)
        _apply(row, item, partial=False)
        db.add(row)
        existing.add(on_date)
        added += 1
    await db.commit()
    return {"added": added}


@router.patch("/entries/{entry_id}")
async def patch_entry(
    entry_id: UUID,
    body: EntryPatch,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_calendar_write(ctx)
    row = await db.get(CalendarEntry, entry_id)
    if row is None or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="ردیف پیدا نشد")
    if not await _entry_in_scope(db, row, ctx):
        raise HTTPException(status_code=404, detail="ردیف پیدا نشد")
    _apply(row, body, partial=True)
    await db.commit()
    await db.refresh(row)
    names = {}
    if row.assignee_id:
        user = await db.get(User, row.assignee_id)
        if user:
            names[user.id] = user.full_name
    return _entry_out(row, names)


@router.delete("/entries/{entry_id}", status_code=204)
async def delete_entry(
    entry_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_calendar_write(ctx)
    row = await db.get(CalendarEntry, entry_id)
    if row is None or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="ردیف پیدا نشد")
    if not await _entry_in_scope(db, row, ctx):
        raise HTTPException(status_code=404, detail="ردیف پیدا نشد")
    await db.delete(row)
    await db.commit()


@router.put("/month/{year}/{month}")
async def save_month(
    year: int,
    month: int,
    body: MonthIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_calendar_write(ctx)
    if not (1300 <= year <= 1500 and 1 <= month <= 12):
        raise HTTPException(status_code=422, detail="ماه نامعتبر است")
    org = ctx.organization_id
    row = await db.scalar(
        select(CalendarMonth).where(
            CalendarMonth.organization_id == org,
            CalendarMonth.jalali_year == year,
            CalendarMonth.jalali_month == month,
        )
    )
    payload = json.dumps(body.model_dump(exclude={"title"}), ensure_ascii=False)
    if row is None:
        row = CalendarMonth(
            organization_id=org,
            jalali_year=year,
            jalali_month=month,
            title=body.title.strip(),
            payload=payload,
            created_by=ctx.user.id,
        )
        db.add(row)
    else:
        row.title = body.title.strip()
        row.payload = payload
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="این ماه قبلاً ثبت شده") from exc
    await db.refresh(row)
    return _month_out(row)


@router.post("/month/{year}/{month}/draft")
async def draft_month(
    year: int,
    month: int,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """پیش‌نویس ۳۰روزه از کمپین‌های فعال. ذخیره نمی‌شود."""
    _require_calendar_write(ctx)
    if not (1300 <= year <= 1500 and 1 <= month <= 12):
        raise HTTPException(status_code=422, detail="ماه نامعتبر است")
    length = jalali_month_length(year, month)
    campaigns = (
        await db.scalars(
            select(PmCampaign)
            .where(PmCampaign.organization_id == ctx.organization_id, PmCampaign.status == "active")
            .order_by(PmCampaign.code)
        )
    ).all()
    client = get_llm_client()
    if client is not None and campaigns:
        lines = "\n".join(f"- {row.code} {row.title} ({row.brand})" for row in campaigns[:12])
        try:
            raw = await client.chat_json(
                system=(
                    "تو برنامه‌ریز محتوای خودرویی هستی. فقط JSON برگردان: "
                    '{"entries":[{"day":1,"tier":"long|mid|short|reactive","format":"","channel":"","topic":"","cta":"","kpi":""}]}'
                    " عدد و آمار نساز. tier فقط همان چهار مقدار."
                ),
                user=f"برای ماه {year}/{month} با {length} روز، از این کمپین‌ها برنامه بساز:\n{lines}",
                temperature=0.3,
            )
            drafted = _from_llm(raw, year, month, length)
            if drafted:
                return {"source": "llm", "entries": drafted}
        except Exception:
            pass
    return {"source": "template", "entries": _template(campaigns, year, month, length)}


def _from_llm(raw, year: int, month: int, length: int) -> list[dict]:
    rows = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            day = int(row.get("day") or 0)
        except (TypeError, ValueError):
            continue
        if day < 1 or day > length:
            continue
        tier = row.get("tier") if row.get("tier") in TIERS else "long"
        topic = str(row.get("topic") or "").strip()
        if not topic:
            continue
        out.append(
            {
                "on_date": jalali_to_gregorian(year, month, day).isoformat(),
                "tier": tier,
                "format": str(row.get("format") or "")[:80],
                "channel": str(row.get("channel") or "")[:120],
                "topic": topic[:400],
                "cta": str(row.get("cta") or "")[:200],
                "kpi": str(row.get("kpi") or "")[:120],
                "status": "todo",
            }
        )
    return out


def _template(campaigns: list[PmCampaign], year: int, month: int, length: int) -> list[dict]:
    cycle = ("long", "mid", "short", "reactive")
    formats = ("Post", "Story", "Reel", "SMS")
    channels = ("Instagram", "Story", "Instagram", "SMS")
    out = []
    for day in range(1, length + 1):
        camp = campaigns[(day - 1) % len(campaigns)] if campaigns else None
        topic = f"{camp.code} — {camp.title}" if camp else "جای خالی برای خبر یا بخشنامه همان هفته"
        out.append(
            {
                "on_date": jalali_to_gregorian(year, month, day).isoformat(),
                "tier": cycle[(day - 1) % 4],
                "format": formats[(day - 1) % 4],
                "channel": channels[(day - 1) % 4],
                "topic": topic,
                "cta": "دریافت شرایط" if camp else "",
                "kpi": "Lead" if camp else "",
                "status": "todo",
            }
        )
    return out


@router.get("/export.xlsx")
async def export_xlsx(
    date_from: str = Query(alias="from"),
    date_to: str = Query(alias="to"),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_site_admin(ctx)
    start = _parse_date(date_from, "از")
    end = _parse_date(date_to, "تا")
    rows = (
        await db.scalars(
            select(CalendarEntry)
            .where(
                CalendarEntry.organization_id == ctx.organization_id,
                CalendarEntry.on_date >= start,
                CalendarEntry.on_date <= end,
            )
            .order_by(CalendarEntry.on_date)
        )
    ).all()
    book = Workbook()
    sheet = book.active
    if sheet is None:
        raise HTTPException(status_code=500, detail="فایل ساخته نشد")
    sheet.title = "تقویم"
    sheet.append(["تاریخ", "کمپین", "فرمت", "کانال", "موضوع", "CTA", "KPI", "وضعیت"])
    tier_fa = {"long": "بلندمدت", "mid": "میان‌مدت", "short": "کوتاه‌مدت", "reactive": "واکنشی"}
    status_fa = {"todo": "برنامه‌ریزی", "doing": "در جریان", "done": "انجام شد"}
    for row in rows:
        sheet.append(
            [
                row.on_date.isoformat(),
                tier_fa.get(row.tier, row.tier),
                row.format,
                row.channel,
                row.topic,
                row.cta,
                row.kpi,
                status_fa.get(row.status, row.status),
            ]
        )
    buffer = BytesIO()
    book.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=calendar.xlsx"},
    )
