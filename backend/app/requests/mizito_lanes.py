"""دسته‌بندی مارکتینگ بر اساس پروژه‌های میزیتو (فقط خواندن از API میزیتو)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MizitoMarketingLane:
    slug: str
    title: str
    team_code: str
    """کد تیم پیش‌فرض CM برای پروژه‌های این دسته."""

    def matches_mizito_title(self, title: str) -> bool:
        from app.perf.services.mizito import normalize

        text = normalize(title)
        want = normalize(self.title)
        return want in text or text in want


MARKETING_MIZITO_LANES: tuple[MizitoMarketingLane, ...] = (
    MizitoMarketingLane("finance_marketing", "مالی و مارکتینگ", "FIN_T"),
    MizitoMarketingLane("content", "تولید محتوا", "MKT_DESIGN"),
    MizitoMarketingLane("performance", "پرفورمنس مارکتینگ", "MKT_PERF"),
    MizitoMarketingLane("campaigns", "کمپین ها", "MKT_PERF"),
    MizitoMarketingLane("automation", "اتومیشن مارکتینگ", "MKT_T"),
    MizitoMarketingLane("sales_circulars", "بخشنامه های فروش", "SALES_T"),
)

LANE_BY_SLUG = {lane.slug: lane for lane in MARKETING_MIZITO_LANES}


def lane_for_mizito_project_title(title: str) -> MizitoMarketingLane | None:
    for lane in MARKETING_MIZITO_LANES:
        if lane.matches_mizito_title(title):
            return lane
    return None


def lane_slug_for_mizito_project_title(title: str) -> str | None:
    lane = lane_for_mizito_project_title(title)
    return lane.slug if lane else None


def wanted_marketing_mizito_project(title: str) -> bool:
    return lane_for_mizito_project_title(title) is not None


def mizito_lane_labels() -> list[dict[str, str]]:
    return [{"slug": lane.slug, "title": lane.title, "team_code": lane.team_code} for lane in MARKETING_MIZITO_LANES]


_ARCHIVE_BOARD_RE = re.compile(r"پرداخت شده|صورت تنخواه|بایگانی|انجام شد|تکمیل شده", re.IGNORECASE)


def is_archive_board_title(title: str) -> bool:
    return bool(_ARCHIVE_BOARD_RE.search((title or "").strip()))
