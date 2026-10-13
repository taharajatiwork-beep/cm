"""محتوای واقعی تقویم آبان ۱۴۰۵، از فایل برنامهٔ اجرایی ستوده. عدد ساختگی ندارد."""

from __future__ import annotations

import json
from datetime import date, timedelta

# ۱ آبان ۱۴۰۵ = ۲۳ اکتبر ۲۰۲۶
ABAN_START = date(2026, 10, 23)
YEAR = 1405
MONTH = 8

# tier, format, channel, topic, cta, kpi
ROWS: list[tuple[str, str, str, str, str, str]] = [
    ("mid", "Reel", "Instagram", "مسیر مراجعه و معرفی شعبه شاخص ستوده", "مشاهده شعبه / تماس", "Reach, Saves"),
    ("long", "Story", "Instagram", "تیزر: این هفته چه شرایط فروشی فعال است؟", "مشاهده استوری بعدی", "Story Completion"),
    ("long", "Post/Carousel", "Instagram + Telegram", "خلاصه بخشنامه فعال هفته؛ بدون شلوغی، با CTA واضح", "دریافت شرایط کامل", "CTR, Leads"),
    ("mid", "Reel", "Instagram", "تور کوتاه شعبه: ورودی، شوروم، تیم فروش و تجربه مراجعه", "رزرو مشاوره", "Reach, DM"),
    ("long", "Story FAQ", "Instagram", "۳ سؤال پرتکرار درباره ثبت‌نام و تحویل", "ارسال سؤال / شماره", "Replies, Leads"),
    ("short", "Poll", "Story", "بین ۲ یا ۳ خودرو کدام انتخاب شماست؟", "رأی دادن", "Engagement"),
    ("long", "Retargeting", "Paid Media", "ریمارکتینگ بازدیدکنندگان صفحه شرایط فروش", "تکمیل فرم", "CPL, CVR"),
    ("mid", "Post", "Instagram", "معرفی برندهای قابل ارائه در یک شعبه منتخب", "مشاهده موجودی", "Reach, Profile Visit"),
    ("long", "Reel", "Instagram", "معرفی یک خودروی جذاب داخل بخشنامه و ۳ مزیت واقعی", "دریافت شرایط", "Video View, Leads"),
    ("long", "SMS", "CRM", "پیام کوتاه برای مخاطبان مرتبط با برند یا خودرو", "ثبت تماس / درخواست", "Response, Leads"),
    ("short", "Quiz", "Story", "کوئیز خودرو: آپشن، مدل یا برند را حدس بزن", "شرکت در بازی", "Replies"),
    ("short", "Reveal", "Story + Reel", "اعلام نتیجه Quiz و معرفی پیشنهاد ویژه مرتبط", "ارسال شماره", "Leads"),
    ("long", "Carousel", "Instagram", "مقایسه دو انتخاب در یک رنج کاربری", "مشاوره انتخاب", "Saves, DM"),
    ("long", "Retargeting", "Paid Media", "آگهی مخصوص Engagerهای هفته اول و دوم", "ثبت Lead", "CPL"),
    ("mid", "Reel", "Instagram", "یک روز با مشاور فروش در شعبه؛ پاسخ کوتاه به سؤالات", "رزرو مشاوره", "Watch Time, Leads"),
    ("short", "Tease", "Story + Telegram", "تیزر پیشنهاد محدود هفته سوم: اقساط، تخفیف یا ظرفیت", "فعال کردن Reminder", "Reminder Taps"),
    ("short", "Launch", "Post + Story", "شروع کمپین Burst: شرایط ویژه با زمان محدود", "دریافت شرایط", "Leads, CTR"),
    ("short", "SMS", "CRM", "اطلاع‌رسانی مستقیم کمپین کوتاه‌مدت به سگمنت هدف", "تماس", "Lead, Call"),
    ("short", "Reel", "Instagram", "توضیح ساده شرایط اقساط یا مزیت پیشنهاد در ۳۰ ثانیه", "ارسال شماره", "Leads"),
    ("short", "Story", "Instagram", "پاسخ به اعتراض‌ها و FAQ کمپین", "ثبت سؤال / درخواست", "Replies, Leads"),
    ("short", "UGC/Social Proof", "Instagram", "بازخورد یا تجربه مشتری و تحویل خودرو", "مشاوره", "Trust, Leads"),
    ("short", "Last Call", "Story + SMS", "۲۴ ساعت پایانی پیشنهاد کوتاه‌مدت", "اقدام فوری", "Conversion"),
    ("long", "Post", "Instagram + Telegram", "برگشت به Always-on: بخشنامه و موجودی هفته آخر", "دریافت شرایط", "Leads"),
    ("mid", "Reel", "Instagram", "معرفی شعبه دوم یا یک سرویس ویژه شعبه", "مراجعه", "Reach, Visit"),
    ("long", "Story", "Instagram", "انتخاب سریع: کدام مدل را کامل بررسی کنیم؟", "Vote", "Engagement"),
    ("long", "Reel", "Instagram", "بررسی مدل منتخب مخاطبان", "دریافت مشخصات", "View, Leads"),
    ("long", "Carousel", "Instagram", "FAQ نهایی ماه: قیمت، تحویل، مدارک، ثبت درخواست", "Save / DM", "Saves, Leads"),
    ("long", "Retargeting", "Paid Media", "Closing Retargeting برای لیدهای ناقص و بازدیدکنندگان", "تکمیل فرم", "CVR, CPL"),
    ("mid", "Story", "Instagram", "جمع‌بندی شعب و راه‌های تماس و مراجعه", "لوکیشن / تماس", "Clicks, Calls"),
    ("long", "Report + Tease", "Internal + Story", "جمع‌بندی آبان و Tease آذر برای مخاطب؛ گزارش KPI برای تیم", "عضویت / پیگیری", "Lead Quality, MoM"),
]

