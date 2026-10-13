"""گزارش زنده کمپین: هزینه، ورودی، CPL و سهم کانال."""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.perf.models import PmCampaign, PmCost, PmLead, PmPage, PmPaymentRequest, PmSmsSend, PmStory
from app.perf.services.common import iso


def _div(num: float, den: float) -> float | None:
    if not den:
        return None
    return round(num / den, 1)


def lead_matches(campaign: PmCampaign, lead: PmLead) -> bool:
    stages = [part.strip() for part in (campaign.lead_stages or "").split(",") if part.strip()]
    if not stages:
        return True
    return (lead.stage or "").strip() in stages


def story_rates(story: PmStory) -> dict:
    views = story.views or 0
    reach = story.reach or story.impressions or 0
    clicks = story.link_clicks or 0
    leads = story.leads or 0
    cost = story.cost_toman or 0
    engaged = (story.likes or 0) + (story.replies or 0) + (story.shares or 0) + clicks
    return {
        "cpr": _div(cost, reach),
        "cpv": _div(cost, views),
        "cpc": _div(cost, clicks),
        "ctr": _div(clicks * 100, views),
        "cpl": _div(cost, leads),
        "engagement": _div(engaged * 100, views),
        "completion": _div((views - (story.exited or 0)) * 100, views) if views else None,
        "exit_rate": _div((story.exited or 0) * 100, views),
    }


def placement_live(story: PmStory) -> bool:
    return (story.status or "published") == "published"


def booked_cost(story: PmStory, paid_ids: set[UUID] | None, linked_ids: set[UUID] | None) -> int:
    """هزینهٔ قطعی فقط برای انتشارِ پرداخت‌شده. ردیف قدیمی بدون درخواست، همان مبلغ را دارد."""
    if not placement_live(story):
        return 0
    amount = story.cost_toman or 0
    if paid_ids is None:
        return amount
    if story.id in paid_ids:
        return amount
    if linked_ids and story.id in linked_ids:
        return 0
    return amount


def settlement_ids(payments: list[PmPaymentRequest], costs: list[PmCost]) -> tuple[set[UUID], set[UUID]]:
    paid = {row.story_id for row in payments if row.story_id and row.status == "recorded"}
    paid.update(row.story_id for row in costs if row.story_id)
    linked = {row.story_id for row in payments if row.story_id}
    return paid, linked


async def load_settlement(db: AsyncSession, organization_id: UUID) -> tuple[set[UUID], set[UUID]]:
    payments = list(
        (
            await db.scalars(
                select(PmPaymentRequest).where(PmPaymentRequest.organization_id == organization_id)
            )
        ).all()
    )
    costs = list(
        (await db.scalars(select(PmCost).where(PmCost.organization_id == organization_id))).all()
    )
    return settlement_ids(payments, costs)


def _money_bucket(kind: str) -> str:
    text = kind or ""
    if "پیامک" in text or "sms" in text.lower():
        return "پیامک"
    if any(word in text for word in ("تبلیغ", "استوری", "بنر", "اینستا", "دیوار", "روبیکا", "بله")):
        return "سوشال"
    return "سایر"


def _ledger_costs(campaign: PmCampaign, costs: list[PmCost] | None) -> list[PmCost]:
    code = (campaign.code or "").strip()
    if not code or not costs:
        return []
    return [
        row
        for row in costs
        if (row.campaign_code or "").strip() == code and row.counts_for_cpl and not row.sms_send_id and not row.story_id
    ]


