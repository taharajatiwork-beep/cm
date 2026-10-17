"""AI Lab snapshots from Novin Hub / Vardast rollups (GET-only aggregates)."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_lab.schemas import SocialInboxReviewIn
from app.perf.services.social_analytics import rollup_for_ai_lab, social_overview
from app.perf.services.social_report import build_social_report


def _parse_day(text: str) -> date:
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {text}") from None


async def social_inbox_review_snapshot(db: AsyncSession, org: UUID, inp: SocialInboxReviewIn) -> dict:
    start = _parse_day(inp.from_date)
    end = _parse_day(inp.to_date)
    if end < start:
        raise HTTPException(status_code=400, detail="to_date must be on or after from_date")
    overview = await social_overview(db, org, refresh=False)
    snap = rollup_for_ai_lab(overview, from_date=inp.from_date, to_date=inp.to_date, brand=inp.brand)
    try:
        snap["daily_report"] = await build_social_report(db, org, inp.from_date, inp.to_date)
    except HTTPException:
        snap["daily_report"] = None
    week_start = (end - timedelta(days=6)).isoformat()
    if week_start < inp.from_date:
        week_start = inp.from_date
    try:
        snap["weekly_trend"] = await build_social_report(db, org, week_start, inp.to_date)
    except HTTPException:
        snap["weekly_trend"] = None
    return snap