HEADER = {
    "title": "تقویم محتوا — آبان ۱۴۰۵",
    "goal": "ساخت Interest، افزایش Engagement و تولید Lead قابل پیگیری در CRM",
    "logic": [
        "به‌جای تمرکز صرف روی تعداد پست، حرکت مخاطب از Awareness به Interest و سپس Lead Generation طراحی شده است.",
        "بخشنامه‌ها و شرایط فروش ماژولارند تا با بخشنامه واقعی همان هفته جایگزین شوند.",
        "کمپین کوتاه‌مدت به‌صورت Burstهای ۳ تا ۷ روزه روی فروش، اقساط، تخفیف یا Gamification اجرا می‌شود.",
    ],
    "weeks": [
        {
            "from": "2026-10-23",
            "to": "2026-10-29",
            "title": "هفته ۱ — Warm-up",
            "body": "شروع با معرفی شعبه و محتوای اعتمادساز، سپس باز کردن موضوع بخشنامه و ایجاد Interest. پایان هفته: اولین CTA برای دریافت شرایط.",
        },
        {
            "from": "2026-10-30",
            "to": "2026-11-05",
            "title": "هفته ۲ — Interest و Lead",
            "body": "تمرکز روی خودروهای موجود در بخشنامه، FAQ، مقایسه و Retargeting. یک Activation کوتاه با Poll یا Quiz.",
        },
        {
            "from": "2026-11-06",
            "to": "2026-11-12",
            "title": "هفته ۳ — Burst فروش",
            "body": "کمپین ۵ تا ۷ روزه روی اقساط، تخفیف یا مزیت محدود. هم‌زمان Story، SMS، Retargeting و CRM.",
        },
        {
            "from": "2026-11-13",
            "to": "2026-11-21",
            "title": "هفته ۴ — Conversion و بستن",
            "body": "Social Proof، آخرین فرصت، Reminder بخشنامه، جمع‌آوری لیدهای مردد و آماده‌سازی مخاطب برای آذر.",
        },
    ],
    "mix": [
        {"label": "بلندمدت", "share": 40, "note": "بخشنامه و Lead Generation"},
        {"label": "میان‌مدت", "share": 30, "note": "شعب و اعتمادسازی"},
        {"label": "کوتاه‌مدت", "share": 20, "note": "Sales Activation / Gamification"},
        {"label": "واکنشی", "share": 10, "note": "بخشنامه ناگهانی، تغییر قیمت، ظرفیت یا خبر فوری"},
    ],
    "kpis": [
        {"stage": "Awareness", "kpi": "Reach، Video Views، Frequency", "use": "شعب و معرفی برند یا خودرو"},
        {"stage": "Interest", "kpi": "Profile Visit، Saves، Story Completion، Landing View", "use": "بخشنامه و محتوای بررسی"},
        {"stage": "Lead", "kpi": "Lead، CPL، Form Completion، Call/DM", "use": "شاخص اصلی کمپین بلندمدت و Burst"},
        {"stage": "Quality", "kpi": "Qualified Lead Rate، Contact Rate، Appointment Rate", "use": "کیفیت لید در CRM"},
        {"stage": "Conversion", "kpi": "Sale/Registration Rate، Cost per Qualified Lead", "use": "مقایسه کانال‌ها"},
    ],
    "rules": [
        "هر محتوای Lead Generation باید UTM، منبع لید و نام کمپین داشته باشد.",
        "قبل از انتشار هر بخشنامه، نسخه نهایی شرایط فروش با تیم فروش و مدیریت چک شود.",
        "برای هر کمپین کوتاه‌مدت حداقل سه فاز Tease، Launch و Last Call اجرا شود.",
        "استوری‌ها فقط مکمل پست نباشند؛ برای Poll، FAQ، Countdown و گرفتن لید طراحی شوند.",
        "لیدهای کمپین حداکثر همان روز وارد پیگیری CRM شوند و نتیجه تماس ثبت شود.",
        "هفته‌ای یک بار CPL، کیفیت لید و عملکرد Creative بررسی شود.",
        "۱۰٪ ظرفیت محتوا خالی بماند تا خبر یا بخشنامه ناگهانی بدون به‌هم ریختن تقویم پوشش داده شود.",
    ],
}


def header_payload() -> str:
    return json.dumps(HEADER, ensure_ascii=False)


def entry_rows() -> list[dict]:
    rows = []
    for index, (tier, fmt, channel, topic, cta, kpi) in enumerate(ROWS):
        rows.append(
            {
                "on_date": ABAN_START + timedelta(days=index),
                "tier": tier,
                "format": fmt,
                "channel": channel,
                "topic": topic,
                "cta": cta,
                "kpi": kpi,
                "status": "todo",
            }
        )
    return rows
