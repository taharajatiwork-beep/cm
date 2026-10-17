"""Global calendar occasions for Jalali 1405 (Gregorian 2026-03-21 .. 2027-03-20)."""

from __future__ import annotations

from datetime import date

from app.core.calendar import IRAN_HOLIDAYS

# Marketing / cultural anchors (Gregorian); extend each year.
MARKETING_OCCASIONS: list[tuple[date, str, str, bool]] = [
    (date(2026, 12, 21), "شب یلدا", "marketing", False),
    (date(2026, 3, 8), "روز جهانی زن", "marketing", False),
    (date(2026, 11, 28), "بلک فرایدی", "marketing", False),
    (date(2026, 3, 21), "نوروز — شروع فروش", "marketing", False),
]


def global_occasions_1405() -> list[dict]:
    rows: list[dict] = []
    for day in sorted(IRAN_HOLIDAYS):
        rows.append(
            {
                "on_date": day.isoformat(),
                "title": "تعطیل رسمی",
                "kind": "official",
                "is_off": True,
            }
        )
    for on_date, title, kind, is_off in MARKETING_OCCASIONS:
        rows.append(
            {
                "on_date": on_date.isoformat(),
                "title": title,
                "kind": kind,
                "is_off": is_off,
            }
        )
    return rows
