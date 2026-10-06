"""درخواست تبلیغ خودرو، پیج و پیشنهاد بودجه."""

from __future__ import annotations

_BRANDS = ("فونیکس", "کرمان موتور", "کرمان", "ام وی ام", "MVM", "لاماری", "فولکس", "تیگو", "آریزو", "جک")


def parse_car_request(text: str) -> dict:
    raw = (text or "").strip()
    found = [name for name in _BRANDS if name in raw]
    first = raw.splitlines()[0][:180] if raw else ""
    return {
        "brand": found[0] if found else "",
        "summary": first,
    }


def suggest_pages(pages: list[dict], budget: int) -> dict:
    """pages: name, price_toman, cpl, cpv."""
    ranked = sorted(
        pages,
        key=lambda row: (
            row.get("cpl") is None,
            row.get("cpl") if row.get("cpl") is not None else 10**18,
            row.get("cpv") if row.get("cpv") is not None else 10**18,
        ),
    )
    picked = []
    left = budget
    for row in ranked:
        price = int(row.get("price_toman") or 0)
        if price <= 0 or price > left:
            continue
        picked.append(row)
        left -= price
    return {"budget_toman": budget, "remaining_toman": left, "pages": picked, "ranked": ranked}
