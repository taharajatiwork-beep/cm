"""پرداخت‌های پروژهٔ مالی میزیتو در برابر ردیف‌های Cost Tracking پنل.

فقط از عکس ذخیره‌شدهٔ میزیتو و دیتابیس پنل خوانده می‌شود؛ به میزیتو وصل نمی‌شود و هیچ ردیف هزینه‌ای نمی‌سازد.
تطبیق فقط با کد کمپین است (عنوان کارت، یا اگر عنوان کد نداشت، کدِ داخل یادداشت) و همیشه «پیشنهادی» است.
مبلغ و تاریخ کارت‌ها برای تطبیق استفاده نمی‌شود: مبلغ در عنوان کارت‌ها تقریباً هیچ‌وقت نیست.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.perf.models import PmCost
from app.perf.services.mizito import board_status, code_key, normalize, saved_mizito

FINANCE_STATUSES = ("waiting_approval", "waiting_payment", "paid", "not_in_cost_tracking")
_FINANCE_PROJECT = "مالی"
_LIST_LIMIT = 100


def is_finance_project(title: Any) -> bool:
    return _FINANCE_PROJECT in normalize(title)


def _status(card: dict) -> str:
    return str(card.get("status") or board_status(card.get("board")))


def _newest_first(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: str(row.get("modified_at") or ""), reverse=True)


def finance_view(cards: list[dict], costs: list[tuple]) -> dict:
    """costs: (کد، شمارهٔ هزینه) یا (کد، شماره، مبلغ، نوع، شرح) از ردیف‌های Cost Tracking پنل."""
    numbers: dict[str, list[int]] = {}
    panel_rows: list[dict] = []
    for item in costs:
        code = item[0] if len(item) else ""
        number = int(item[1] or 0) if len(item) > 1 else 0
        key = code_key(code)
        if not key:
            continue
        numbers.setdefault(key, []).append(number)
        panel_rows.append(
            {
                "campaign_code": key,
                "cost_number": number,
                "amount_toman": int(item[2] or 0) if len(item) > 2 else None,
                "kind": str(item[3] or "") if len(item) > 3 else "",
                "description": str(item[4] or "") if len(item) > 4 else "",
            }
        )
    counts = {status: {"total": 0, "open": 0} for status in FINANCE_STATUSES}
    to_register: list[dict] = []
    paid_without_cost: list[dict] = []
    paid_suggested = 0
    for card in cards:
        if not isinstance(card, dict) or not is_finance_project(card.get("project")):
            continue
        status = _status(card)
        if status not in counts:
            continue
        completed = bool(card.get("completed"))
        counts[status]["total"] += 1
        if not completed:
            counts[status]["open"] += 1
        key = code_key(card.get("code"))
        found = sorted(numbers.get(key, [])) if key else []
        item = {
            "id": str(card.get("id") or ""),
            "title": str(card.get("title") or ""),
            "board": str(card.get("board") or ""),
            "status": status,
            "code": key,
            "code_source": str(card.get("code_source") or ("title" if key else "")),
            "completed": completed,
            "modified_at": card.get("modified_at"),
            "match": "suggested" if found else ("no_cost_row" if key else "no_code"),
            "suggested_costs": found[:5],
        }
        if status == "not_in_cost_tracking" and not completed:
            to_register.append(item)
        elif status == "paid":
            if found:
                paid_suggested += 1
            else:
                paid_without_cost.append(item)
    paid_without_cost = _newest_first(paid_without_cost)
    paid_without_cost.sort(key=lambda row: row["match"] != "no_cost_row")
    seen_codes: set[str] = set()
    tracked_codes: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            continue
        key = code_key(card.get("code"))
        if not key:
            continue
        if is_finance_project(card.get("project")):
            seen_codes.add(key)
        else:
            tracked_codes.add(key)
    panel_without_card = [
        row for row in panel_rows if row["campaign_code"] in tracked_codes and row["campaign_code"] not in seen_codes
    ]
    panel_without_card.sort(key=lambda row: row["cost_number"], reverse=True)
    return {
        "match_basis": "code",
        "counts": counts,
        "to_register": _newest_first(to_register)[:_LIST_LIMIT],
        "to_register_count": len(to_register),
        "paid_without_cost": paid_without_cost[:_LIST_LIMIT],
        "paid_without_cost_count": len(paid_without_cost),
        "paid_suggested_count": paid_suggested,
        "panel_without_card": panel_without_card[:_LIST_LIMIT],
        "panel_without_card_count": len(panel_without_card),
    }


async def mizito_finance(db: AsyncSession, organization_id: UUID) -> dict:
    data = await saved_mizito(db, organization_id)
    rows = (
        await db.execute(
            select(PmCost.campaign_code, PmCost.cost_number, PmCost.amount_toman, PmCost.kind, PmCost.description).where(
                PmCost.organization_id == organization_id
            )
        )
    ).all()
    view = finance_view(
        data.get("cards") or [],
        [(code or "", number or 0, amount or 0, kind or "", description or "") for code, number, amount, kind, description in rows],
    )
    return {"connected": bool(data.get("connected")), "read_at": data.get("read_at"), **view}
