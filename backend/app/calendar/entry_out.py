"""Serialize calendar entries for API."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from uuid import UUID

from app.calendar.models import CalendarEntry
from app.calendar.recurrence import occurrence_key


def _combine_dt(on_date: date, t: time | None) -> str | None:
    if t is None:
        return None
    return datetime.combine(on_date, t, tzinfo=timezone.utc).isoformat()


def entry_out(
    row: CalendarEntry,
    names: dict[UUID, str],
    attendee_ids: list[UUID],
    occurrence_date: date | None = None,
) -> dict:
    on = occurrence_date or row.on_date
    label = row.title.strip() or row.topic
    late = on.isoformat() < date.today().isoformat() and row.status != "done"
    return {
        "id": occurrence_key(row.id, on) if occurrence_date else str(row.id),
        "entry_id": str(row.id),
        "on_date": on.isoformat(),
        "entry_type": row.entry_type,
        "title": label,
        "topic": row.topic,
        "tier": row.tier,
        "format": row.format,
        "channel": row.channel,
        "cta": row.cta,
        "kpi": row.kpi,
        "status": row.status,
        "production_status": row.production_status,
        "published_url": row.published_url,
        "all_day": row.all_day,
        "start_time": row.start_time.isoformat() if row.start_time else None,
        "end_time": row.end_time.isoformat() if row.end_time else None,
        "start": _combine_dt(on, row.start_time) if not row.all_day and row.start_time else on.isoformat(),
        "end": _combine_dt(on, row.end_time) if not row.all_day and row.end_time else on.isoformat(),
        "location": row.location,
        "notes": row.notes,
        "recurrence": row.recurrence,
        "recur_until": row.recur_until.isoformat() if row.recur_until else None,
        "recurrence_parent_id": str(row.recurrence_parent_id) if row.recurrence_parent_id else None,
        "campaign_id": str(row.campaign_id) if row.campaign_id else None,
        "assignee_id": str(row.assignee_id) if row.assignee_id else None,
        "assignee_name": names.get(row.assignee_id, "") if row.assignee_id else "",
        "attendee_ids": [str(uid) for uid in attendee_ids],
        "project_id": str(row.project_id) if row.project_id else None,
        "color_key": row.entry_type,
        "late": late,
        "kind": "content" if row.entry_type == "content" else "event",
    }
