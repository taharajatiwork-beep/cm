"""Expand calendar entries with recurrence into concrete dates."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from app.calendar.models import CalendarEntry


def iter_recurrence_dates(row: CalendarEntry, range_start: date, range_end: date) -> list[date]:
    if row.recurrence_parent_id:
        if range_start <= row.on_date <= range_end:
            return [row.on_date]
        return []
    if row.recurrence == "none" or not row.recur_until:
        if range_start <= row.on_date <= range_end:
            return [row.on_date]
        return []
    end = min(range_end, row.recur_until)
    cur = row.on_date
    out: list[date] = []
    while cur <= end:
        if cur >= range_start:
            out.append(cur)
        if row.recurrence == "daily":
            cur += timedelta(days=1)
        elif row.recurrence == "weekly":
            cur += timedelta(days=7)
        elif row.recurrence == "monthly":
            if cur.month == 12:
                cur = date(cur.year + 1, 1, cur.day)
            else:
                try:
                    cur = date(cur.year, cur.month + 1, cur.day)
                except ValueError:
                    cur = date(cur.year, cur.month + 2, 1) - timedelta(days=1)
        else:
            break
        if len(out) > 120:
            break
    return out


def occurrence_key(entry_id: UUID, on_date: date) -> str:
    return f"{entry_id}:{on_date.isoformat()}"
