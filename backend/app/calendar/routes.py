"""خواندن و نوشتن تقویم محتوا — org.admin یا سرپرست/پرفورمنس با اسکوپ تیم."""

from __future__ import annotations

import json
from datetime import date, time
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.ai.llm import get_llm_client
from app.api.deps import AuthContext, get_current_user, handle_authz
from app.core.permissions import AuthorizationError, PermissionCode, require_any_permission, require_permission
from app.calendar.dates import jalali_month_length, jalali_to_gregorian
from app.calendar.entry_out import entry_out
from app.calendar.events import (
    attendee_map_for,
    expand_entries,
    gather_marketing_events,
    gather_mizito_events,
    gather_work_events,
    mark_conflicts,
)
from app.calendar.models import CalendarEntry, CalendarEntryAttendee, CalendarMonth, CalendarOccasion
from app.calendar.occasions import occasions_in_range
from app.db.session import get_db
from app.models import User
from app.perf.models import PmCampaign
from app.requests.models import WorkProject

router = APIRouter(prefix="/calendar", tags=["calendar"])

TIERS = ("long", "mid", "short", "reactive")
STATUSES = ("todo", "doing", "done")


def _is_calendar_admin(ctx: AuthContext) -> bool:
    return PermissionCode.ORG_ADMIN in ctx.permissions


def _calendar_read_only(ctx: AuthContext) -> bool:
    if _is_calendar_admin(ctx):
        return False
    if PermissionCode.REQUEST_TRIAGE in ctx.permissions:
        return False
    if PermissionCode.REQUEST_MANAGE in ctx.permissions:
        return False
    if PermissionCode.PERF_WRITE in ctx.permissions:
        return False
    return PermissionCode.CALENDAR_READ in ctx.permissions


