"""وارد کردن تقویم آبان ۱۴۰۵. اگر ماه وجود داشته باشد دوباره ساخته نمی‌شود."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.calendar.aban_1405 import HEADER, MONTH, YEAR, entry_rows, header_payload
from app.calendar.models import CalendarEntry, CalendarMonth


async def seed_content_calendar(db: AsyncSession, organization_id: UUID, created_by: UUID | None) -> dict:
    existing = await db.scalar(
        select(CalendarMonth).where(
            CalendarMonth.organization_id == organization_id,
            CalendarMonth.jalali_year == YEAR,
            CalendarMonth.jalali_month == MONTH,
        )
    )
    if existing is not None:
        return {"entries": 0, "skipped": True}
    db.add(
        CalendarMonth(
            organization_id=organization_id,
            jalali_year=YEAR,
            jalali_month=MONTH,
            title=HEADER["title"],
            payload=header_payload(),
            created_by=created_by,
        )
    )
    for row in entry_rows():
        db.add(CalendarEntry(organization_id=organization_id, created_by=created_by, **row))
    await db.flush()
    return {"entries": len(entry_rows()), "skipped": False}
