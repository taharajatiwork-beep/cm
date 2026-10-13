"""ردیف تازه را به کپی سه شیت اصلی اضافه می‌کند.

کمپین به دفتر شماره، هزینه به Cost Tracking، پیامک و سوشال به reporter.
ردیف‌هایی که از قبل در همان شیت هستند دوباره نوشته نمی‌شوند و هیچ تبی پاک نمی‌شود.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import httpx

from app.core.config import get_settings
from app.core.jalali import format_jalali
from app.perf.campaign_register import sequence_of
from app.perf.models import PmCampaign, PmCost, PmSmsSend, PmStory
from app.perf.services.reports import booked_cost, placement_live, story_rates
from app.perf.services.sheets import _access_token, _credentials, spreadsheet_id

_SMS_HEADERS = ["کمپین", "تاریخ", "خط", "گیرنده", "صفحه", "هزینه", "رسیده", "تماس", "ورودی", "متن"]


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _amount(value) -> int:
    text = _text(value).replace(",", "").replace("٬", "")
    if not text:
        return 0
    try:
        return int(round(float(text)))
    except ValueError:
        return 0


def _when(value: date | datetime | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = value.date()
    return format_jalali(value).replace("/", "-")


def pending_source_export(rows: list) -> list:
    """ردیف‌هایی که هنوز به شیت منبع فرستاده نشده‌اند — کلید پایدار همان id/کد است، نه ساعت آرشیو."""
    return [row for row in rows if getattr(row, "source_sheet_exported_at", None) is None]


def since_import(rows: list) -> list:
    """سازگاری با تست‌های قدیمی — همان pending_source_export."""
    return pending_source_export(rows)


def _tag(code: str) -> str:
    match_end = 0
    for index, char in enumerate(code):
        if char.isalpha():
            match_end = index + 1
        else:
            break
    return code[:match_end]


def register_rows(campaigns: list[PmCampaign], existing_codes: set[str]) -> list[list]:
    """ردیف‌های دفتر «Campaign Number» برای کدهایی که هنوز آنجا نیستند."""
    rows = []
    seen = set(existing_codes)
    for campaign in campaigns:
        code = _text(campaign.code)
        if not code or "-" in code or code in seen or sequence_of(code) is None:
            continue
        seen.add(code)
        when = campaign.starts_on or (campaign.created_at.date() if campaign.created_at else None)
        rows.append([_tag(code), sequence_of(code), code, campaign.title, _when(when)])
    return rows


def _cost_key(campaign: str, amount, description: str) -> tuple[str, int, str]:
    return (_text(campaign), _amount(amount), _text(description)[:80])


def cost_rows(costs: list[PmCost], existing: set[tuple[str, int, str]]) -> tuple[list[list], list[list]]:
    """ردیف Sheet3 و Log. کلید تکراری: کمپین، مبلغ، شرح."""
    sheet_rows: list[list] = []
    log_rows: list[list] = []
    seen = set(existing)
    for cost in costs:
        key = _cost_key(cost.campaign_code, cost.amount_toman, cost.description)
        if key in seen or key[1] <= 0:
            continue
        seen.add(key)
        when = _when(cost.spent_on)
        sheet_rows.append(
            [
                cost.cost_number or "",
                when,
                cost.amount_toman or 0,
                cost.kind or "",
                cost.detail or "",
                cost.brand or "",
                cost.campaign_code or "",
                cost.cost_center or "",
                cost.description or "",
            ]
        )
        log_rows.append(
            [
                cost.cost_number or "",
                "",
                when,
                cost.amount_toman or 0,
                cost.kind or "",
                cost.detail or "",
                cost.brand or "",
                cost.campaign_code or "",
                cost.cost_center or "",
                cost.description or "",
                when[:7],
            ]
        )
    return sheet_rows, log_rows


def sms_rows(sends: list[PmSmsSend], codes: dict, existing: set[tuple[str, int, str]]) -> list[list]:
    rows = []
    seen = set(existing)
    for send in sends:
        code = _text(codes.get(send.campaign_id, ""))
        body = _text(send.body).replace("\n", " ")
        key = (code, send.recipient_count or 0, body[:80])
        if key in seen or (not code and not body):
            continue
        seen.add(key)
        rows.append(
            [
                code,
                _when(send.sent_at),
                send.sender_line or "",
                send.recipient_count or 0,
                send.pages or 0,
                send.cost_toman or 0,
                send.delivered_count or 0,
                send.calls or 0,
                send.leads or 0,
                send.body or "",
            ]
        )
    return rows


def social_tab(page: str, bale_pages: set[str], instagram_pages: set[str]) -> str:
    name = _text(page)
    if name and name in bale_pages and name not in instagram_pages:
        return "BaleRubika"
    return "Instagram-S"


def _social_key(code: str, page: str, views, leads) -> tuple[str, str, int, int]:
    return (_text(code), _text(page), _amount(views), _amount(leads))


def social_rows(
    stories: list[PmStory],
    codes: dict,
    pages: dict,
    header: list[str],
    existing: set[tuple[str, str, int, int]],
    *,
    bale: bool,
    paid_ids: set | None = None,
    linked_ids: set | None = None,
) -> list[list]:
    rows = []
    seen = set(existing)
    for story in stories:
        if not placement_live(story):
            continue
        code = _text(codes.get(story.campaign_id, ""))
        page = pages.get(story.page_id)
        page_name = page.name if page else ""
        key = _social_key(code, page_name, story.views, story.leads)
        if not code or key in seen:
            continue
        seen.add(key)
        cost = booked_cost(story, paid_ids, linked_ids)
        rates = story_rates(story)
        values = {
            "campaign": code,
            "page name": page_name,
            "publication date": _when(story.published_on),
            "cost": cost,
            "views": story.views or 0,
            "impressions": story.impressions or 0,
            "accounts reached": story.reach or 0,
            "likes": story.likes or 0,
            "replies": story.replies or 0,
            "shares": story.shares or 0,
            "link clicks": story.link_clicks or 0,
            "sticker taps": story.sticker_taps or 0,
            "navigation": story.navigation or 0,
            "forward": story.forward or 0,
            "next story": story.next_story or 0,
            "back": story.back or 0,
            "exited": story.exited or 0,
            "lead": story.leads or 0,
            "cpv": rates["cpv"] if rates["cpv"] is not None else "",
            "cpl": rates["cpl"] if rates["cpl"] is not None else "",
        }
        if bale:
            values = {
                "campaign": code,
                "page name": page_name,
                "publication date": values["publication date"],
                "cost": cost,
                "views": story.views or 0,
                "lead": story.leads or 0,
                "cpv": values["cpv"],
                "cpl": values["cpl"],
            }
        width = max(len(header), 8 if bale else 22)
        row = [""] * width
        for index, name in enumerate(header):
            row[index] = values.get(name.strip().lower(), "")
        rows.append(row)
    return rows


def _quote(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


async def _get_values(client: httpx.AsyncClient, token: str, sheet_id: str, title: str, cells: str) -> list[list]:
    response = await client.get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{_quote(title)}!{cells}",
        headers={"Authorization": f"Bearer {token}"},
        params={"valueRenderOption": "UNFORMATTED_VALUE"},
    )
    if response.status_code == 400:
        return []
    response.raise_for_status()
    return response.json().get("values") or []


async def _append(client: httpx.AsyncClient, token: str, sheet_id: str, title: str, rows: list[list]) -> None:
    if not rows:
        return
    response = await client.post(
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{_quote(title)}!A1:append",
        headers={"Authorization": f"Bearer {token}"},
        params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
        json={"majorDimension": "ROWS", "values": rows},
    )
    response.raise_for_status()


async def _ensure_tab(client: httpx.AsyncClient, token: str, sheet_id: str, title: str) -> None:
    meta = await client.get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}",
        headers={"Authorization": f"Bearer {token}"},
        params={"fields": "sheets.properties.title"},
    )
    meta.raise_for_status()
    names = {item["properties"]["title"] for item in meta.json().get("sheets", [])}
    if title in names:
        return
    created = await client.post(
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}:batchUpdate",
        headers={"Authorization": f"Bearer {token}"},
        json={"requests": [{"addSheet": {"properties": {"title": title}}}]},
    )
    created.raise_for_status()
    await _append(client, token, sheet_id, title, [_SMS_HEADERS])


def _column_keys(rows: list[list], index: int) -> set[str]:
    found = set()
    for row in rows[1:]:
        if index < len(row):
            text = _text(row[index])
            if text:
                found.add(text)
    return found


def _indexed(header: list[str], *names: str) -> int | None:
    folded = [cell.strip().lower() for cell in header]
    for name in names:
        if name in folded:
            return folded.index(name)
    return None


def describe_sources(counts: dict[str, int]) -> str:
    labels = (
        ("register", "دفتر کمپین"),
        ("costs", "هزینه"),
        ("sms", "پیامک"),
        ("social", "سوشال"),
    )
    parts = [f"{label} {counts[key]}" for key, label in labels if counts.get(key)]
    if not parts:
        return "سه شیت اصلی ردیف تازه‌ای نداشتند."
    return "به شیت‌های اصلی اضافه شد: " + "، ".join(parts) + "."


async def sync_source_sheets(
    campaigns: list[PmCampaign],
    sends: list[PmSmsSend],
    stories: list[PmStory],
    costs: list[PmCost],
    pages: dict,
    paid_ids: set | None,
    linked_ids: set | None,
    *,
    write: bool = True,
) -> dict:
    settings = get_settings()
    creds = _credentials()
    register_id = spreadsheet_id(settings.perf_sheets_register_campaign_id)
    cost_id = spreadsheet_id(settings.perf_sheets_cost_tracking_id)
    reporter_id = spreadsheet_id(settings.perf_sheets_reporter_id)
    counts = {"register": 0, "costs": 0, "sms": 0, "social": 0}
    if creds is None or not any((register_id, cost_id, reporter_id)):
        return {**counts, "note": ""}
    codes = {row.id: row.code for row in campaigns}
    stamped = datetime.now(UTC)
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            token = await _access_token(client, creds)
            if register_id:
                current = await _get_values(client, token, register_id, "Campaign Number", "A:E")
                header = current[0] if current else []
                code_at = _indexed(header, "campaign number")
                existing = _column_keys(current, code_at if code_at is not None else 2)
                pending_campaigns = pending_source_export(campaigns)
                fresh = register_rows(pending_campaigns, existing)
                if write:
                    await _append(client, token, register_id, "Campaign Number", fresh)
                    exported_codes = {row[2] for row in fresh if len(row) > 2}
                    for campaign in pending_campaigns:
                        if _text(campaign.code) in exported_codes:
                            campaign.source_sheet_exported_at = stamped
                counts["register"] = len(fresh)
            if cost_id:
                sheet = await _get_values(client, token, cost_id, "Sheet3", "A:I")
                log = await _get_values(client, token, cost_id, "Log", "A:K")
                existing_costs = _cost_keys(sheet) | _cost_keys(log)
                pending_costs = pending_source_export(costs)
                sheet_fresh, log_fresh = cost_rows(pending_costs, existing_costs)
                if write:
                    await _append(client, token, cost_id, "Sheet3", sheet_fresh)
                    await _append(client, token, cost_id, "Log", log_fresh)
                    for cost in pending_costs:
                        key = _cost_key(cost.campaign_code, cost.amount_toman, cost.description)
                        if key[1] > 0 and key not in existing_costs:
                            cost.source_sheet_exported_at = stamped
                counts["costs"] = len(sheet_fresh)
            if reporter_id:
                if write:
                    await _ensure_tab(client, token, reporter_id, "SMS")
                sms_table = await _get_values(client, token, reporter_id, "SMS", "A:J")
                sms_header = sms_table[0] if sms_table else _SMS_HEADERS
                code_at = _indexed(sms_header, "کمپین", "campaign")
                count_at = _indexed(sms_header, "گیرنده")
                body_at = _indexed(sms_header, "متن")
                existing_sms = set()
                for row in sms_table[1:]:
                    existing_sms.add(
                        (
                            _text(row[code_at]) if code_at is not None and code_at < len(row) else "",
                            _amount(row[count_at]) if count_at is not None and count_at < len(row) else 0,
                            _text(row[body_at]).replace("\n", " ")[:80] if body_at is not None and body_at < len(row) else "",
                        )
                    )
                pending_sends = pending_source_export(sends)
                fresh_sms = sms_rows(pending_sends, codes, existing_sms)
                if write:
                    await _append(client, token, reporter_id, "SMS", fresh_sms)
                    for send in pending_sends:
                        code = _text(codes.get(send.campaign_id, ""))
                        body = _text(send.body).replace("\n", " ")
                        key = (code, send.recipient_count or 0, body[:80])
                        if key not in existing_sms and (code or body):
                            send.source_sheet_exported_at = stamped
                counts["sms"] = len(fresh_sms)

                instagram = await _get_values(client, token, reporter_id, "Instagram-S", "A:V")
                bale = await _get_values(client, token, reporter_id, "BaleRubika", "A:H")
                ig_header = instagram[0] if instagram else []
                bale_header = bale[0] if bale else []
                ig_pages = _column_keys(instagram, _indexed(ig_header, "page name") or 1)
                bale_pages = _column_keys(bale, _indexed(bale_header, "page name") or 1)
                ig_existing = _social_keys(instagram, ig_header)
                bale_existing = _social_keys(bale, bale_header)
                ig_stories = []
                bale_stories = []
                for story in pending_source_export(stories):
                    page = pages.get(story.page_id)
                    name = page.name if page else ""
                    if social_tab(name, bale_pages, ig_pages) == "BaleRubika":
                        bale_stories.append(story)
                    else:
                        ig_stories.append(story)
                ig_fresh = social_rows(
                    ig_stories, codes, pages, ig_header, ig_existing, bale=False, paid_ids=paid_ids, linked_ids=linked_ids
                )
                bale_fresh = social_rows(
                    bale_stories, codes, pages, bale_header, bale_existing, bale=True, paid_ids=paid_ids, linked_ids=linked_ids
                )
                if write:
                    await _append(client, token, reporter_id, "Instagram-S", ig_fresh)
                    await _append(client, token, reporter_id, "BaleRubika", bale_fresh)
                    for story in ig_stories + bale_stories:
                        story.source_sheet_exported_at = stamped
                counts["social"] = len(ig_fresh) + len(bale_fresh)
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        return {**counts, "note": f"شیت‌های اصلی به‌روز نشد: {exc}"}
    return {**counts, "note": describe_sources(counts)}


def _cost_keys(rows: list[list]) -> set[tuple[str, int, str]]:
    if not rows:
        return set()
    header = rows[0]
    campaign_at = _indexed(header, "کمپین", "campaign")
    amount_at = _indexed(header, "مبلغ (تومان)", "مبلغ")
    detail_at = _indexed(header, "شرح هزینه", "شرح")
    found = set()
    if campaign_at is None or amount_at is None:
        return found
    for row in rows[1:]:
        description = _text(row[detail_at]) if detail_at is not None and detail_at < len(row) else ""
        campaign = _text(row[campaign_at]) if campaign_at < len(row) else ""
        amount = _amount(row[amount_at]) if amount_at < len(row) else 0
        if amount:
            found.add(_cost_key(campaign, amount, description))
    return found


def _social_keys(rows: list[list], header: list[str]) -> set[tuple[str, str, int, int]]:
    if not rows:
        return set()
    code_at = _indexed(header, "campaign")
    page_at = _indexed(header, "page name")
    views_at = _indexed(header, "views")
    lead_at = _indexed(header, "lead")
    found = set()
    if code_at is None or page_at is None:
        return found
    for row in rows[1:]:
        found.add(
            _social_key(
                _text(row[code_at]) if code_at < len(row) else "",
                _text(row[page_at]) if page_at < len(row) else "",
                row[views_at] if views_at is not None and views_at < len(row) else 0,
                row[lead_at] if lead_at is not None and lead_at < len(row) else 0,
            )
        )
    return found