def report_from_parts(
    campaign: PmCampaign,
    sends: list[PmSmsSend],
    stories: list[PmStory],
    leads: list[PmLead],
    pages: dict[UUID, PmPage],
    paid_ids: set[UUID] | None = None,
    linked_ids: set[UUID] | None = None,
    costs: list[PmCost] | None = None,
) -> dict:
    """آمار یک کمپین از ردیف‌های شیت، نه از یک جمع جدا."""
    imported = [row for row in leads if lead_matches(campaign, row)]
    sms_leads = sum(row.leads or 0 for row in sends)
    live = [row for row in stories if placement_live(row)]
    story_leads = sum(row.leads or 0 for row in live)
    lead_count = sum(row.quantity or 1 for row in imported) if imported else sms_leads + story_leads
    sms_cost = sum(row.cost_toman or 0 for row in sends)
    story_cost = sum(booked_cost(row, paid_ids, linked_ids) for row in stories)
    ledger = _ledger_costs(campaign, costs)
    if ledger:
        sms_cost = sum(row.amount_toman or 0 for row in ledger if _money_bucket(row.kind) == "پیامک")
        story_cost = sum(row.amount_toman or 0 for row in ledger if _money_bucket(row.kind) == "سوشال")
        other_cost = sum(row.amount_toman or 0 for row in ledger if _money_bucket(row.kind) == "سایر")
    else:
        other_cost = 0
    cost = sms_cost + story_cost + other_cost
    budget = campaign.budget_toman or 0
    budget_over = budget > 0 and cost > budget
    views = sum(row.views or 0 for row in live)
    clicks = sum(row.link_clicks or 0 for row in live) + sum(row.calls or 0 for row in sends)

    by_day: dict[str, dict] = defaultdict(lambda: {"cost": 0, "leads": 0})
    for row in sends:
        key = (row.sent_at.date().isoformat() if row.sent_at else "—")
        if not ledger:
            by_day[key]["cost"] += row.cost_toman or 0
        if not imported:
            by_day[key]["leads"] += row.leads or 0
    for row in live:
        key = row.published_on.isoformat() if row.published_on else "—"
        if not ledger:
            by_day[key]["cost"] += booked_cost(row, paid_ids, linked_ids)
        if not imported:
            by_day[key]["leads"] += row.leads or 0
    for row in ledger:
        key = row.spent_on.isoformat() if row.spent_on else "—"
        by_day[key]["cost"] += row.amount_toman or 0
    for row in imported:
        key = row.occurred_on.isoformat() if row.occurred_on else "—"
        by_day[key]["leads"] += 1
    trend = [{"day": day, **vals} for day, vals in sorted(by_day.items()) if day != "—"]

    page_rows = []
    for page_id, group in _group_stories(live).items():
        page = pages.get(page_id)
        p_cost = sum(booked_cost(item, paid_ids, linked_ids) for item in group)
        p_views = sum(item.views or 0 for item in group)
        p_leads = sum(item.leads or 0 for item in group)
        page_rows.append(
            {
                "page_id": str(page_id) if page_id else None,
                "name": page.name if page else "بدون پیج",
                "cost": p_cost,
                "views": p_views,
                "leads": p_leads,
                "cpv": _div(p_cost, p_views),
                "cpl": _div(p_cost, p_leads),
            }
        )
    page_rows.sort(key=lambda row: (row["cpl"] is None, row["cpl"] or 0, row["cpv"] or 0))

    channels = [
        {"label": "پیامک", "cost": sms_cost, "leads": len([r for r in imported if r.channel == "sms"]) or sms_leads, "views": 0},
        {"label": "سوشال", "cost": story_cost, "leads": len([r for r in imported if r.channel == "ig_story"]) or story_leads, "views": views},
    ]
    if other_cost:
        channels.append({"label": "سایر", "cost": other_cost, "leads": 0, "views": 0})
    if imported and not any(row.channel for row in imported):
        channels[0]["leads"] = sms_leads
        channels[1]["leads"] = story_leads

    return {
        "campaign_id": str(campaign.id),
        "code": campaign.code,
        "title": campaign.title,
        "brand": campaign.brand,
        "starts_on": iso(campaign.starts_on),
        "ends_on": iso(campaign.ends_on),
        "budget_toman": campaign.budget_toman,
        "budget_over": budget_over,
        "budget_warning": (
            f"هزینهٔ شیت ({fa_num(cost)} تومان) از بودجه ({fa_num(budget)} تومان) بیشتر است — فقط هشدار."
            if budget_over
            else ""
        ),
        "cost_toman": cost,
        "sms_cost_toman": sms_cost,
        "story_cost_toman": story_cost,
        "leads": lead_count,
        "views": views,
        "clicks": clicks,
        "cpl": _div(cost, lead_count),
        "cpv": _div(cost, views),
        "channels": channels,
        "trend": trend,
        "pages": page_rows,
        "stories": [
            {
                "id": str(row.id),
                "page": pages[row.page_id].name if row.page_id in pages else "",
                "published_on": iso(row.published_on),
                "cost_toman": row.cost_toman,
                "views": row.views,
                "leads": row.leads,
                **story_rates(row),
            }
            for row in stories
        ],
        "notes": rule_notes(cost, lead_count, views, channels, page_rows),
        "advice": budget_advice(channels, page_rows),
        "source": "sheet",
    }


