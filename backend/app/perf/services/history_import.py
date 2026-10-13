"""کمپین‌های دفتر میزیتو را از فایل تاریخی به دیتابیس جاری می‌آورد.

عددها همان ردیف‌های هزینه، استوری، پیامک و ورودی هستند. چیزی ساخته نمی‌شود.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Organization
from app.perf.campaign_register import LEGACY, NUMBERS
from app.perf.models import PmCampaign, PmCost, PmLead, PmPage, PmSmsSend, PmStory

_SKIP = {"S90", "S94", "S95"}
_SOURCE = Path(__file__).resolve().parents[3] / "cm_dev.db"


def _uuid(value: object) -> UUID | None:
    if not value:
        return None
    text = str(value).strip().replace("-", "")
    if len(text) != 32:
        return None
    return UUID(f"{text[0:8]}-{text[8:12]}-{text[12:16]}-{text[16:20]}-{text[20:]}")


def _day(value: object) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _book_codes() -> set[str]:
    return {str(row["code"]) for row in [*NUMBERS, *LEGACY]} | {"S4"}


async def import_campaign_history(db: AsyncSession) -> dict:
    """اگر فایل تاریخی باشد، کمپین و دفتر عددی‌اش را که هنوز نیست اضافه می‌کند."""
    if not _SOURCE.exists():
        return {"status": "no_source"}
    org = await db.scalar(select(Organization).where(Organization.slug == "autoco"))
    if org is None:
        return {"status": "no_org"}
    wanted = _book_codes() - _SKIP
    src = sqlite3.connect(_SOURCE)
    src.row_factory = sqlite3.Row
    try:
        source_rows = [
            row
            for row in src.execute(
                "select id, code, title, brand, goal, starts_on, ends_on, budget_toman, status, channels from pm_campaign"
            )
            if row["code"] in wanted
        ]
        if not source_rows:
            return {"status": "empty"}
        live = {
            row.code: row
            for row in (
                await db.scalars(select(PmCampaign).where(PmCampaign.organization_id == org.id))
            ).all()
        }
        added = 0
        id_map: dict[UUID, UUID] = {}
        for row in source_rows:
            old = _uuid(row["id"])
            if old is None:
                continue
            current = live.get(row["code"])
            if current is None:
                current = PmCampaign(
                    organization_id=org.id,
                    code=row["code"],
                    title=(row["title"] or row["code"])[:200],
                    brand=row["brand"] or "",
                    goal=row["goal"] or "",
                    starts_on=_day(row["starts_on"]),
                    ends_on=_day(row["ends_on"]),
                    budget_toman=row["budget_toman"],
                    status=row["status"] if row["status"] in ("draft", "active", "done") else "done",
                    channels=row["channels"] or "sms",
                )
                db.add(current)
                live[current.code] = current
                added += 1
            id_map[old] = current.id
        pages = await _pages(db, src, org.id, set(id_map))
        stories = await _stories(db, src, org.id, id_map, pages)
        sends = await _sends(db, src, org.id, id_map)
        costs = await _costs(db, src, org.id, set(live), stories, sends)
        leads = await _leads(db, src, org.id, id_map)
        await _bind_leads(db, org.id)
        await db.flush()
        return {
            "status": "imported",
            "campaigns": added,
            "costs": costs,
            "stories": stories and len(stories),
            "sends": sends and len(sends),
            "leads": leads,
        }
    finally:
        src.close()


async def _pages(db: AsyncSession, src: sqlite3.Connection, organization_id: UUID, campaigns: set[UUID]) -> dict[UUID, UUID]:
    live = {
        row.name: row.id
        for row in (await db.scalars(select(PmPage).where(PmPage.organization_id == organization_id))).all()
    }
    needed = {
        _uuid(row["page_id"])
        for row in src.execute("select campaign_id, page_id from pm_story where page_id is not null")
        if _uuid(row["campaign_id"]) in campaigns and _uuid(row["page_id"])
    }
    mapping: dict[UUID, UUID] = {}
    for row in src.execute("select id, name, followers, topic, contact, price_toman from pm_page"):
        old = _uuid(row["id"])
        if old is None or old not in needed:
            continue
        name = (row["name"] or "بدون پیج")[:160]
        if name in live:
            mapping[old] = live[name]
            continue
        page = PmPage(
            organization_id=organization_id,
            name=name,
            followers=int(row["followers"] or 0),
            topic=row["topic"] or "",
            contact=row["contact"] or "",
            price_toman=int(row["price_toman"] or 0),
        )
        db.add(page)
        live[name] = page.id
        mapping[old] = page.id
    return mapping


async def _stories(
    db: AsyncSession,
    src: sqlite3.Connection,
    organization_id: UUID,
    campaigns: dict[UUID, UUID],
    pages: dict[UUID, UUID],
) -> dict[UUID, UUID]:
    have = {
        (row.campaign_id, row.published_on, row.cost_toman or 0, row.views or 0, row.kind or "")
        for row in (await db.scalars(select(PmStory).where(PmStory.organization_id == organization_id))).all()
    }
    mapping: dict[UUID, UUID] = {}
    for row in src.execute("select * from pm_story"):
        old_campaign = _uuid(row["campaign_id"])
        old = _uuid(row["id"])
        if old is None or old_campaign not in campaigns:
            continue
        published = _day(row["published_on"])
        key = (campaigns[old_campaign], published, int(row["cost_toman"] or 0), int(row["views"] or 0), row["kind"] or "story")
        if key in have:
            continue
        story = PmStory(
            organization_id=organization_id,
            campaign_id=campaigns[old_campaign],
            page_id=pages.get(_uuid(row["page_id"]) or UUID(int=0)),
            kind=row["kind"] or "story",
            status=row["status"] if row["status"] in ("planned", "published") else "published",
            published_on=published,
            cost_toman=int(row["cost_toman"] or 0),
            views=int(row["views"] or 0),
            impressions=int(row["impressions"] or 0),
            reach=int(row["reach"] or 0),
            likes=int(row["likes"] or 0),
            replies=int(row["replies"] or 0),
            shares=int(row["shares"] or 0),
            link_clicks=int(row["link_clicks"] or 0),
            sticker_taps=int(row["sticker_taps"] or 0),
            navigation=int(row["navigation"] or 0),
            forward=int(row["forward"] or 0),
            next_story=int(row["next_story"] or 0),
            back=int(row["back"] or 0),
            exited=int(row["exited"] or 0),
            leads=int(row["leads"] or 0),
        )
        db.add(story)
        have.add(key)
        mapping[old] = story.id
    return mapping


async def _sends(
    db: AsyncSession, src: sqlite3.Connection, organization_id: UUID, campaigns: dict[UUID, UUID]
) -> dict[UUID, UUID]:
    have = {
        (row.campaign_id, row.sent_at.date().isoformat() if row.sent_at else "", row.recipient_count or 0, row.cost_toman or 0)
        for row in (await db.scalars(select(PmSmsSend).where(PmSmsSend.organization_id == organization_id))).all()
    }
    mapping: dict[UUID, UUID] = {}
    for row in src.execute("select * from pm_sms_send"):
        old_campaign = _uuid(row["campaign_id"])
        old = _uuid(row["id"])
        if old is None or old_campaign not in campaigns:
            continue
        sent = str(row["sent_at"] or "")[:10]
        key = (campaigns[old_campaign], sent, int(row["recipient_count"] or 0), int(row["cost_toman"] or 0))
        if key in have:
            continue
        from datetime import UTC, datetime

        sent_at = None
        if row["sent_at"]:
            try:
                sent_at = datetime.fromisoformat(str(row["sent_at"]).replace("Z", "+00:00"))
                if sent_at.tzinfo is None:
                    sent_at = sent_at.replace(tzinfo=UTC)
            except ValueError:
                sent_at = None
        item = PmSmsSend(
            organization_id=organization_id,
            campaign_id=campaigns[old_campaign],
            sender_line=row["sender_line"] or "",
            body=row["body"] or "",
            pages=int(row["pages"] or 1),
            recipient_count=int(row["recipient_count"] or 0),
            sent_at=sent_at,
            cost_toman=int(row["cost_toman"] or 0),
            delivered_count=int(row["delivered_count"] or 0),
            calls=int(row["calls"] or 0),
            leads=int(row["leads"] or 0),
        )
        db.add(item)
        have.add(key)
        mapping[old] = item.id
    return mapping


async def _costs(
    db: AsyncSession,
    src: sqlite3.Connection,
    organization_id: UUID,
    codes: set[str],
    stories: dict[UUID, UUID],
    sends: dict[UUID, UUID],
) -> int:
    have = {
        (row.campaign_code, row.spent_on, row.amount_toman or 0, row.kind or "", row.detail or "")
        for row in (await db.scalars(select(PmCost).where(PmCost.organization_id == organization_id))).all()
    }
    added = 0
    for row in src.execute("select * from pm_cost"):
        if row["campaign_code"] not in codes:
            continue
        spent = _day(row["spent_on"])
        key = (row["campaign_code"] or "", spent, int(row["amount_toman"] or 0), row["kind"] or "", row["detail"] or "")
        if key in have:
            continue
        story_id = stories.get(_uuid(row["story_id"]) or UUID(int=0))
        send_id = sends.get(_uuid(row["sms_send_id"]) or UUID(int=0))
        db.add(
            PmCost(
                organization_id=organization_id,
                cost_number=int(row["cost_number"] or 0),
                spent_on=spent,
                amount_toman=int(row["amount_toman"] or 0),
                kind=row["kind"] or "",
                detail=(row["detail"] or "")[:160],
                brand=row["brand"] or "",
                campaign_code=row["campaign_code"] or "",
                cost_center=row["cost_center"] or "",
                description=(row["description"] or "")[:400],
                counts_for_cpl=bool(row["counts_for_cpl"]),
                sms_send_id=send_id,
                story_id=story_id,
            )
        )
        have.add(key)
        added += 1
    return added


async def _bind_leads(db: AsyncSession, organization_id: UUID) -> None:
    """ورودی‌هایی که فقط کد دارند به همان کمپین وصل می‌شوند."""
    rows = list((await db.scalars(select(PmCampaign).where(PmCampaign.organization_id == organization_id))).all())
    by_code = {row.code: row.id for row in rows}
    loose = list(
        (
            await db.scalars(
                select(PmLead).where(PmLead.organization_id == organization_id, PmLead.campaign_id.is_(None))
            )
        ).all()
    )
    for lead in loose:
        found = by_code.get((lead.campaign_code or "").strip())
        if found:
            lead.campaign_id = found


async def _leads(db: AsyncSession, src: sqlite3.Connection, organization_id: UUID, campaigns: dict[UUID, UUID]) -> int:
    have = {
        (row.campaign_id, row.phone or "", row.occurred_on, row.quantity or 1, row.channel or "")
        for row in (await db.scalars(select(PmLead).where(PmLead.organization_id == organization_id))).all()
    }
    added = 0
    for row in src.execute("select * from pm_lead"):
        old_campaign = _uuid(row["campaign_id"])
        if old_campaign not in campaigns:
            continue
        occurred = _day(row["occurred_on"])
        key = (campaigns[old_campaign], row["phone"] or "", occurred, int(row["quantity"] or 1), row["channel"] or "")
        if key in have:
            continue
        db.add(
            PmLead(
                organization_id=organization_id,
                campaign_id=campaigns[old_campaign],
                phone=row["phone"] or "",
                occurred_on=occurred,
                campaign_code=row["campaign_code"] or "",
                channel=row["channel"] or "",
                stage=row["stage"] or "",
                quantity=int(row["quantity"] or 1),
            )
        )
        have.add(key)
        added += 1
    return added
