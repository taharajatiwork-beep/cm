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
    # swagger پیشگامان: توکن خام در هدر Authorization می‌رود (نه Bearer).
    headers = {"Authorization": token}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.request(method, url, headers=headers, json=payload)
    return {"status_code": response.status_code, "body": response.text[:500], "url": url}


# جدول کد وضعیت دلیوری از مستند رسمی پیشگامان (swagger: ارسال پیامک پیشگام رایان).
PISHGAM_DELIVERY_TEXTS = {
    0: "نامشخص",
    1: "رسیده به گوشی",
    2: "نرسیده به گوشی",
    3: "ارسال شده به اپراتور",
    4: "رسیده به مخابرات",
    5: "نرسیده به مخابرات",
    6: "پیامک توسط سرور دریافت نشد",
    7: "خطا در ارسال",
    8: "منتظر ارسال",
    9: "ارسال شد",
    10: "ارسال نشده",
    11: "منقضی",
    12: "در حال ارسال",
    14: "لیست سیاه",
    15: "متن پیامک فیلتر است",
    16: "حذف شده",
    17: "در انتظار تایید",
    18: "کمبود اعتبار",
    19: "در حال آماده‌سازی",
    20: "آماده شده برای ارسال",
    21: "عدم دسترسی",
    22: "متن پیام خالی است",
    24: "نام کاربری یا رمز اشتباه است",
    26: "فرستنده معتبر نیست",
    27: "موبایل معتبر نیست",
    29: "ذخیره شده",
    30: "جدول لیست سیاه",
    33: "تایید نشده",
    34: "شناسه پیامک یافت نشد",
    35: "در صف ارسال",
    36: "متن پیام نامعتبر است",
    37: "متن پیام حاوی لینک است",
    38: "بسته ارسالی بیشتر از ۱۰۰ است",
    39: "تعداد پیام و شماره همخوانی ندارد",
    40: "زمان ارسال نامعتبر است",
    41: "تعداد پیام و کدینگ همخوانی ندارد",
    42: "اپراتور پشتیبانی نمی‌شود",
    43: "تعرفه نامعتبر است",
    44: "کدینگ پیام پشتیبانی نمی‌شود",
    45: "خط ارسال‌کننده غیرفعال است",
    46: "خط ارسال‌کننده منقضی است",
    47: "شماره گیرنده از طرف اپراتور پشتیبانی نمی‌شود",
    48: "زمان ارسال غیرمجاز است",
    49: "لغو از سوی کاربر",
    50: "کدینگ غیرمجاز",
    51: "لغو از سوی اپراتور",
    52: "منقضی از سوی اپراتور",
    53: "ردشده از سمت اپراتور",
    54: "نام کاربری یافت نشد",
    55: "کاربر منقضی است",
    56: "کاربر غیرفعال است",
    57: "udh نامعتبر است",
    58: "خطای سیستم از سوی اپراتور",
    59: "غیرمجاز",
    60: "ردشده توسط مخابرات",
    61: "درخواست نامعتبر",
    62: "خط ارسال‌کننده بلاک شده است",
    63: "اپراتور در دسترس نیست",
    67: "صدا دارای خطا است",
    68: "آی‌پی نامعتبر است",
}


def delivery_text(code: object) -> str:
    """کد دلیوری پیشگامان یا متن خام را به «رسیده/نرسیده» فارسی تبدیل می‌کند."""
    text = str(code or "").strip()
    if not text:
        return ""
    try:
        return PISHGAM_DELIVERY_TEXTS.get(int(float(text)), text)
    except ValueError:
        return text


def pishgam_delivered_count(statuses: list[object]) -> int:
    """«رسیده به گوشی» تحویل است؛ بقیه شمرده نمی‌شوند."""
    delivered = 0
    for raw in statuses:
        try:
            if int(float(raw)) == 1:
                delivered += 1
        except (ValueError, TypeError):
            continue
    return delivered


async def read_insight_image(data: bytes, content_type: str) -> dict:
    settings = get_settings()
    if not settings.llm_external_enabled:
        return {
            "ok": False,
            "reason": "ارسال تصویر به مدل بیرونی خاموش است (LLM_EXTERNAL_ENABLED=false).",
            "fields": {},
        }
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
