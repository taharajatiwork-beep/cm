"""Iran business calendar: Friday weekend plus a fixed official-holiday set.

Holiday dates are Gregorian so SLA math does not depend on a locale library.
Extend IRAN_HOLIDAYS each year (solar dates below are derived from the
Solar Hijri year 1405 = 2026-03-21 .. 2027-03-20).

قمری: تاریخ‌های هجری قمری (فطر، قربان، غدیر، محرم، صفر، مبعث و…) هر سال
جا می‌خواهند و باید دستی به همین مجموعه اضافه شوند — عمداً به کتابخانهٔ
خارجی گره نخورده‌اند تا محاسبهٔ SLA آفلاین و قطعی بماند.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

# Official Iranian holidays (Gregorian) used for SLA — Solar Hijri year 1405.
IRAN_HOLIDAYS = {
    # نوروز: ۲۹ اسفند ۱۴۰۴ و ۱ تا ۴ فروردین ۱۴۰۵
    date(2026, 3, 20),
    date(2026, 3, 21),
    date(2026, 3, 22),
    date(2026, 3, 23),
    date(2026, 3, 24),
    # ۱۲ و ۱۳ فروردین (روز جمهوری اسلامی و طبیعت)
    date(2026, 4, 1),
    date(2026, 4, 2),
    # ۱۴ خرداد (رحلت امام خمینی) و ۱۵ خرداد (قیام ۱۵ خرداد)
    date(2026, 6, 4),
    date(2026, 6, 5),
    # ۲۲ بهمن (پیروزی انقلاب اسلامی، ۱۴۰۵/۱۱/۲۲)
    date(2027, 2, 11),
}


def is_business_day(day: date) -> bool:
    if day.weekday() == 4:  # Friday
        return False
    return day not in IRAN_HOLIDAYS


def is_business_moment(moment: datetime) -> bool:
    """لحظه داخل شنبه تا پنجشنبه، ساعت کاری ۸ تا ۱۷ است؟"""
    return is_business_day(moment.date()) and 8 <= moment.hour < 17


def to_business_time(moment: datetime) -> datetime:
    """اگر لحظه در ساعات/روزهای کاری نباشد، به اولین لحظهٔ کاری بعدی می‌بردش.

    برای همان روزِ کاری قبل از ساعت ۸ → همان روز ساعت ۸:۰۰.
    """
    if is_business_moment(moment):
        return moment
    if is_business_day(moment.date()) and moment.hour < 8:
        return moment.replace(hour=8, minute=0, second=0, microsecond=0)
    return _next_open(moment)


def add_business_minutes(start: datetime, minutes: int) -> datetime:
    remaining = minutes
    cursor = start
    while remaining > 0:
        if not is_business_day(cursor.date()) or cursor.hour < 8 or cursor.hour >= 17:
            cursor = _next_open(cursor)
            continue
        end_of_day = cursor.replace(hour=17, minute=0, second=0, microsecond=0)
        available = int((end_of_day - cursor).total_seconds() // 60)
        step = min(remaining, max(available, 0))
        if step <= 0:
            cursor = _next_open(cursor)
            continue
        cursor += timedelta(minutes=step)
        remaining -= step
    return cursor


def _next_open(cursor: datetime) -> datetime:
    # صبحِ همان روزِ کاری (قبل از ساعت ۸) زودتر از روز بعد است.
    if is_business_day(cursor.date()) and cursor.hour < 8:
        return cursor.replace(hour=8, minute=0, second=0, microsecond=0)
    nxt = (cursor + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    while not is_business_day(nxt.date()):
        nxt += timedelta(days=1)
    return nxt
