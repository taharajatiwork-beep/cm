"""شیت گزارش: اطلاعات به شیت می‌رود و آمار از همان شیت خوانده می‌شود.

بدون شناسهٔ spreadsheet و فایل سرویس‌اکانت هیچ تماس شبکه‌ای زده نمی‌شود.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.perf.models import PmCampaign, PmCost, PmLead, PmPage, PmSmsSend, PmStory
from app.perf.services.common import iso
from app.perf.services.excel import COST_HEADERS
from app.perf.services.reports import booked_cost, lead_matches, load_settlement, placement_live, report_from_parts

SMS_HEADERS = ["کمپین", "تاریخ", "خط", "گیرنده", "صفحه", "هزینه", "رسیده", "تماس", "ورودی", "متن"]
SOCIAL_HEADERS = ["کمپین", "پیج", "تاریخ", "نوع", "هزینه", "بازدید", "ریچ", "کلیک", "اشتراک", "پاسخ", "خروج", "ورودی"]
LEAD_HEADERS = ["کمپین", "تاریخ", "کانال", "مرحله"]
REPORT_HEADERS = ["کمپین", "عنوان", "برند", "هزینه", "بازدید", "ورودی", "CPL", "CPV"]
_TABS = ("SMS", "Social", "Leads", "Costs", "Report")
_TOKEN: dict[str, object] = {"token": "", "exp": 0, "email": ""}


@dataclass
class SheetState:
    campaigns: list[PmCampaign]
    sends: list[PmSmsSend]
    stories: list[PmStory]
    costs: list[PmCost]
    pages: dict[UUID, PmPage]
    reports: dict[UUID, dict]
    google_connected: bool = False
    spreadsheet_url: str = ""
    reason: str = ""
    sources: dict = field(default_factory=dict)
    tables: dict[str, list[list]] = field(default_factory=dict)


def spreadsheet_id(value: str) -> str:
    text = value.strip()
    if "/d/" in text:
        text = text.split("/d/", 1)[1].split("/", 1)[0]
    return text.split("?", 1)[0]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _num(row: list, index: int) -> int:
    if index >= len(row) or row[index] in (None, ""):
        return 0
    try:
        return int(round(float(row[index])))
    except (TypeError, ValueError):
        return 0


def _rate(row: list, index: int) -> float | None:
    if index >= len(row) or row[index] in (None, ""):
        return None
    try:
        return round(float(row[index]), 1)
    except (TypeError, ValueError):
        return None


def build_tables(
    campaigns: list[PmCampaign],
    sends: list[PmSmsSend],
    stories: list[PmStory],
    leads: list[PmLead],
    costs: list[PmCost],
    pages: dict[UUID, PmPage],
    paid_ids: set[UUID] | None = None,
    linked_ids: set[UUID] | None = None,
) -> dict[str, list[list]]:
    codes = {row.id: row.code for row in campaigns}
    sms = [SMS_HEADERS]
    for row in sends:
        sms.append(
            [
                codes.get(row.campaign_id, ""),
                iso(row.sent_at),
                row.sender_line,
                row.recipient_count,
                row.pages,
                row.cost_toman or 0,
                row.delivered_count or 0,
                row.calls or 0,
                row.leads or 0,
                row.body,
            ]
        )
    social = [SOCIAL_HEADERS]
    for row in stories:
        page = pages.get(row.page_id) if row.page_id else None
        live = placement_live(row)
        social.append(
            [
                codes.get(row.campaign_id, ""),
                page.name if page else "",
                iso(row.published_on) if live else "",
                row.kind or "story",
                booked_cost(row, paid_ids, linked_ids),
                (row.views or 0) if live else 0,
                (row.reach or 0) if live else 0,
                (row.link_clicks or 0) if live else 0,
                (row.shares or 0) if live else 0,
                (row.replies or 0) if live else 0,
                (row.exited or 0) if live else 0,
                (row.leads or 0) if live else 0,
            ]
        )
    lead_rows = [LEAD_HEADERS]
    by_id = {row.id: row for row in campaigns}
    for row in leads:
        campaign = by_id.get(row.campaign_id)
        if campaign is None or not lead_matches(campaign, row):
            continue
        lead_rows.append([campaign.code, iso(row.occurred_on), row.channel or "", row.stage or ""])
    cost_rows = [COST_HEADERS]
    for row in costs:
        cost_rows.append(
            [
                row.cost_number,
                iso(row.spent_on),
                row.amount_toman,
                row.kind,
                row.detail,
                row.brand,
                row.campaign_code,
                row.cost_center,
                row.description,
            ]
        )
    report = [REPORT_HEADERS]
    for index, campaign in enumerate(campaigns, start=2):
        report.append(
            [
                campaign.code,
                campaign.title,
                campaign.brand,
                f"=SUMIF(SMS!A:A,A{index},SMS!F:F)+SUMIF(Social!A:A,A{index},Social!E:E)",
                f"=SUMIF(Social!A:A,A{index},Social!F:F)",
                (
                    f"=IF(COUNTIF(Leads!A:A,A{index})=0,"
                    f"SUMIF(SMS!A:A,A{index},SMS!I:I)+SUMIF(Social!A:A,A{index},Social!L:L),"
                    f"COUNTIF(Leads!A:A,A{index}))"
                ),
                f'=IF(F{index}=0,"",D{index}/F{index})',
                f'=IF(E{index}=0,"",D{index}/E{index})',
            ]
        )
    return {"SMS": sms, "Social": social, "Leads": lead_rows, "Costs": cost_rows, "Report": report}


def apply_report_values(campaigns: list[PmCampaign], reports: dict[UUID, dict], values: list[list]) -> None:
    """عددهای محاسبه‌شدهٔ تب Report را روی آمار کمپین می‌گذارد."""
    by_code = {row.code: row for row in campaigns}
    for raw in values[1:]:
        if not raw or raw[0] in (None, ""):
            continue
        campaign = by_code.get(str(raw[0]))
        if campaign is None or campaign.id not in reports:
            continue
        report = reports[campaign.id]
        report["cost_toman"] = _num(raw, 3)
        report["views"] = _num(raw, 4)
        report["leads"] = _num(raw, 5)
        report["cpl"] = _rate(raw, 6)
        report["cpv"] = _rate(raw, 7)
        report["source"] = "google"


def _credentials() -> dict | None:
    path = get_settings().perf_sheets_credentials_file.strip()
    if not path:
        return None
    file = Path(path)
    if not file.is_file():
        return None
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not data.get("client_email") or not data.get("private_key"):
        return None
    return data


async def _access_token(client: httpx.AsyncClient, creds: dict) -> str:
    now = int(time.time())
    if _TOKEN["token"] and int(_TOKEN["exp"]) > now + 60 and _TOKEN["email"] == creds["client_email"]:
        return str(_TOKEN["token"])
    header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claim = _b64(
        json.dumps(
            {
                "iss": creds["client_email"],
                "scope": "https://www.googleapis.com/auth/spreadsheets",
                "aud": "https://oauth2.googleapis.com/token",
                "iat": now,
                "exp": now + 3600,
            }
        ).encode()
    )
    key = serialization.load_pem_private_key(creds["private_key"].encode(), password=None)
    signature = key.sign(f"{header}.{claim}".encode(), padding.PKCS1v15(), hashes.SHA256())
    assertion = f"{header}.{claim}.{_b64(signature)}"
    response = await client.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
    )
    response.raise_for_status()
    payload = response.json()
    _TOKEN["token"] = payload["access_token"]
    _TOKEN["exp"] = now + int(payload.get("expires_in", 3600))
    _TOKEN["email"] = creds["client_email"]
    return str(payload["access_token"])


async def write_google(tables: dict[str, list[list]]) -> dict:
    settings = get_settings()
    sheet_id = spreadsheet_id(settings.perf_sheets_spreadsheet_id)
    creds = _credentials()
    if not sheet_id or creds is None:
        return {
            "pushed": False,
            "google_connected": False,
            "spreadsheet_url": "",
            "reason": "شناسهٔ گوگل‌شیت یا فایل سرویس‌اکانت تنظیم نشده است",
            "report_values": [],
        }
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            token = await _access_token(client, creds)
            headers = {"Authorization": f"Bearer {token}"}
            meta = await client.get(
                f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}",
                headers=headers,
                params={"fields": "sheets.properties.title"},
            )
            meta.raise_for_status()
            existing = {item["properties"]["title"] for item in meta.json().get("sheets", [])}
            missing = [title for title in _TABS if title not in existing]
            if missing:
                created = await client.post(
                    f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}:batchUpdate",
                    headers=headers,
                    json={"requests": [{"addSheet": {"properties": {"title": title}}} for title in missing]},
                )
                created.raise_for_status()
            cleared = await client.post(
                f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values:batchClear",
                headers=headers,
                json={"ranges": [f"{title}!A:Z" for title in _TABS]},
            )
            cleared.raise_for_status()
            updated = await client.post(
                f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values:batchUpdate",
                headers=headers,
                params={"valueInputOption": "USER_ENTERED"},
                json={
                    "data": [
                        {"range": f"{title}!A1", "majorDimension": "ROWS", "values": tables[title]}
                        for title in _TABS
                    ],
                },
            )
            updated.raise_for_status()
            read = await client.get(
                f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/Report!A1:H",
                headers=headers,
                params={"valueRenderOption": "UNFORMATTED_VALUE"},
            )
            read.raise_for_status()
            values = read.json().get("values") or []
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        return {
            "pushed": False,
            "google_connected": False,
            "spreadsheet_url": url,
            "reason": f"گوگل‌شیت به‌روز نشد: {exc}",
            "report_values": [],
        }
    return {
        "pushed": True,
        "google_connected": True,
        "spreadsheet_url": url,
        "reason": "",
        "report_values": values,
    }


async def refresh_sheet(db: AsyncSession, organization_id: UUID, *, push: bool = True) -> SheetState:
    """ردیف‌ها را می‌سازد، در گوگل‌شیت می‌نویسد و آمار را از تب Report برمی‌گرداند."""
    campaigns = list(
        (
            await db.scalars(
                select(PmCampaign)
                .where(PmCampaign.organization_id == organization_id)
                .order_by(PmCampaign.created_at.desc())
            )
        ).all()
    )
    sends = list(
        (await db.scalars(select(PmSmsSend).where(PmSmsSend.organization_id == organization_id))).all()
    )
    stories = list(
        (await db.scalars(select(PmStory).where(PmStory.organization_id == organization_id))).all()
    )
    leads = list((await db.scalars(select(PmLead).where(PmLead.organization_id == organization_id))).all())
    costs = list((await db.scalars(select(PmCost).where(PmCost.organization_id == organization_id))).all())
    pages = {
        row.id: row
        for row in (await db.scalars(select(PmPage).where(PmPage.organization_id == organization_id))).all()
    }
    paid_ids, linked_ids = await load_settlement(db, organization_id)
    reports = {
        campaign.id: report_from_parts(
            campaign,
            [row for row in sends if row.campaign_id == campaign.id],
            [row for row in stories if row.campaign_id == campaign.id],
            [row for row in leads if row.campaign_id == campaign.id],
            pages,
            paid_ids,
            linked_ids,
            [row for row in costs if (row.campaign_code or "").strip() == campaign.code],
        )
        for campaign in campaigns
    }
    tables = build_tables(campaigns, sends, stories, leads, costs, pages, paid_ids, linked_ids)
    if push:
        remote = await write_google(tables)
    else:
        remote = {
            "pushed": False,
            "google_connected": False,
            "spreadsheet_url": "",
            "reason": "",
            "report_values": [],
        }
    if remote["report_values"]:
        apply_report_values(campaigns, reports, remote["report_values"])
    sources: dict = {}
    if remote["google_connected"]:
        from app.perf.services.source_sheets import sync_source_sheets

        sources = await sync_source_sheets(
            campaigns, sends, stories, costs, pages, paid_ids, linked_ids
        )
    note = sources.get("note") or ""
    reason = remote["reason"]
    if note and not reason:
        reason = note
    return SheetState(
        campaigns=campaigns,
        sends=sends,
        stories=stories,
        costs=costs,
        pages=pages,
        reports=reports,
        google_connected=bool(remote["google_connected"]),
        spreadsheet_url=remote["spreadsheet_url"],
        reason=reason,
        sources=sources,
        tables=tables,
    )