async def build_report(db: AsyncSession, campaign: PmCampaign) -> dict:
    org = campaign.organization_id
    sends = list(
        (
            await db.scalars(
                select(PmSmsSend).where(
                    PmSmsSend.organization_id == org, PmSmsSend.campaign_id == campaign.id
                )
            )
        ).all()
    )
    stories = list(
        (
            await db.scalars(
                select(PmStory).where(PmStory.organization_id == org, PmStory.campaign_id == campaign.id)
            )
        ).all()
    )
    leads = list(
        (
            await db.scalars(
                select(PmLead).where(PmLead.organization_id == org, PmLead.campaign_id == campaign.id)
            )
        ).all()
    )
    pages = {
        row.id: row
        for row in (
            await db.scalars(select(PmPage).where(PmPage.organization_id == org))
        ).all()
    }
    paid_ids, linked_ids = await load_settlement(db, org)
    costs = list(
        (
            await db.scalars(
                select(PmCost).where(PmCost.organization_id == org, PmCost.campaign_code == campaign.code)
            )
        ).all()
    )
    return report_from_parts(campaign, sends, stories, leads, pages, paid_ids, linked_ids, costs)


def _group_stories(stories: list[PmStory]) -> dict[UUID | None, list[PmStory]]:
    grouped: dict[UUID | None, list[PmStory]] = defaultdict(list)
    for row in stories:
        grouped[row.page_id].append(row)
    return grouped


def fa_num(value: float | int) -> str:
    text = f"{round(value):,}".replace(",", "٬")
    return text.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def budget_advice(channels: list[dict], pages: list[dict]) -> str:
    """یک جمله برای تصمیم، نه تکرار عددهایی که بالا هست."""
    priced = [row for row in channels if row.get("cost") and row.get("leads")]
    if len(priced) >= 2:
        priced.sort(key=lambda row: row["cost"] / row["leads"])
        cheap, dear = priced[0], priced[-1]
        cheap_cpl = round(cheap["cost"] / cheap["leads"])
        dear_cpl = round(dear["cost"] / dear["leads"])
        if dear_cpl > cheap_cpl * 1.25:
            gap = dear["cost"] - round(dear["leads"] * cheap_cpl)
            return (
                f"بودجهٔ بعدی را به {cheap['label']} بدهید. "
                f"هر ورودی‌اش {fa_num(cheap_cpl)} تومان است و {dear['label']} {fa_num(dear_cpl)} تومان. "
                f"اگر همان ورودی‌های {dear['label']} با نرخ ارزان‌تر می‌آمد، حدود {fa_num(gap)} تومان کمتر می‌شد."
            )
    ranked = [row for row in pages if row.get("cpl")]
    if len(ranked) >= 2 and ranked[0]["cpl"] < ranked[1]["cpl"]:
        return (
            f"پیج بعدی را {ranked[0]['name']} بگیرید. "
            f"هر ورودی‌اش {fa_num(ranked[0]['cpl'])} تومان است و {ranked[1]['name']} {fa_num(ranked[1]['cpl'])} تومان."
        )
    return ""