def _require_calendar_read(ctx: AuthContext) -> None:
    if _is_calendar_admin(ctx):
        return
    try:
        require_any_permission(
            ctx.permissions,
            PermissionCode.CALENDAR_READ,
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
    in_range = and_(CalendarEntry.on_date >= start, CalendarEntry.on_date <= end)
    recurring = and_(
        CalendarEntry.recurrence != "none",
        CalendarEntry.recurrence_parent_id.is_(None),
        CalendarEntry.recur_until.is_not(None),
        CalendarEntry.recur_until >= start,
        CalendarEntry.on_date <= end,
    )
    stmt = (
        select(CalendarEntry)
        .where(CalendarEntry.organization_id == org, or_(in_range, recurring))
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
    entry_type: str = "content"
    title: str = ""
    start_time: str | None = None
    end_time: str | None = None
    all_day: bool = True
    location: str = ""
    notes: str = ""
    tier: str = "long"
    format: str = ""
    channel: str = ""
    topic: str = ""
    cta: str = ""
    kpi: str = ""
    status: str = "todo"
    production_status: str = "idea"
    published_url: str = ""
    recurrence: str = "none"
    recur_until: str | None = None
    campaign_id: str | None = None
    assignee_id: str | None = None
    project_id: str | None = None
    attendee_ids: list[str] = Field(default_factory=list)


class EntryPatch(BaseModel):
    on_date: str | None = None
    entry_type: str | None = None
    title: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    all_day: bool | None = None
    location: str | None = None
    notes: str | None = None
    tier: str | None = None
    format: str | None = None
    channel: str | None = None
    topic: str | None = None
    cta: str | None = None
    kpi: str | None = None
    status: str | None = None
    production_status: str | None = None
    published_url: str | None = None
    recurrence: str | None = None
    recur_until: str | None = None
    campaign_id: str | None = None
    assignee_id: str | None = None
    project_id: str | None = None
    attendee_ids: list[str] | None = None
    scope: str | None = None
    occurrence_date: str | None = None


class OccasionIn(BaseModel):
    on_date: str
    title: str
    kind: str = "marketing"
    is_off: bool = False


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


ENTRY_TYPES = ("content", "event")
RECURRENCE = ("none", "daily", "weekly", "monthly")
PRODUCTION = ("idea", "draft", "design", "review", "approved", "published")


def _check(row: CalendarEntry) -> None:
    if row.entry_type not in ENTRY_TYPES:
        raise HTTPException(status_code=422, detail="نوع ردیف نامعتبر است")
    if row.tier not in TIERS:
        raise HTTPException(status_code=422, detail="نوع کمپین نامعتبر است")
    if row.status not in STATUSES:
        raise HTTPException(status_code=422, detail="وضعیت نامعتبر است")
    if row.recurrence not in RECURRENCE:
        raise HTTPException(status_code=422, detail="تکرار نامعتبر است")
    if row.production_status not in PRODUCTION:
        raise HTTPException(status_code=422, detail="وضعیت تولید نامعتبر است")
    label = (row.title or row.topic or "").strip()
    if not label:
        raise HTTPException(status_code=422, detail="عنوان یا موضوع لازم است")
    if not row.topic.strip():
        row.topic = label


async def _entry_response(db: AsyncSession, row: CalendarEntry, names: dict[UUID, str]) -> dict:
    amap = await attendee_map_for(db, [row.id])
    return entry_out(row, names, amap.get(row.id, []))


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    try:
        parts = value.split(":")
        return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    except (ValueError, IndexError):
        raise HTTPException(status_code=422, detail="زمان نامعتبر است") from None


async def _set_attendees(db: AsyncSession, entry_id: UUID, user_ids: list[UUID]) -> None:
    existing = list((await db.scalars(select(CalendarEntryAttendee).where(CalendarEntryAttendee.entry_id == entry_id))).all())
    for row in existing:
        await db.delete(row)
    for uid in user_ids:
        db.add(CalendarEntryAttendee(entry_id=entry_id, user_id=uid))


async def _org_user_names(db: AsyncSession, org: UUID) -> dict[UUID, str]:
    return {
        row.id: row.full_name
        for row in (await db.scalars(select(User).where(User.organization_id == org))).all()
    }


def _copy_entry(dst: CalendarEntry, src: CalendarEntry) -> None:
    for key in (
        "entry_type",
        "title",
        "start_time",
        "end_time",
        "all_day",
        "location",
        "notes",
        "tier",
        "format",
        "channel",
        "topic",
        "cta",
        "kpi",
        "status",
        "production_status",
        "published_url",
        "campaign_id",
        "assignee_id",
        "project_id",
    ):
        setattr(dst, key, getattr(src, key))


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


@router.get("")
async def calendar_range(
    date_from: str = Query(alias="from"),
    date_to: str = Query(alias="to"),
    year: int = Query(0),
    month: int = Query(0),
    layers: str | None = Query(None),
    mine: bool = Query(False),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_calendar_read(ctx)
    start = _parse_date(date_from, "از")
    end = _parse_date(date_to, "تا")
    if end < start or (end - start).days > 62:
        raise HTTPException(status_code=422, detail="بازه باید حداکثر دو ماه باشد")
    org = ctx.organization_id
    layer_set = {part.strip() for part in (layers or "").split(",") if part.strip()} or None
    names = {
        row.id: row.full_name
        for row in (await db.scalars(select(User).where(User.organization_id == org))).all()
    }
    raw_entries = list((await db.scalars(_scoped_entries_stmt(org, start, end, ctx))).all())
    if mine:
        raw_entries = [
            row
            for row in raw_entries
            if row.created_by == ctx.user.id or row.assignee_id == ctx.user.id
        ]
    entry_ids = [row.id for row in raw_entries]
    amap = await attendee_map_for(db, entry_ids)
    expanded = await expand_entries(db, raw_entries, start, end, names, amap)
    if layer_set and "content" not in layer_set and "event" not in layer_set:
        expanded = []
    elif layer_set:
        expanded = [e for e in expanded if e.get("entry_type") in layer_set or e.get("kind") in layer_set]
    mark_conflicts(expanded)
    work_events, load_map = await gather_work_events(db, org, start, end, names, ctx, layer_set, mine)
    mizito = await gather_mizito_events(db, org, start, end, names, ctx, layer_set, mine)
    marketing = await gather_marketing_events(db, org, start, end, names, ctx, layer_set, mine)
    occasions = await occasions_in_range(db, org, start, end) if (not layer_set or "holiday" in layer_set) else []
    header = None
    if 1300 <= year <= 1500 and 1 <= month <= 12:
        header = await db.scalar(
            select(CalendarMonth).where(
                CalendarMonth.organization_id == org,
                CalendarMonth.jalali_year == year,
                CalendarMonth.jalali_month == month,
            )
        )
    load = [{"person_id": pid, "date": day, "count": count} for (pid, day), count in load_map.items()]
    return {
        "entries": expanded,
        "month": _month_out(header),
        "events": work_events + mizito + marketing,
        "occasions": occasions,
        "load": load,
    }


def _apply(row: CalendarEntry, body: EntryIn | EntryPatch, partial: bool) -> None:
    data = body.model_dump(exclude_unset=partial, exclude={"attendee_ids", "scope", "occurrence_date"})
    if "on_date" in data and data["on_date"] is not None:
        row.on_date = _parse_date(data["on_date"], "تاریخ")
    if "recur_until" in data:
        row.recur_until = _parse_date(data["recur_until"], "تا تاریخ") if data["recur_until"] else None
    if "topic" in data and data["topic"] is not None:
        row.topic = data["topic"].strip()
    if "title" in data and data["title"] is not None:
        row.title = data["title"].strip()
    if "start_time" in data:
        row.start_time = _parse_time(data["start_time"])
    if "end_time" in data:
        row.end_time = _parse_time(data["end_time"])
    for key in (
        "entry_type",
        "tier",
        "format",
        "channel",
        "cta",
        "kpi",
        "status",
        "production_status",
        "published_url",
        "recurrence",
        "location",
        "notes",
    ):
        if key in data and data[key] is not None:
            setattr(row, key, data[key].strip() if isinstance(data[key], str) else data[key])
    if "all_day" in data and data["all_day"] is not None:
        row.all_day = data["all_day"]
    for key in ("campaign_id", "assignee_id", "project_id"):
        if key in data:
            setattr(row, key, _uuid(data[key]))
    _check(row)


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
    await db.flush()
    if body.attendee_ids:
        await _set_attendees(db, row.id, [_uuid(uid) for uid in body.attendee_ids if uid])
    await db.commit()
    await db.refresh(row)
    names = await _org_user_names(db, ctx.organization_id)
    return await _entry_response(db, row, names)


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
    existing_rows = (
        await db.scalars(select(CalendarEntry).where(CalendarEntry.organization_id == org))
    ).all()
    existing_keys = {(row.on_date, (row.topic or row.title or "").strip().lower()) for row in existing_rows}
    added = 0
    for item in body.entries:
        on_date = _parse_date(item.on_date, "تاریخ")
        label = (item.topic or item.title or "").strip().lower()
        if not label:
            continue
        key = (on_date, label)
        if key in existing_keys:
            continue
        row = CalendarEntry(
            organization_id=org,
            on_date=on_date,
            topic="",
            production_status=item.production_status or "idea",
            created_by=ctx.user.id,
        )
        _apply(row, item, partial=False)
        if not row.production_status:
            row.production_status = "idea"
        db.add(row)
        existing_keys.add(key)
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
    org = ctx.organization_id
    names = await _org_user_names(db, org)

    if body.scope == "all" and row.recurrence_parent_id:
        parent = await db.get(CalendarEntry, row.recurrence_parent_id)
        if parent is None or parent.organization_id != org:
            raise HTTPException(status_code=404, detail="ردیف پیدا نشد")
        row = parent

    if body.scope == "this" and row.recurrence != "none" and not row.recurrence_parent_id:
        occ = _parse_date(body.occurrence_date, "تاریخ") if body.occurrence_date else row.on_date
        exc = CalendarEntry(
            organization_id=org,
            on_date=occ,
            topic="",
            recurrence="none",
            recur_until=None,
            recurrence_parent_id=row.id,
            created_by=ctx.user.id,
        )
        _copy_entry(exc, row)
        _apply(exc, body, partial=True)
        db.add(exc)
        await db.flush()
        if body.attendee_ids is not None:
            await _set_attendees(db, exc.id, [_uuid(uid) for uid in body.attendee_ids if uid])
        await db.commit()
        await db.refresh(exc)
        return await _entry_response(db, exc, names)

    _apply(row, body, partial=True)
    if body.attendee_ids is not None:
        await _set_attendees(db, row.id, [_uuid(uid) for uid in body.attendee_ids if uid])
    await db.commit()
    await db.refresh(row)
    return await _entry_response(db, row, names)


@router.get("/occasions")
async def list_occasions(
    date_from: str = Query(alias="from"),
    date_to: str = Query(alias="to"),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_calendar_read(ctx)
    start = _parse_date(date_from, "از")
    end = _parse_date(date_to, "تا")
    return await occasions_in_range(db, ctx.organization_id, start, end)


@router.post("/occasions", status_code=201)
async def create_occasion(
    body: OccasionIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _is_calendar_admin(ctx):
        raise HTTPException(status_code=403, detail="فقط ادمین سازمان")
    if body.kind not in ("official", "religious", "marketing"):
        raise HTTPException(status_code=422, detail="نوع مناسبت نامعتبر است")
    row = CalendarOccasion(
        organization_id=ctx.organization_id,
        on_date=_parse_date(body.on_date, "تاریخ"),
        title=body.title.strip(),
        kind=body.kind,
        is_off=body.is_off,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {
        "id": str(row.id),
        "on_date": row.on_date.isoformat(),
        "title": row.title,
        "kind": row.kind,
        "is_off": row.is_off,
        "global": False,
    }


@router.delete("/occasions/{occasion_id}", status_code=204)
async def delete_occasion(
    occasion_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _is_calendar_admin(ctx):
        raise HTTPException(status_code=403, detail="فقط ادمین سازمان")
    row = await db.get(CalendarOccasion, occasion_id)
    if row is None or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="مناسبت پیدا نشد")
    await db.delete(row)
    await db.commit()


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
                "production_status": "idea",
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
                "production_status": "idea",
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
