"""کار بعدی از روی ثبت‌ها. هیچ ارسالی، خریدی یا توقفی اینجا انجام نمی‌شود."""

from __future__ import annotations


def next_steps(campaigns, panels, waiting_payments: int, cars, stories, sends, limit: int = 8) -> list[dict]:
    items: list[dict] = []
    for panel in panels:
        if _get(panel, "low"):
            items.append(_item("warn", "شارژ", f"{_get(panel, 'name')}: موجودی کم است", "/perf/money"))
    if waiting_payments:
        items.append(_item("warn", "پول", f"{waiting_payments} پرداخت منتظر تأیید", "/perf/money"))
    active = [row for row in campaigns if getattr(row, "status", "") == "active"]
    gaps = []
    for campaign in active:
        gap = campaign_gap(campaign, cars, stories, sends)
        if gap:
            gaps.append(gap)
    items.extend(gaps[:limit])
    return items


def campaign_gap(campaign, cars, stories, sends) -> dict | None:
    cid = campaign.id
    mine_cars = [row for row in cars if row.campaign_id == cid]
    mine_stories = [row for row in stories if row.campaign_id == cid]
    mine_sends = [row for row in sends if row.campaign_id == cid]
    new_cars = [row for row in mine_cars if row.status == "new"]
    budget = campaign.budget_toman or 0
    social = f"/perf/social?campaign={cid}"
    sms = f"/perf/sms?campaign={cid}"
    code = campaign.code
    if new_cars and budget <= 0:
        return _item("", "بودجه", f"{code}: {len(new_cars)} ماشین آمده و بودجه ندارد", social, "budget")
    if budget > 0 and not mine_stories:
        return _item("", "چیدن پیج", f"{code}: بودجه هست و هنوز پیجی چیده نشده", social, "pages")
    waiting = [row for row in mine_stories if row.status != "published"]
    if waiting:
        return _item("", "انتشار", f"{code}: {len(waiting)} قرار هنوز منتشر نشده", social, "publish")
    blank = [
        row
        for row in mine_stories
        if row.status == "published" and not (row.views or row.impressions or row.leads)
    ]
    if blank:
        return _item("", "اینسایت", f"{code}: {len(blank)} انتشار بدون عدد اینسایت", social, "insight")
    if "sms" in (campaign.channels or "") and not mine_sends:
        return _item("", "پیامک", f"{code}: پیامک این کمپین ثبت نشده", sms, "sms")
    undelivered = [
        row
        for row in mine_sends
        if (row.recipient_count or 0) > 0 and not (row.delivered_count or 0) and row.sent_at
    ]
    if undelivered:
        return _item("", "تحویل", f"{code}: فایل تحویل ارسال ثبت نشده", sms, "delivery")
    return None


def _get(row, name: str, default=None):
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def _item(tone: str, label: str, title: str, href: str, step: str = "") -> dict:
    if step:
        href = f"{href}{'&' if '?' in href else '?'}step={step}"
    return {"tone": tone, "label": label, "title": title, "href": href}
