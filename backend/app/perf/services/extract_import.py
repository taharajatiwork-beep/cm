"""میزیتو و پنل‌های پیامک را به کمپین، ارسال و ورودی وصل می‌کند.

هزینهٔ دفتر پرداخت اگر باشد دست نمی‌خورد. هزینهٔ گزارش میزیتو فقط برای کمپینی می‌آید که هنوز ردیف هزینه ندارد.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.perf.models import PmCampaign, PmCost, PmLead, PmPanel, PmSmsSend, PmStory

ASSETS = Path(__file__).resolve().parents[4] / "assets"
SOTO_DB = ASSETS / "New folder" / "sotoudeh.db"
ISMS_DB = ASSETS / "isms" / "isms_panel.db"

_CHANNEL_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("sms", ("پیامک", "sms")),
    ("lbs", ("موقعیت", "lbs")),
    ("ig_story", ("اینستاگرام", "تلگرام", "سوشال", "روبیکا", "بله", "واتس")),
    ("divar", ("دیوار",)),
    ("google", ("گوگل",)),
    ("native", ("همسان", "پری‌رول", "یکتانت", "صبا")),
    ("banner", ("بنر", "باما")),
    ("influencer", ("اینفلوئنسر", "بلاگر")),
    ("landing", ("لندینگ", "سایت", "پرسلاین")),
)


def channel_codes(names: list[str]) -> list[str]:
    blob = " ".join(names).lower()
    found = [code for code, words in _CHANNEL_WORDS if any(word in blob for word in words)]
    return found


def toman_from_rial(amount: int) -> int:
    return amount // 10 if amount else 0


def _connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    return db


def _sms_body(raw: str) -> str:
    text_value = (raw or "").replace("🔍 نمایش اطلاعات کامل", "").strip()
    cut = text_value.find("تعداد صفحه")
    if cut > 0:
        text_value = text_value[:cut].strip()
    return text_value[:800]


async def _ensure_quantity(db: AsyncSession) -> None:
    cols = (await db.execute(text("PRAGMA table_info(pm_lead)"))).all()
    names = {row[1] for row in cols}
    if "quantity" not in names:
        await db.execute(text("ALTER TABLE pm_lead ADD COLUMN quantity INTEGER DEFAULT 1"))


async def import_extracts(db: AsyncSession, organization_id: UUID) -> dict:
    await _ensure_quantity(db)
    campaigns = {
        row.code: row
        for row in (await db.scalars(select(PmCampaign).where(PmCampaign.organization_id == organization_id))).all()
    }
    panels = {
        row.code: row
        for row in (await db.scalars(select(PmPanel).where(PmPanel.organization_id == organization_id))).all()
    }
    sends = list((await db.scalars(select(PmSmsSend).where(PmSmsSend.organization_id == organization_id))).all())
    stories = list((await db.scalars(select(PmStory).where(PmStory.organization_id == organization_id))).all())
    costs = list((await db.scalars(select(PmCost).where(PmCost.organization_id == organization_id))).all())
    leads = list((await db.scalars(select(PmLead).where(PmLead.organization_id == organization_id))).all())
    bodies = {row.body or "" for row in sends}
    result = {"campaigns": 0, "channels": 0, "costs": 0, "sends": 0, "leads": 0, "panels": 0}

    if not SOTO_DB.exists():
        return result
    soto = _connect(SOTO_DB)
    try:
        brands = {row["brand_id"]: row["name_fa"] or "" for row in soto.execute("select brand_id, name_fa from brands")}
        names_by_campaign: dict[int, list[str]] = {}
        for row in soto.execute(
            """
            select cc.campaign_id, ch.name_fa
            from mz_campaign_channels cc
            join channels ch on ch.channel_id = cc.channel_id
            """
        ):
            names_by_campaign.setdefault(row["campaign_id"], []).append(row["name_fa"] or "")

        number = max((row.cost_number or 0 for row in costs), default=0)
        ledger_codes = {
            (row.campaign_code or "").strip()
            for row in costs
            if row.counts_for_cpl and not row.sms_send_id and not row.story_id
        }
        story_leads = {}
        for row in stories:
            if row.campaign_id and (row.leads or 0):
                story_leads[row.campaign_id] = story_leads.get(row.campaign_id, 0) + (row.leads or 0)
        sms_leads = {}
        for row in sends:
            if row.campaign_id and (row.leads or 0):
                sms_leads[row.campaign_id] = sms_leads.get(row.campaign_id, 0) + (row.leads or 0)
        already_have_leads = {row.campaign_id for row in leads if row.campaign_id}

        for row in soto.execute("select * from mz_campaigns"):
            code = (row["code"] or "").strip()
            if not code:
                continue
            current = campaigns.get(code)
            if current is None:
                current = PmCampaign(
                    organization_id=organization_id,
                    code=code,
                    title=(row["title"] or code)[:200],
                    brand=(brands.get(row["brand_id"]) or "")[:80],
                    status="done",
                    channels="sms",
                )
                db.add(current)
                campaigns[code] = current
                result["campaigns"] += 1
            if not (current.goal or "").strip() and row["objective"]:
                goal = row["objective"]
                if row["products_text"]:
                    goal = f"{goal} · {row['products_text']}"
                current.goal = goal[:255]
            codes = channel_codes(names_by_campaign.get(row["campaign_id"], []))
            if codes:
                current.channels = ",".join(codes)[:80]
                result["channels"] += 1
            amount = int(row["cost_amount"] or 0)
            if amount > 0 and row["cost_unit"] == "تومان" and code not in ledger_codes:
                number += 1
                db.add(
                    PmCost(
                        organization_id=organization_id,
                        cost_number=number,
                        amount_toman=amount,
                        kind="سایر",
                        detail="گزارش میزیتو",
                        brand=current.brand or "",
                        campaign_code=code,
                        description="گزارش میزیتو",
                        counts_for_cpl=True,
                    )
                )
                ledger_codes.add(code)
                result["costs"] += 1

        await db.flush()

        for row in soto.execute(
            """
            select s.send_id, s.message_count, s.send_kind, s.database_segment, s.region, s.notes, c.code
            from mz_sms_sends s
            join mz_campaigns c on c.campaign_id = s.campaign_id
            where s.record_type = 'send' and coalesce(s.message_count, 0) > 0 and c.code is not null
            """
        ):
            marker = f"[[mz:{row['send_id']}]]"
            if any(marker in body for body in bodies):
                continue
            campaign = campaigns.get((row["code"] or "").strip())
            if campaign is None:
                continue
            note = " · ".join(part for part in (row["database_segment"], row["region"], row["notes"]) if part)
            body = f"{marker} {note}".strip()
            db.add(
                PmSmsSend(
                    organization_id=organization_id,
                    campaign_id=campaign.id,
                    body=body[:2000],
                    recipient_count=int(row["message_count"] or 0),
                    pages=1,
                )
            )
            bodies.add(body)
            result["sends"] += 1

        for row in soto.execute(
            """
            select c.code, m.dimension_value, m.value
            from mz_campaign_metrics m
            join mz_campaigns c on c.campaign_id = m.campaign_id
            where m.dimension = 'crm_stage' and m.metric = 'leads' and c.code is not null and coalesce(m.value, 0) > 0
            """
        ):
            campaign = campaigns.get((row["code"] or "").strip())
            if campaign is None or campaign.id in already_have_leads:
                continue
            if story_leads.get(campaign.id) or sms_leads.get(campaign.id):
                already_have_leads.add(campaign.id)
                continue
            db.add(
                PmLead(
                    organization_id=organization_id,
                    campaign_id=campaign.id,
                    campaign_code=campaign.code,
                    channel="میزیتو",
                    stage=(row["dimension_value"] or "")[:80],
                    quantity=int(row["value"]),
                )
            )
            result["leads"] += 1
    finally:
        soto.close()

    if ISMS_DB.exists():
        isms = _connect(ISMS_DB)
        try:
            panel = panels.get("isms")
            for row in isms.execute(
                """
                select id, message_text, quantity
                from lbs_sends
                where coalesce(quantity, 0) > 0
                """
            ):
                marker = f"[[lbs:{row['id']}]]"
                if any(marker in body for body in bodies):
                    continue
                body = f"{marker}\n{_sms_body(row['message_text'] or '')}".strip()
                db.add(
                    PmSmsSend(
                        organization_id=organization_id,
                        panel_id=panel.id if panel else None,
                        body=body[:2000],
                        recipient_count=int(row["quantity"] or 0),
                        pages=1,
                    )
                )
                bodies.add(body)
                result["sends"] += 1
        finally:
            isms.close()

    soto = _connect(SOTO_DB) if SOTO_DB.exists() else None
    if soto is not None:
        try:
            panel = panels.get("pishgam")
            account = {row["key"]: row for row in soto.execute("select key, value_text, value_num, unit from pg_account_info")}
            balance = account.get("balance")
            if panel is not None and balance is not None and balance["unit"] == "ریال" and balance["value_num"]:
                panel.balance_toman = toman_from_rial(int(balance["value_num"]))
                result["panels"] += 1
            sender = account.get("sender_line")
            if panel is not None and sender and sender["value_text"] and not (panel.sender_line or "").strip():
                panel.sender_line = sender["value_text"][:40]
            user = account.get("username")
            if panel is not None and user and user["value_text"] and not (panel.api_username or "").strip():
                panel.api_username = user["value_text"][:120]
            isms_panel = panels.get("isms")
            if isms_panel is not None and (isms_panel.api_username or "").endswith("@autoco.example"):
                isms_panel.api_username = "mvm401"
                result["panels"] += 1
            for row in soto.execute("select * from pg_outbox_samples"):
                marker = f"[[pg:{row['sample_id']}]]"
                if any(marker in body for body in bodies):
                    continue
                recipients = int(row["recipients"] or 0)
                cost = toman_from_rial(int(row["price_rial"] or 0))
                if any((item.recipient_count or 0) == recipients and (item.cost_toman or 0) == cost and cost for item in sends):
                    continue
                body = f"{marker}\n{row['message_text_raw'] or ''}".strip()
                db.add(
                    PmSmsSend(
                        organization_id=organization_id,
                        panel_id=panel.id if panel else None,
                        sender_line=(row["sender_line"] or "")[:40],
                        body=body[:2000],
                        recipient_count=recipients,
                        cost_toman=cost,
                        pages=1,
                    )
                )
                bodies.add(body)
                result["sends"] += 1
        finally:
            soto.close()

    await db.flush()
    return result
