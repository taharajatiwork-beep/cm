"""Baseline and follow-up KPI measurement for accepted recommendations."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_lab.models import AiRecFollowup, AiTask
from app.ai_lab.snapshots import _parse_day, _sms_in_range, _in_range, _div
from app.perf.models import PmCampaign, PmCost, PmLead, PmSmsSend, PmStory
from app.perf.services.reports import placement_live


async def metrics_for_scope(
    db: AsyncSession,
    organization_id: UUID,
    kind: str,
    input_data: dict,
    period_days: int = 14,
    end: date | None = None,
) -> dict:
    end = end or date.today()
    start = end - timedelta(days=period_days - 1)
    sends = list((await db.scalars(select(PmSmsSend).where(PmSmsSend.organization_id == organization_id))).all())
    stories = list((await db.scalars(select(PmStory).where(PmStory.organization_id == organization_id))).all())
    costs = list((await db.scalars(select(PmCost).where(PmCost.organization_id == organization_id))).all())
    leads = list((await db.scalars(select(PmLead).where(PmLead.organization_id == organization_id))).all())

    campaign_id = input_data.get("campaign_id")
    brand = (input_data.get("brand") or "").strip()

    def in_scope_sms(row: PmSmsSend) -> bool:
        if not _sms_in_range(row.sent_at, start, end):
            return False
        if campaign_id and str(row.campaign_id) != str(campaign_id):
            return False
        return True

    def in_scope_story(row: PmStory) -> bool:
        if not placement_live(row) or not _in_range(row.published_on, start, end):
            return False
        if campaign_id and str(row.campaign_id) != str(campaign_id):
            return False
        return True

    if kind == "channel_budget" and input_data.get("reference_from"):
        start = _parse_day(input_data["reference_from"])
        end = _parse_day(input_data.get("reference_to") or end.isoformat())
    elif kind in ("period_review", "sms_copy_review") and input_data.get("from_date"):
        start = _parse_day(input_data["from_date"])
        end = _parse_day(input_data.get("to_date") or end.isoformat())
        if brand:
            camps = {
                str(c.id)
                for c in (
                    await db.scalars(select(PmCampaign).where(PmCampaign.organization_id == organization_id))
                ).all()
                if brand in (c.brand or "")
            }

            def in_scope_sms(row: PmSmsSend) -> bool:
                if not _sms_in_range(row.sent_at, start, end):
                    return False
                return str(row.campaign_id) in camps if camps else True

    sms_cost = sum(row.cost_toman or 0 for row in sends if in_scope_sms(row))
    sms_leads = sum(row.leads or 0 for row in sends if in_scope_sms(row))
    story_cost = sum(row.cost_toman or 0 for row in stories if in_scope_story(row))
    story_leads = sum(row.leads or 0 for row in stories if in_scope_story(row))
    ledger = sum(
        row.amount_toman or 0
        for row in costs
        if row.counts_for_cpl and _in_range(row.spent_on, start, end)
    )
    imported = sum(
        row.quantity or 1
        for row in leads
        if _in_range(row.occurred_on, start, end)
        and (not campaign_id or str(row.campaign_id) == str(campaign_id))
    )
    total_cost = sms_cost + story_cost + ledger
    lead_count = imported or (sms_leads + story_leads)
    return {
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "cost_toman": total_cost,
        "leads": lead_count,
        "cpl": _div(total_cost, lead_count),
    }


async def ensure_followup_on_accept(
    db: AsyncSession,
    row: AiTask,
    rec_id: str,
    cm_task_id: UUID | None = None,
    followup_days: int = 14,
) -> AiRecFollowup:
    existing = await db.scalar(
        select(AiRecFollowup).where(AiRecFollowup.ai_task_id == row.id, AiRecFollowup.rec_id == rec_id)
    )
    if existing:
        if cm_task_id and not existing.cm_task_id:
            existing.cm_task_id = cm_task_id
        return existing
    try:
        inp = json.loads(row.input_json or "{}")
    except json.JSONDecodeError:
        inp = {}
    baseline = await metrics_for_scope(db, row.organization_id, row.kind, inp)
    now = datetime.now(UTC)
    fu = AiRecFollowup(
        ai_task_id=row.id,
        rec_id=rec_id,
        cm_task_id=cm_task_id,
        accepted_at=now,
        baseline_json=json.dumps(baseline, ensure_ascii=False),
        followup_due_on=(date.today() + timedelta(days=followup_days)),
    )
    db.add(fu)
    await db.flush()
    return fu


async def measure_due_followups(db: AsyncSession) -> int:
    today = date.today()
    rows = list(
        (
            await db.scalars(
                select(AiRecFollowup).where(
                    AiRecFollowup.measured_at.is_(None),
                    AiRecFollowup.followup_due_on <= today,
                )
            )
        ).all()
    )
    count = 0
    for fu in rows:
        task = await db.get(AiTask, fu.ai_task_id)
        if not task:
            continue
        try:
            inp = json.loads(task.input_json or "{}")
        except json.JSONDecodeError:
            inp = {}
        followup = await metrics_for_scope(db, task.organization_id, task.kind, inp)
        fu.followup_json = json.dumps(followup, ensure_ascii=False)
        fu.measured_at = datetime.now(UTC)
        count += 1
    return count
