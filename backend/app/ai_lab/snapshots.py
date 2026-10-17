"""Read-only aggregates from perf tables for Grok Bot (no PII)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_lab.history import build_history
from app.ai_lab.schemas import (
    CampaignReviewIn,
    ChannelBudgetIn,
    FinanceReconcileIn,
    MyWorkReviewIn,
    PeriodReviewIn,
    ProjectsHealthIn,
    SmsCopyReviewIn,
    SocialInboxReviewIn,
    TeamLoadIn,
)
from app.ai_lab.snapshots_social import social_inbox_review_snapshot
from app.ai_lab.snapshots_work import (
    finance_reconcile_snapshot,
    my_work_review_snapshot,
    projects_health_snapshot,
    team_load_snapshot,
)
from app.api.deps import AuthContext
from app.perf.models import PmCampaign, PmCost, PmLead, PmPage, PmSmsSend, PmStory
from app.perf.services.reports import build_report, load_settlement, placement_live


def _parse_day(text: str) -> date:
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {text}") from None


def _div(num: float, den: float) -> float | None:
    if not den:
        return None
    return round(num / den, 1)


def _in_range(d: date | None, start: date, end: date) -> bool:
    if d is None:
        return False
    return start <= d <= end


def _sms_in_range(sent_at: datetime | None, start: date, end: date) -> bool:
    if sent_at is None:
        return False
    return _in_range(sent_at.date(), start, end)


async def build_snapshot(
    db: AsyncSession,
    organization_id: UUID,
    kind: str,
    raw_input: dict,
    *,
    auth: AuthContext | None = None,
) -> dict:
    if kind == "period_review":
        snap = await _period_review(db, organization_id, PeriodReviewIn(**raw_input))
    elif kind == "campaign_review":
        snap = await _campaign_review(db, organization_id, CampaignReviewIn(**raw_input))
    elif kind == "channel_budget":
        snap = await _channel_budget(db, organization_id, ChannelBudgetIn(**raw_input))
    elif kind == "sms_copy_review":
        snap = await _sms_copy_review(db, organization_id, SmsCopyReviewIn(**raw_input))
    elif kind == "social_inbox_review":
        snap = await social_inbox_review_snapshot(db, organization_id, SocialInboxReviewIn(**raw_input))
    elif kind == "projects_health":
        snap = await projects_health_snapshot(db, organization_id, ProjectsHealthIn(**raw_input))
    elif kind == "team_load":
        snap = await team_load_snapshot(db, organization_id, TeamLoadIn(**raw_input))
    elif kind == "finance_reconcile":
        snap = await finance_reconcile_snapshot(db, organization_id, FinanceReconcileIn(**raw_input))
    elif kind == "my_work_review":
        snap = await my_work_review_snapshot(db, auth, MyWorkReviewIn(**raw_input))
    else:
        raise HTTPException(status_code=400, detail="Unknown task kind")
    scope = dict(raw_input)
    viewer = auth.user.id if auth else None
    snap["history"] = await build_history(db, organization_id, kind, scope, viewer_id=viewer)
    return snap


async def _period_review(db: AsyncSession, org: UUID, inp: PeriodReviewIn) -> dict:
    start = _parse_day(inp.from_date)
    end = _parse_day(inp.to_date)
    if end < start:
        raise HTTPException(status_code=400, detail="to_date must be on or after from_date")
    span = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span - 1)

    campaigns = list(
        (await db.scalars(select(PmCampaign).where(PmCampaign.organization_id == org))).all()
    )
    if inp.brand.strip():
        brand = inp.brand.strip()
        campaigns = [c for c in campaigns if brand in (c.brand or "")]

    sends = list((await db.scalars(select(PmSmsSend).where(PmSmsSend.organization_id == org))).all())
    stories = list((await db.scalars(select(PmStory).where(PmStory.organization_id == org))).all())
    costs = list((await db.scalars(select(PmCost).where(PmCost.organization_id == org))).all())
    leads = list((await db.scalars(select(PmLead).where(PmLead.organization_id == org))).all())

    def bucket(period_start: date, period_end: date) -> dict:
        sms_cost = sum(
            row.cost_toman or 0
            for row in sends
            if _sms_in_range(row.sent_at, period_start, period_end)
        )
        story_cost = sum(
            row.cost_toman or 0
            for row in stories
            if placement_live(row) and _in_range(row.published_on, period_start, period_end)
        )
        ledger_cost = sum(
            row.amount_toman or 0
            for row in costs
            if row.counts_for_cpl and _in_range(row.spent_on, period_start, period_end)
        )
        total_cost = sms_cost + story_cost + ledger_cost
        sms_leads = sum(
            row.leads or 0
            for row in sends
            if _sms_in_range(row.sent_at, period_start, period_end)
        )
        story_leads = sum(
            row.leads or 0
            for row in stories
            if placement_live(row) and _in_range(row.published_on, period_start, period_end)
        )
        imported = sum(
            row.quantity or 1
            for row in leads
            if _in_range(row.occurred_on, period_start, period_end)
        )
        lead_count = imported or (sms_leads + story_leads)
        by_brand: dict[str, dict] = {}
        for camp in campaigns:
            if camp.starts_on and camp.starts_on > period_end:
                continue
            if camp.ends_on and camp.ends_on < period_start:
                continue
            key = (camp.brand or "—").strip() or "—"
            by_brand.setdefault(key, {"campaigns": 0, "budget_toman": 0})
            by_brand[key]["campaigns"] += 1
            by_brand[key]["budget_toman"] += camp.budget_toman or 0
        return {
            "cost_toman": total_cost,
            "leads": lead_count,
            "cpl": _div(total_cost, lead_count),
            "channels": [
                {"channel": "sms", "cost_toman": sms_cost, "leads": sms_leads, "cpl": _div(sms_cost, sms_leads)},
                {
                    "channel": "ig_story",
                    "cost_toman": story_cost,
                    "leads": story_leads,
                    "cpl": _div(story_cost, story_leads),
                },
            ],
            "brands": by_brand,
        }

    current = bucket(start, end)
    previous = bucket(prev_start, prev_end)
    active = [
        {"code": c.code, "title": c.title, "brand": c.brand, "status": c.status}
        for c in campaigns
        if c.status == "active"
    ]
    social_automation: dict | None = None
    try:
        from app.perf.services.social_analytics import social_overview

        overview = await social_overview(db, org, refresh=False)
        nh = overview.get("novinhub") if isinstance(overview.get("novinhub"), dict) else {}
        vd = overview.get("vardast") if isinstance(overview.get("vardast"), dict) else {}
        if nh.get("connected") or vd.get("connected"):
            social_automation = {
                "rollup_at": overview.get("rollup_at"),
                "comments_open_est": nh.get("comments_open_est"),
                "conversations_open_est": nh.get("conversations_open_est"),
                "accounts_needing_login": nh.get("accounts_needing_login"),
                "vardast_chat_credit": (vd.get("usage") or {}).get("chat_credit") if vd else None,
            }
    except (ValueError, TypeError, KeyError):
        social_automation = None
    return {
        "kind": "period_review",
        "period": {"from": inp.from_date, "to": inp.to_date, "brand_filter": inp.brand.strip()},
        "current": current,
        "previous_period": {"from": prev_start.isoformat(), "to": prev_end.isoformat(), **previous},
        "active_campaigns": active,
        "social_automation": social_automation,
        "notes": "Aggregated perf data only; no phone numbers or payment identifiers.",
    }


async def _campaign_review(db: AsyncSession, org: UUID, inp: CampaignReviewIn) -> dict:
    campaign = await db.get(PmCampaign, inp.campaign_id)
    if not campaign or campaign.organization_id != org:
        raise HTTPException(status_code=404, detail="Campaign not found")
    report = await build_report(db, campaign)
    sends = [
        {
            "body": (row.body or "")[:500],
            "recipient_count": row.recipient_count,
            "delivered_count": row.delivered_count,
            "calls": row.calls,
            "leads": row.leads,
            "cost_toman": row.cost_toman,
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        }
        for row in (
            await db.scalars(
                select(PmSmsSend).where(
                    PmSmsSend.organization_id == org, PmSmsSend.campaign_id == campaign.id
                )
            )
        ).all()
    ]
    lead_stages: dict[str, int] = {}
    for row in (
        await db.scalars(
            select(PmLead).where(PmLead.organization_id == org, PmLead.campaign_id == campaign.id)
        )
    ).all():
        stage = (row.stage or "—").strip() or "—"
        lead_stages[stage] = lead_stages.get(stage, 0) + (row.quantity or 1)
    brief = {}
    if campaign.brief:
        try:
            brief = json.loads(campaign.brief)
        except json.JSONDecodeError:
            brief = {"raw": campaign.brief[:800]}
    return {
        "kind": "campaign_review",
        "campaign": {
            "id": str(campaign.id),
            "code": campaign.code,
            "title": campaign.title,
            "brand": campaign.brand,
            "goal": campaign.goal,
            "budget_toman": campaign.budget_toman,
            "channels": campaign.channels,
            "brief": brief,
        },
        "metrics": report,
        "sms_sends": sends,
        "lead_stages": lead_stages,
        "notes": "No customer phone numbers included.",
    }


async def _channel_budget(db: AsyncSession, org: UUID, inp: ChannelBudgetIn) -> dict:
    start = _parse_day(inp.reference_from)
    end = _parse_day(inp.reference_to)
    sends = list((await db.scalars(select(PmSmsSend).where(PmSmsSend.organization_id == org))).all())
    stories = list((await db.scalars(select(PmStory).where(PmStory.organization_id == org))).all())
    pages = {row.id: row for row in (await db.scalars(select(PmPage).where(PmPage.organization_id == org))).all()}
    paid_ids, linked_ids = await load_settlement(db, org)

    sms_cost = 0
    sms_leads = 0
    for row in sends:
        if not _sms_in_range(row.sent_at, start, end):
            continue
        sms_cost += row.cost_toman or 0
        sms_leads += row.leads or 0

    page_stats: dict[UUID | None, dict] = {}
    for row in stories:
        if not placement_live(row) or not _in_range(row.published_on, start, end):
            continue
        from app.perf.services.reports import booked_cost

        cost = booked_cost(row, paid_ids, linked_ids)
        key = row.page_id
        bucket = page_stats.setdefault(
            key,
            {"cost_toman": 0, "leads": 0, "views": 0, "placements": 0},
        )
        bucket["cost_toman"] += cost
        bucket["leads"] += row.leads or 0
        bucket["views"] += row.views or 0
        bucket["placements"] += 1

    page_rows = []
    for page_id, stats in page_stats.items():
        page = pages.get(page_id) if page_id else None
        page_rows.append(
            {
                "page_id": str(page_id) if page_id else None,
                "name": page.name if page else "بدون پیج",
                "followers": page.followers if page else 0,
                "list_price_toman": page.price_toman if page else 0,
                "cost_toman": stats["cost_toman"],
                "leads": stats["leads"],
                "views": stats["views"],
                "cpl": _div(stats["cost_toman"], stats["leads"]),
                "placements": stats["placements"],
            }
        )
    page_rows.sort(key=lambda r: (r["cpl"] is None, r["cpl"] or 0))

    return {
        "kind": "channel_budget",
        "reference_period": {"from": inp.reference_from, "to": inp.reference_to},
        "next_budget_toman": inp.next_budget_toman,
        "sms": {
            "cost_toman": sms_cost,
            "leads": sms_leads,
            "cpl": _div(sms_cost, sms_leads),
        },
        "pages": page_rows,
        "notes": "Use historical CPL to suggest split for next_budget_toman.",
    }


async def _sms_copy_review(db: AsyncSession, org: UUID, inp: SmsCopyReviewIn) -> dict:
    start = _parse_day(inp.from_date)
    end = _parse_day(inp.to_date)
    if end < start:
        raise HTTPException(status_code=400, detail="to_date must be on or after from_date")
    sends = list((await db.scalars(select(PmSmsSend).where(PmSmsSend.organization_id == org))).all())
    if inp.brand.strip():
        brand = inp.brand.strip()
        camps = {
            c.id
            for c in (await db.scalars(select(PmCampaign).where(PmCampaign.organization_id == org))).all()
            if brand in (c.brand or "")
        }
        sends = [s for s in sends if s.campaign_id in camps]
    rows = []
    for row in sends:
        if not _sms_in_range(row.sent_at, start, end):
            continue
        body = (row.body or "")[:300]
        recipients = row.recipient_count or 0
        leads = row.leads or 0
        cost = row.cost_toman or 0
        rows.append(
            {
                "body": body,
                "recipient_count": recipients,
                "delivered_count": row.delivered_count,
                "leads": leads,
                "lead_rate_pct": _div(leads * 100, recipients),
                "cost_toman": cost,
                "cpl": _div(cost, leads),
                "sent_at": row.sent_at.isoformat() if row.sent_at else None,
            }
        )
    rows.sort(key=lambda r: (r["cpl"] is None, r["cpl"] or 0))
    return {
        "kind": "sms_copy_review",
        "period": {"from": inp.from_date, "to": inp.to_date, "brand_filter": inp.brand.strip()},
        "sms_samples": rows[:50],
        "notes": "Suggest A/B SMS copy in recommendations[].action; no phone numbers.",
    }
