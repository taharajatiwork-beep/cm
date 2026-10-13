"""تبدیل تاریخ شمسی برای بازهٔ پیش‌نویس ماه."""

from __future__ import annotations

from datetime import date


def jalali_month_length(year: int, month: int) -> int:
    if month < 1 or month > 12:
        raise ValueError("ماه نامعتبر است")
    if month <= 6:
        return 31
    if month <= 11:
        return 30
    return 30 if year % 33 in {1, 5, 9, 13, 17, 22, 26, 30} else 29


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> date:
    j_days = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]
    jy -= 979
    jm -= 1
    jd -= 1
    j_day_no = 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4
    for i in range(jm):
        j_day_no += j_days[i]
    j_day_no += jd
    g_day_no = j_day_no + 79
    gy = 1600 + 400 * (g_day_no // 146097)
    g_day_no %= 146097
    leap = True
    if g_day_no >= 36525:
        g_day_no -= 1
        gy += 100 * (g_day_no // 36524)
        g_day_no %= 36524
        if g_day_no >= 365:
            g_day_no += 1
        else:
            leap = False
    gy += 4 * (g_day_no // 1461)
    g_day_no %= 1461
    if g_day_no >= 366:
        leap = False
        g_day_no -= 1
        gy += g_day_no // 365
        g_day_no %= 365
    g_days = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 11 and g_day_no >= g_days[gm]:
        g_day_no -= g_days[gm]
        gm += 1
    return date(gy, gm + 1, g_day_no + 1)