def rule_notes(cost: int, leads: int, views: int, channels: list[dict], pages: list[dict]) -> list[str]:
    del views
    notes: list[str] = []
    if cost and not leads:
        notes.append("هزینه ثبت شده، ولی هنوز ورودی‌ای برای این کمپین نیست.")
    ranked = [ch for ch in channels if ch.get("cost") and ch.get("leads")]
    if len(ranked) >= 2:
        best = min(ranked, key=lambda ch: ch["cost"] / ch["leads"])
        notes.append(f"ارزان‌ترین کانال نسبت به ورودی: {best['label']}.")
    priced = [row for row in pages if row.get("cpl")]
    if priced:
        notes.append(f"بهترین پیج از نظر هزینهٔ ورودی: {priced[0]['name']}.")
    if not notes:
        notes.append("با ثبت ارسال یا سوشال، شاخص‌های این کمپین اینجا محاسبه می‌شود.")
    return notes


async def campaign_board(
    db: AsyncSession,
    organization_id: UUID,
    *,
    user_id: UUID | None = None,
    scope: str = "org",
    project_ids: set[UUID] | None = None,
) -> list[dict]:
    """گزارش کمپین‌ها از دفتر؛ با scope=me فقط کمپین‌های مرتبط با پروژه‌های کاربر."""
    query = select(PmCampaign).where(PmCampaign.organization_id == organization_id)
    if scope == "me" and project_ids is not None:
        if not project_ids:
            return []
        query = query.where(PmCampaign.project_id.in_(project_ids))
    elif scope == "me" and user_id is not None:
        from app.requests.models import WorkProject, WorkRequest

        req_ids = {
            row.id
            for row in (
                await db.scalars(
                    select(WorkRequest).where(
                        WorkRequest.organization_id == organization_id,
                        WorkRequest.requested_by == user_id,
                    )
                )
            ).all()
        }
        projects = list(
            (await db.scalars(select(WorkProject).where(WorkProject.organization_id == organization_id))).all()
        )
        proj_ids = {
            row.id
            for row in projects
            if row.lead_user_id == user_id or (row.request_id and row.request_id in req_ids)
        }
        if not proj_ids:
            return []
        query = query.where(PmCampaign.project_id.in_(proj_ids))
    campaigns = list((await db.scalars(query.order_by(PmCampaign.code))).all())
    if not campaigns:
        return []
    sends = list((await db.scalars(select(PmSmsSend).where(PmSmsSend.organization_id == organization_id))).all())
    stories = list((await db.scalars(select(PmStory).where(PmStory.organization_id == organization_id))).all())
    leads = list((await db.scalars(select(PmLead).where(PmLead.organization_id == organization_id))).all())
    pages = {
        row.id: row
        for row in (await db.scalars(select(PmPage).where(PmPage.organization_id == organization_id))).all()
    }
    costs = list((await db.scalars(select(PmCost).where(PmCost.organization_id == organization_id))).all())
    paid_ids, linked_ids = await load_settlement(db, organization_id)
    by_send: dict[UUID, list] = defaultdict(list)
    by_story: dict[UUID, list] = defaultdict(list)
    by_lead: dict[UUID, list] = defaultdict(list)
    for row in sends:
        if row.campaign_id:
            by_send[row.campaign_id].append(row)
    for row in stories:
        if row.campaign_id:
            by_story[row.campaign_id].append(row)
    for row in leads:
        if row.campaign_id:
            by_lead[row.campaign_id].append(row)
    out = []
    for campaign in campaigns:
        report = report_from_parts(
            campaign,
            by_send.get(campaign.id, []),
            by_story.get(campaign.id, []),
            by_lead.get(campaign.id, []),
            pages,
            paid_ids,
            linked_ids,
            costs,
        )
        out.append(
            {
                "id": report["campaign_id"],
                "code": report["code"],
                "title": report["title"],
                "brand": report["brand"],
                "status": campaign.status,
                "cost_toman": report["cost_toman"],
                "leads": report["leads"],
                "views": report["views"],
                "cpl": report["cpl"],
                "cpv": report["cpv"],
            }
        )
    out.sort(key=lambda row: (-int(row["cost_toman"] or 0), row["code"]))
    return out
