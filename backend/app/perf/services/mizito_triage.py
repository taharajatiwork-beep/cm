"""لیست رسیدگی کارت‌های فعال میزیتو برای مدیر مارکتینگ.

فقط از عکس ذخیره‌شده خوانده می‌شود؛ به میزیتو وصل نمی‌شود و چیزی نمی‌نویسد.
پرچم‌ها: بدون کد (فقط پروژه‌های پرفورمنس و کمپین)، بیش از N روز بدون تغییر، بدون مسئول، مهلت گذشته.
«بدون مهلت» پرچم نیست، چون مهلت در میزیتو تقریباً هیچ‌وقت پر نمی‌شود.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.perf.services.common import now as utc_now
from app.perf.services.mizito import INACTIVE, board_status, normalize, saved_mizito

FLAGS = ("no_code", "stuck", "no_assignee", "overdue")
DEFAULT_DAYS = 14
_CODE_PROJECTS = ("پرفورمنس", "کمپین")
_LIST_LIMIT = 200


def clamp_days(value: Any) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return max(1, min(365, days))


def _when(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else None


def expects_code(project: Any) -> bool:
    text = normalize(project)
    return any(normalize(name) in text for name in _CODE_PROJECTS)


def _active(card: dict) -> bool:
    if card.get("completed"):
        return False
    status = str(card.get("status") or board_status(card.get("board")))
    return status not in INACTIVE and card.get("active", True) is not False


def triage_view(cards: list[dict], days: int, now: datetime) -> dict:
    days = clamp_days(days)
    counts = dict.fromkeys(FLAGS, 0)
    checked = 0
    found: list[dict] = []
    for card in cards:
        if not isinstance(card, dict) or not _active(card):
            continue
        checked += 1
        modified = _when(card.get("modified_at"))
        deadline = _when(card.get("deadline"))
        idle = (now - modified).days if modified else None
        flags = []
        if expects_code(card.get("project")) and not str(card.get("code") or "").strip():
            flags.append("no_code")
        if idle is not None and idle > days:
            flags.append("stuck")
        # عکس‌های قدیمی فیلد مسئول ندارند؛ آنجا «بدون مسئول» نمی‌گوییم.
        if "assignees" in card and not card.get("assignees"):
            flags.append("no_assignee")
        if deadline and deadline < now:
            flags.append("overdue")
        if not flags:
            continue
        for flag in flags:
            counts[flag] += 1
        assignees = card.get("assignees")
        found.append(
            {
                "id": str(card.get("id") or ""),
                "title": str(card.get("title") or ""),
                "project": str(card.get("project") or ""),
                "board": str(card.get("board") or ""),
                "status": str(card.get("status") or board_status(card.get("board"))),
                "code": str(card.get("code") or ""),
                "flags": flags,
                "days_since_change": idle,
                "modified_at": card.get("modified_at"),
                "deadline": card.get("deadline"),
                "assignees": len(assignees) if isinstance(assignees, list) else None,
            }
        )
    # بیشترین پرچم اول، بعد قدیمی‌ترین تغییر؛ کارت بی‌تاریخ آخر.
    found.sort(
        key=lambda row: (
            -len(row["flags"]),
            -(row["days_since_change"] if row["days_since_change"] is not None else -1),
        )
    )
    return {
        "days": days,
        "now": now.isoformat(),
        "checked": checked,
        "counts": counts,
        "total": len(found),
        "cards": found[:_LIST_LIMIT],
    }


async def mizito_triage(
    db: AsyncSession, organization_id: UUID, days: int | None = None, now: datetime | None = None
) -> dict:
    data = await saved_mizito(db, organization_id)
    limit = clamp_days(days if days is not None else get_settings().perf_mizito_stuck_days)
    view = triage_view(data.get("cards") or [], limit, now or utc_now())
    return {"connected": bool(data.get("connected")), "read_at": data.get("read_at"), **view}
