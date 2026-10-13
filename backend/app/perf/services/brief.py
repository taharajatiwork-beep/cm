"""بریف کمپین: پیش‌نویس با LLM، در نبودش قالب آماده. ساختار بریف مثل نمونهٔ شعبهٔ نور."""

from __future__ import annotations

import json

from app.ai.llm import get_llm_client
from app.perf.models import PmCampaign

_WEEKDAYS = ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه")

_BRIEF_SYSTEM = (
    "تو برنامه‌ریز تبلیغات یک گروه خودرویی ایرانی هستی. برای کمپین داده‌شده یک بریف هفتگی فارسی می‌سازی. "
    "فقط JSON معتبر برگردان. لحن کوتاه و عملیاتی؛ ادعای بی‌دلیل ننویس. عدد بودجه را کمتر از ۱۰۰٪ هفته بین فازها تقسیم نکن."
)

_BRIEF_USER_TMPL = """کمپین: {title} (کد {code})
برند: {brand}
هدف: {goal}
از {start} تا {end}
بودجه: {budget} تومان
کانال‌ها: {channels}

این JSON را با همین کلیدها برگردان:
{{
  "slogan": "شعار کمپین",
  "goals": ["هدف ۱", "هدف ۲"],
  "angle": "زاویه محتوایی در یک جمله",
  "content_plan": [7 آیتم {{"day": "شنبه", "kind": "پست اصلی|استوری|ریلز|کروسل|CTA", "details": "جزئیات محتوا", "place": "محل انتشار"}}],
  "caption": "کپشن آمادهٔ پست اصلی با جای‌خالی [آدرس] و [تلفن]",
  "reels": ["ایدهٔ ریلز ۱", "ایدهٔ ریلز ۲"],
  "ad_phases": [{{"name": "فاز ۱ آگاهی‌سازی", "goal": "هدف فاز", "audience": "مخاطب فاز", "budget_share": 40, "text": "متن تبلیغ"}}],
  "ctas": ["CTA ۱", "CTA ۲"],
  "hashtags": ["#هشتگ"],
  "highlight": "نام هایلایت",
  "pinned": "متن پست پین‌شده"
}}"""


def parse_brief(row: PmCampaign) -> dict:
    """بریف ذخیره‌شده را دیکشنری می‌کند؛ خرابی JSON خالی برگرداند."""
    try:
        data = json.loads(row.brief or "")
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def normalize_brief(raw: dict, campaign: PmCampaign) -> dict:
    """فیلدهای بریف را به شکل ثابت درمی‌آورد تا UI همیشه همان شکل را بخواند."""
    out = {
        "slogan": _str(raw.get("slogan")),
        "goals": _strs(raw.get("goals")),
        "angle": _str(raw.get("angle")),
        "content_plan": _plan(raw.get("content_plan")),
        "caption": _str(raw.get("caption")),
        "reels": _strs(raw.get("reels")),
        "ad_phases": _phases(raw.get("ad_phases")),
        "ctas": _strs(raw.get("ctas")),
        "hashtags": _strs(raw.get("hashtags")),
        "highlight": _str(raw.get("highlight")),
        "pinned": _str(raw.get("pinned")),
    }
    if not out["slogan"]:
        out["slogan"] = f"{campaign.brand or campaign.title} | {campaign.goal or 'کمپین این هفته'}".strip(" |")
    return out


def _str(value) -> str:
    return str(value).strip() if value is not None else ""


