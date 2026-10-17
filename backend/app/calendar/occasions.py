"""Global and org calendar occasions."""

from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.calendar.models import CalendarOccasion
from app.calendar.occasions_1405 import global_occasions_1405
from uuid import UUID


async def ensure_global_occasions(db: AsyncSession) -> None:
    count = await db.scalar(select(CalendarOccasion.id).where(CalendarOccasion.organization_id.is_(None)).limit(1))
    if count is not None:
        return
    for row in global_occasions_1405():
        db.add(
            CalendarOccasion(
                organization_id=None,
                on_date=date.fromisoformat(row["on_date"]),
                title=row["title"],
                kind=row["kind"],
                is_off=row["is_off"],
            )
        )
    await db.flush()


async def occasions_in_range(db: AsyncSession, org: UUID, start: date, end: date) -> list[dict]:
    await ensure_global_occasions(db)
    rows = (
        await db.scalars(
            select(CalendarOccasion).where(
                CalendarOccasion.on_date >= start,
                CalendarOccasion.on_date <= end,
                or_(CalendarOccasion.organization_id.is_(None), CalendarOccasion.organization_id == org),
            )
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "on_date": row.on_date.isoformat(),
            "title": row.title,
            "kind": row.kind,
            "is_off": row.is_off,
            "global": row.organization_id is None,
        }
        for row in rows
    ]
