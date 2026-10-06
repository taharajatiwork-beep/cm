"""اتصال‌های بیرونی. بدون تنظیم، هیچ تماس شبکه‌ای زده نمی‌شود."""

from __future__ import annotations

import base64
import json
from datetime import date, datetime

import httpx

from app.core.config import get_settings
from app.perf.services.common import PerfError

_SUCCESS = {2, 3, 4, 6, 9, 10, 11, 12}


def count_delivered(rows: list[object]) -> int:
    """«دریافت موفق» تحویل است. وضعیت منتظر گزارش، لیست سیاه است و شمرده نمی‌شود."""
    delivered = 0
    for raw in rows:
        text = str(raw or "").strip()
        if "منتظر" in text:
            continue
        if "موفق" in text or "تحویل" in text or "deliver" in text.lower():
            delivered += 1
            continue
        try:
            if int(float(text)) in _SUCCESS:
                delivered += 1
        except ValueError:
            continue
    return delivered


def sheet_day(header: list[str], rows: list[list]) -> date | None:
    index = next((i for i, name in enumerate(header) if "تاریخ" in name or "date" in name.lower()), None)
    if index is None:
        return None
    for line in rows:
        if index >= len(line) or not line[index]:
            continue
        text = str(line[index])[:10]
        try:
            parsed = datetime.fromisoformat(text).date()
        except ValueError:
            return None
        if parsed.year < 1900:
            return None
        return parsed
    return None


def pick_send(sends: list, row_count: int, day: date | None):
    """ارسال را با تاریخ میلادی یا تعداد گیرنده پیدا می‌کند، نه با انتخاب دستی ردیف."""
    pool = list(sends)
    if day is not None:
        same_day = [row for row in pool if getattr(row, "sent_at", None) and row.sent_at.date() == day]
        if len(same_day) == 1:
            return same_day[0]
        if same_day:
            pool = same_day
    close = []
    for row in pool:
        count = row.recipient_count or 0
        if count and abs(count - row_count) <= max(2, int(row_count * 0.02)):
            close.append(row)
    if len(close) == 1:
        return close[0]
    if len(pool) == 1 and row_count:
        return pool[0]
    return None


async def send_isms_service(
    *,
    username: str,
    password: str,
    sender: str,
    mobiles: list[str],
    body: str,
    url: str | None = None,
) -> dict:
    if not username or not password:
        raise PerfError("نام کاربری یا رمز وب‌سرویس آی‌اس‌ام‌اس در پنل نیست")
    if len(mobiles) > 20:
        raise PerfError("sendWS فقط برای پیام خدماتی است؛ برای تبلیغ انبوه از فایل پنل استفاده کنید")
    if not mobiles:
        raise PerfError("شماره‌ای نیست")
    target = url or get_settings().isms_send_url
    params = {
        "username": username,
        "password": password,
        "sender": sender,
        "mobiles": ",".join(mobiles),
        "body": body,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(target, params=params)
    return {"status_code": response.status_code, "body": response.text[:500], "url": target}


async def pishgam_call(
    *,
    api_base: str,
    token: str,
    path: str,
    method: str = "GET",
    payload: dict | None = None,
) -> dict:
    if not api_base or not token:
        raise PerfError("آدرس یا توکن پیشگامان در تنظیمات پنل نیست. مستند API این پنل هنوز وارد نشده است.")
    url = api_base.rstrip("/") + path
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.request(method, url, headers=headers, json=payload)
    return {"status_code": response.status_code, "body": response.text[:500], "url": url}


async def read_insight_image(data: bytes, content_type: str) -> dict:
    settings = get_settings()
    if not settings.llm_api_key or settings.llm_provider in ("", "off", "rules", "fake"):
        return {
            "ok": False,
            "reason": "خواندن اسکرین‌شات به کلید مدل زبانی نیاز دارد. اعداد را دستی وارد کنید.",
            "fields": {},
        }
    encoded = base64.b64encode(data).decode()
    payload = {
        "model": settings.llm_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "اعداد اینسایت استوری اینستاگرام را به JSON برگردان. کلیدها: "
                            "views, impressions, reach, likes, replies, shares, link_clicks, exited, leads. "
                            "اگر عددی نیست null بگذار."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{encoded}"}},
                ],
            }
        ],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.llm_api_base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json=payload,
        )
    if response.status_code >= 400:
        return {"ok": False, "reason": "مدل زبانی تصویر را نخواند", "fields": {}}
    try:
        content = response.json()["choices"][0]["message"]["content"]
        fields = json.loads(content) if isinstance(content, str) else content
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return {"ok": False, "reason": "پاسخ مدل قابل خواندن نبود", "fields": {}}
    if not isinstance(fields, dict):
        return {"ok": False, "reason": "پاسخ مدل قابل خواندن نبود", "fields": {}}
    return {"ok": True, "reason": "", "fields": fields}


async def push_sheet(kind: str, rows: list[dict]) -> dict:
    url = get_settings().perf_sheets_webhook.strip()
    if not url:
        return {"pushed": False, "reason": "آدرس همگام‌سازی گوگل شیت تنظیم نشده است"}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json={"kind": kind, "rows": rows})
    return {"pushed": response.status_code < 400, "status_code": response.status_code}