def _strs(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _plan(value) -> list[dict]:
    rows = value if isinstance(value, list) else []
    out = [
        {
            "day": _str(item.get("day")) if isinstance(item, dict) else "",
            "kind": _str(item.get("kind")) if isinstance(item, dict) else "",
            "details": _str(item.get("details")) if isinstance(item, dict) else "",
            "place": _str(item.get("place")) if isinstance(item, dict) else "",
        }
        for item in rows
    ]
    out = [row for row in out if row["day"] or row["details"]]
    while len(out) < 7:
        out.append({"day": _WEEKDAYS[len(out)], "kind": "", "details": "", "place": ""})
    return out[:7]


def _phases(value) -> list[dict]:
    rows = value if isinstance(value, list) else []
    out = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        share = item.get("budget_share")
        try:
            share = max(0, min(100, int(share))) if share is not None else None
        except (TypeError, ValueError):
            share = None
        out.append({
            "name": _str(item.get("name")),
            "goal": _str(item.get("goal")),
            "audience": _str(item.get("audience")),
            "budget_share": share,
            "text": _str(item.get("text")),
        })
    return [row for row in out if row["name"] or row["goal"] or row["text"]]


def _template_draft(campaign: PmCampaign) -> dict:
    brand = campaign.brand or "ستوده"
    plan_kinds = (("پست اصلی", "معرفی"), ("استوری", "پشت‌صحنه"), ("پست", "موجودی و خودروهای مناسب"), ("استوری", "خدمات"), ("ریلز کوتاه", "دلایل مراجعه"), ("کروسل / پست مشتری", "نظر مشتری یا پیشنهاد ویژه"), ("استوری CTA", "یادآوری + دعوت به بازدید"))
    plan = [
        {"day": day, "kind": kind, "details": f"{topic} — {brand}", "place": "پیج اصلی"}
        for day, (kind, topic) in zip(_WEEKDAYS, plan_kinds, strict=False)
    ]
    budget = campaign.budget_toman or 0
    return {
        "slogan": f"{campaign.title} — {campaign.goal or brand}".strip(" —"),
        "goals": [campaign.goal] if campaign.goal else ["معرفی کامل", "جذب ورودی با CTA"],
        "angle": campaign.goal or "معرفی و جذب ورودی",
        "content_plan": plan,
        "caption": f"{campaign.title} آمادهٔ خدمت است.\nآدرس: [آدرس]\nساعات کاری: [ساعات کاری]\nتماس: [شماره تماس]",
        "reels": [f"«۳ دلیل {campaign.title}»", f"«مسیر رسیدن به {campaign.title} در ۳۰ ثانیه»"],
        "ad_phases": [
            {
                "name": "فاز آگاهی‌سازی",
                "goal": "بازدید از پست معرفی",
                "audience": "علاقه‌مندان مرتبط با برند و منطقه",
                "budget_share": 40 if budget else None,
                "text": f"{campaign.title} منتظر شماست — همین حالا مسیر را بگیرید.",
            },
            {
                "name": "فاز تبدیل (ریتارگتینگ)",
                "goal": "کلیک روی مسیر یا تماس",
                "audience": "کسانی که پست و استوری‌ها را دیده‌اند",
                "budget_share": None,
                "text": f"{brand} منتظرتان است — همین حالا تماس بگیرید.",
            },
        ],
        "ctas": ["مسیر شعبه", "تماس", "درخواست مشاوره رایگان", "مشاهدهٔ موجودی"],
        "hashtags": [f"#{brand.replace(' ', '_')}" if brand else "#کمپین"],
        "highlight": campaign.title,
        "pinned": f"این هفته: {campaign.title}",
    }


async def draft_brief(campaign: PmCampaign) -> tuple[dict, str]:
    """(بریف نرمال‌شده، منبع) — منبع llm یا template."""
    from app.core.config import get_settings

    client = get_llm_client() if get_settings().llm_external_enabled else None
    if client is not None:
        budget = f"{campaign.budget_toman:,}" if campaign.budget_toman else "نامشخص"
        user = _BRIEF_USER_TMPL.format(
            title=campaign.title,
            code=campaign.code,
            brand=campaign.brand or "—",
            goal=campaign.goal or "—",
            start=campaign.starts_on or "—",
            end=campaign.ends_on or "—",
            budget=budget,
            channels=", ".join(part for part in (campaign.channels or "").split(",") if part) or "—",
        )
        try:
            raw = await client.chat_json(system=_BRIEF_SYSTEM, user=user, temperature=0.3)
            return normalize_brief(raw, campaign), "llm"
        except Exception:
            pass  # LLM در دسترس نبود؛ قالب جایگزین
    return _template_draft(campaign), "template"