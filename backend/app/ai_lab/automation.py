"""Scheduled and anomaly-triggered AI Lab tasks."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_lab.models import AiTask
from app.ai_lab.service import create_ai_task
from app.ai_lab.snapshots import _div, _in_range, _sms_in_range
from app.core.config import get_settings
from app.models import User
from app.perf.models import PmCampaign, PmCost, PmLead, PmSmsSend, PmStory
from app.perf.services.reports import placement_live


async def _schedule_user(db: AsyncSession, organization_id: UUID) -> User | None:
    settings = get_settings()
    email = (settings.ai_lab_schedule_user_email or "").strip().lower()
    if not email:
        return None
    return await db.scalar(select(User).where(User.organization_id == organization_id, User.email == email))


async def run_weekly_period_reviews(db: AsyncSession, organization_id: UUID) -> int:
    settings = get_settings()
    if not settings.ai_lab_enabled or not settings.ai_lab_weekly_enabled:
        return 0
    user = await _schedule_user(db, organization_id)
    if not user:
        return 0
    today = date.today()
    if today.weekday() != settings.ai_lab_weekly_weekday:
        return 0
    week_start = today - timedelta(days=today.weekday())
    existing = await db.scalar(
        select(AiTask.id).where(
            AiTask.organization_id == organization_id,
            AiTask.kind == "period_review",
            AiTask.trigger == "scheduled",
            AiTask.created_at >= datetime.combine(week_start, datetime.min.time(), tzinfo=UTC),
        )
    )
    if existing:
        return 0
    end = today
    start = end - timedelta(days=6)
    await create_ai_task(
        db,
        organization_id=organization_id,
        user_id=user.id,
        kind="period_review",
        input_data={"from_date": start.isoformat(), "to_date": end.isoformat(), "brand": ""},
        trigger="scheduled",
    )
    return 1


async def _campaign_metrics(
    db: AsyncSession,
    org: UUID,
    campaign_id: UUID,
    start: date,
    end: date,
) -> tuple[float | None, int]:
    sends = list(
        (
            await db.scalars(
                select(PmSmsSend).where(
                    PmSmsSend.organization_id == org,
                    PmSmsSend.campaign_id == campaign_id,
                )
            )
        ).all()
    )
    stories = list(
        (
            await db.scalars(
                select(PmStory).where(PmStory.organization_id == org, PmStory.campaign_id == campaign_id)
            )
        ).all()
    )
    costs = list((await db.scalars(select(PmCost).where(PmCost.organization_id == org))).all())
    leads = list(
        (
            await db.scalars(
                select(PmLead).where(PmLead.organization_id == org, PmLead.campaign_id == campaign_id)
            )
        ).all()
    )
    sms_cost = sum(row.cost_toman or 0 for row in sends if _sms_in_range(row.sent_at, start, end))
    sms_leads = sum(row.leads or 0 for row in sends if _sms_in_range(row.sent_at, start, end))
    story_cost = sum(
        row.cost_toman or 0
        for row in stories
        if placement_live(row) and _in_range(row.published_on, start, end)
    )
    story_leads = sum(
        row.leads or 0
        for row in stories
        if placement_live(row) and _in_range(row.published_on, start, end)
    )
    ledger = sum(
        row.amount_toman or 0
        for row in costs
        if row.counts_for_cpl and _in_range(row.spent_on, start, end)
    )
    imported = sum(
        row.quantity or 1 for row in leads if _in_range(row.occurred_on, start, end)
    )
    total_cost = sms_cost + story_cost + ledger
    lead_count = imported or (sms_leads + story_leads)
    return _div(total_cost, lead_count), lead_count


async def run_anomaly_campaign_reviews(db: AsyncSession, organization_id: UUID) -> int:
    settings = get_settings()
    if not settings.ai_lab_enabled or not settings.ai_lab_anomaly_enabled:
        return 0
    user = await _schedule_user(db, organization_id)
    if not user:
        return 0
    today = date.today()
    recent_cutoff = datetime.now(UTC) - timedelta(days=3)
    created = 0
    campaigns = list(
        (
            await db.scalars(
                select(PmCampaign).where(
                    PmCampaign.organization_id == organization_id,
                    PmCampaign.status == "active",
                )
            )
        ).all()
    )
    for camp in campaigns:
        dup = await db.scalar(
            select(AiTask.id).where(
                AiTask.organization_id == organization_id,
                AiTask.kind == "campaign_review",
                AiTask.created_at >= recent_cutoff,
                AiTask.input_json.contains(str(camp.id)),
            )
        )
        if dup:
            continue
        cpl_7, leads_7 = await _campaign_metrics(db, organization_id, camp.id, today - timedelta(days=6), today)
        cpl_28, leads_28 = await _campaign_metrics(
            db, organization_id, camp.id, today - timedelta(days=27), today - timedelta(days=7)
        )
        anomaly: dict = {}
        if cpl_7 and cpl_28 and cpl_28 > 0:
            ratio = cpl_7 / cpl_28
            if ratio >= settings.ai_lab_anomaly_cpl_ratio:
                anomaly["cpl_ratio"] = round(ratio, 2)
        if leads_28 > 0 and leads_7 < leads_28 * 0.5:
            anomaly["leads_drop_pct"] = round((1 - leads_7 / leads_28) * 100, 1)
        if not anomaly:
            continue
        await create_ai_task(
            db,
            organization_id=organization_id,
            user_id=user.id,
            kind="campaign_review",
            input_data={"campaign_id": str(camp.id), "anomaly": anomaly},
            trigger="anomaly",
        )
        created += 1
    return created


async def run_ai_lab_automation(db: AsyncSession) -> dict[str, int]:
    from app.models import Organization

    orgs = list((await db.scalars(select(Organization.id))).all())
    weekly = 0
    anomaly = 0
    for org_id in orgs:
        weekly += await run_weekly_period_reviews(db, org_id)
        anomaly += await run_anomaly_campaign_reviews(db, org_id)
    return {"weekly": weekly, "anomaly": anomaly}
