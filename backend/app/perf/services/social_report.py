"""گزارش بازه از pm_social_daily."""

from __future__ import annotations

import json
from datetime import date, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.perf.models import (
    PmCampaign,
    PmIntegration,
    PmPage,
    PmSocialAccountLink,
    PmSocialDaily,
    PmStory,
    PmVardastChannelLink,
)


def _parse_day(text: str) -> date:
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {text}") from None


def _avg(values: list[int]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _sum(values: list[int]) -> int:
    return sum(values)


def _daily_out(row: PmSocialDaily) -> dict:
    extra = {}
    if (row.metrics_json or "").strip():
        try:
            parsed = json.loads(row.metrics_json)
            if isinstance(parsed, dict):
                extra = parsed
        except json.JSONDecodeError:
            pass
    return {
        "day": row.day.isoformat(),
        "comments_open_est": row.comments_open_est,
        "conversations_open_est": row.conversations_open_est,
        "comments_sampled": row.comments_sampled,
        "conversations_sampled": row.conversations_sampled,
        "accounts_needing_login": row.accounts_needing_login,
        "vardast_chat_credit": row.vardast_chat_credit,
        "vardast_channel_count": row.vardast_channel_count,
        **extra,
    }


async def build_social_report(db: AsyncSession, organization_id: UUID, from_date: str, to_date: str) -> dict:
    start = _parse_day(from_date)
    end = _parse_day(to_date)
    if end < start:
        raise HTTPException(status_code=400, detail="to_date must be on or after from_date")
    span = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span - 1)

    rows = list(
        (
            await db.scalars(
                select(PmSocialDaily)
                .where(
                    PmSocialDaily.organization_id == organization_id,
                    PmSocialDaily.day >= start,
                    PmSocialDaily.day <= end,
                )
                .order_by(PmSocialDaily.day)
            )
        ).all()
    )
    prev_rows = list(
        (
            await db.scalars(
                select(PmSocialDaily)
                .where(
                    PmSocialDaily.organization_id == organization_id,
                    PmSocialDaily.day >= prev_start,
                    PmSocialDaily.day <= prev_end,
                )
            )
        ).all()
    )

    def aggregate(daily_rows: list[PmSocialDaily]) -> dict:
        if not daily_rows:
            return {
                "days_with_data": 0,
                "avg_comments_open": None,
                "avg_conversations_open": None,
                "max_comments_open": None,
                "max_conversations_open": None,
                "total_accounts_needing_login": 0,
            }
        comments = [r.comments_open_est for r in daily_rows]
        convs = [r.conversations_open_est for r in daily_rows]
        return {
            "days_with_data": len(daily_rows),
            "avg_comments_open": _avg(comments),
            "avg_conversations_open": _avg(convs),
            "max_comments_open": max(comments) if comments else None,
            "max_conversations_open": max(convs) if convs else None,
            "total_accounts_needing_login": _sum([r.accounts_needing_login for r in daily_rows]),
        }

    current = aggregate(rows)
    previous = aggregate(prev_rows)

    account_links = list(
        (
            await db.scalars(select(PmSocialAccountLink).where(PmSocialAccountLink.organization_id == organization_id))
        ).all()
    )
    channel_links = list(
        (
            await db.scalars(select(PmVardastChannelLink).where(PmVardastChannelLink.organization_id == organization_id))
        ).all()
    )
    pages = {p.id: p for p in (await db.scalars(select(PmPage).where(PmPage.organization_id == organization_id))).all()}
    campaigns = {
        c.id: c
        for c in (await db.scalars(select(PmCampaign).where(PmCampaign.organization_id == organization_id))).all()
    }

    return {
        "period": {"from": from_date, "to": to_date},
        "previous_period": {"from": prev_start.isoformat(), "to": prev_end.isoformat(), **previous},
        "current": current,
        "days": [_daily_out(r) for r in rows],
        "links": {
            "novinhub_accounts": [
                {
                    "account_id": link.novinhub_account_id,
                    "page_id": str(link.page_id) if link.page_id else None,
                    "page_name": pages[link.page_id].name if link.page_id and link.page_id in pages else None,
                }
                for link in account_links
            ],
            "vardast_channels": [
                {
                    "channel_id": link.vardast_channel_id,
                    "campaign_id": str(link.campaign_id) if link.campaign_id else None,
                    "campaign_code": campaigns[link.campaign_id].code if link.campaign_id and link.campaign_id in campaigns else None,
                }
                for link in channel_links
            ],
        },
        "notes": "Daily points come from scheduled GET sync; open counts are sample-based estimates.",
    }


async def campaign_social_context(db: AsyncSession, organization_id: UUID, campaign_id: UUID) -> dict:
    campaign = await db.get(PmCampaign, campaign_id)
    if not campaign or campaign.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    page_ids = {
        row.page_id
        for row in (
            await db.scalars(
                select(PmStory).where(
                    PmStory.organization_id == organization_id,
                    PmStory.campaign_id == campaign_id,
                    PmStory.page_id.isnot(None),
                )
            )
        ).all()
        if row.page_id
    }
    pages = {p.id: p for p in (await db.scalars(select(PmPage).where(PmPage.organization_id == organization_id))).all()}
    account_links = list(
        (
            await db.scalars(select(PmSocialAccountLink).where(PmSocialAccountLink.organization_id == organization_id))
        ).all()
    )
    channel_links = list(
        (
            await db.scalars(
                select(PmVardastChannelLink).where(
                    PmVardastChannelLink.organization_id == organization_id,
                    PmVardastChannelLink.campaign_id == campaign_id,
                )
            )
        ).all()
    )
    nh_accounts = []
    for link in account_links:
        if link.page_id and link.page_id in page_ids:
            page = pages.get(link.page_id)
            nh_accounts.append(
                {
                    "account_id": link.novinhub_account_id,
                    "page_id": str(link.page_id),
                    "page_name": page.name if page else None,
                }
            )
    vd_channels = [{"channel_id": link.vardast_channel_id} for link in channel_links]
    latest = await db.scalar(
        select(PmSocialDaily)
        .where(PmSocialDaily.organization_id == organization_id)
        .order_by(PmSocialDaily.day.desc())
        .limit(1)
    )
    integration = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
    rollup_at = None
    if integration and integration.social_rollup_at:
        rollup_at = integration.social_rollup_at.isoformat()
    return {
        "campaign_id": str(campaign_id),
        "campaign_code": campaign.code,
        "novinhub_accounts": nh_accounts,
        "vardast_channels": vd_channels,
        "latest_daily": _daily_out(latest) if latest else None,
        "rollup_at": rollup_at,
        "has_links": bool(nh_accounts or vd_channels),
    }


async def load_social_links_payload(db: AsyncSession, organization_id: UUID) -> dict:
    account_links = list(
        (
            await db.scalars(select(PmSocialAccountLink).where(PmSocialAccountLink.organization_id == organization_id))
        ).all()
    )
    channel_links = list(
        (
            await db.scalars(select(PmVardastChannelLink).where(PmVardastChannelLink.organization_id == organization_id))
        ).all()
    )
    pages = [
        {"id": str(p.id), "name": p.name}
        for p in (await db.scalars(select(PmPage).where(PmPage.organization_id == organization_id).order_by(PmPage.name))).all()
    ]
    campaigns = [
        {"id": str(c.id), "code": c.code, "title": c.title}
        for c in (
            await db.scalars(
                select(PmCampaign).where(PmCampaign.organization_id == organization_id).order_by(PmCampaign.code.desc())
            )
        ).all()
    ]
    return {
        "novinhub_accounts": [
            {"account_id": row.novinhub_account_id, "page_id": str(row.page_id) if row.page_id else None}
            for row in account_links
        ],
        "vardast_channels": [
            {"channel_id": row.vardast_channel_id, "campaign_id": str(row.campaign_id) if row.campaign_id else None}
            for row in channel_links
        ],
        "pages": pages,
        "campaigns": campaigns,
    }


async def save_social_links(
    db: AsyncSession,
    organization_id: UUID,
    *,
    novinhub_accounts: list[dict],
    vardast_channels: list[dict],
) -> dict:
    existing_accounts = list(
        (
            await db.scalars(select(PmSocialAccountLink).where(PmSocialAccountLink.organization_id == organization_id))
        ).all()
    )
    existing_channels = list(
        (
            await db.scalars(select(PmVardastChannelLink).where(PmVardastChannelLink.organization_id == organization_id))
        ).all()
    )
    for row in existing_accounts:
        await db.delete(row)
    for row in existing_channels:
        await db.delete(row)
    await db.flush()

    page_ids = {
        p.id
        for p in (await db.scalars(select(PmPage).where(PmPage.organization_id == organization_id))).all()
    }
    camp_ids = {
        c.id
        for c in (await db.scalars(select(PmCampaign).where(PmCampaign.organization_id == organization_id))).all()
    }

    for item in novinhub_accounts:
        account_id = str(item.get("account_id") or "").strip()
        if not account_id:
            continue
        page_raw = item.get("page_id")
        page_id = UUID(str(page_raw)) if page_raw else None
        if page_id and page_id not in page_ids:
            raise HTTPException(status_code=400, detail=f"Unknown page_id for account {account_id}")
        db.add(
            PmSocialAccountLink(
                organization_id=organization_id,
                novinhub_account_id=account_id[:64],
                page_id=page_id,
            )
        )
    for item in vardast_channels:
        channel_id = str(item.get("channel_id") or "").strip()
        if not channel_id:
            continue
        camp_raw = item.get("campaign_id")
        campaign_id = UUID(str(camp_raw)) if camp_raw else None
        if campaign_id and campaign_id not in camp_ids:
            raise HTTPException(status_code=400, detail=f"Unknown campaign_id for channel {channel_id}")
        db.add(
            PmVardastChannelLink(
                organization_id=organization_id,
                vardast_channel_id=channel_id[:64],
                campaign_id=campaign_id,
            )
        )
    await db.flush()
    return await load_social_links_payload(db, organization_id)
