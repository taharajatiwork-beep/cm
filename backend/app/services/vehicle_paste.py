"""خواندن پیام موجودی مدیر فروش و تبدیل آن به ردیف خودرو.

عدد قیمت در پیام به میلیون تومان است. مبلغ ذخیره‌شده تومان است (× ۱٬۰۰۰٬۰۰۰).
"""

from __future__ import annotations

import re

MILLION = 1_000_000

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_COLORS = (
    "سورمه ای",
    "سورمه‌ای",
    "نوک مدادی",
    "نقره ای",
    "نقره‌ای",
    "سفید",
    "مشکی",
    "سبز",
    "قرمز",
    "آبی",
    "خاکستری",
    "طوسی",
    "بژ",
)

_SKIP = ("شرایط", "لیزینگ", "موجودی خودرو", "سایر شعب", "بروزرسانی", "خودروهایی که", "📌", "🔷", "🟣")


def to_latin_digits(text: str) -> str:
    return text.translate(_DIGIT_MAP)


def million_to_toman(value: int) -> int:
    return value * MILLION


def parse_stock_message(text: str) -> list[dict]:
    """هر سطر خودرو: برند، مدل، رنگ، سال، کارکرد، شعبه، یادداشت تحویل، قیمت (تومان)."""
    raw_lines = [to_latin_digits(line).strip() for line in text.splitlines()]
    lines = [line for line in raw_lines if line]
    brand = ""
    rows: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _is_brand_header(line):
            brand = line.rstrip(":").strip()
            i += 1
            continue
        if _should_skip(line):
            i += 1
            continue
        merged = line
        if _price_of(line) is None and i + 1 < len(lines) and _price_of(lines[i + 1]) is not None:
            merged = f"{line} {lines[i + 1]}"
            i += 1
        price = _price_of(merged)
        model = _model_of(merged)
        if price is None or not model:
            i += 1
            continue
        rows.append(
            {
                "brand": brand or _brand_guess(merged),
                "model": model,
                "color": _color_of(merged),
                "year": _year_of(merged),
                "mileage": _mileage_of(merged),
                "branch_name": _branch_of(merged),
                "delivery_note": _delivery_of(merged),
                "sale_price": million_to_toman(price),
                "price_million": price,
                "raw": merged,
            }
        )
        i += 1
    return rows


def _is_brand_header(line: str) -> bool:
    if not line.endswith(":"):
        return False
    return _price_of(line) is None and len(line) < 40


def _should_skip(line: str) -> bool:
    if len(line) < 2:
        return True
    return any(token in line for token in _SKIP)


def _price_of(line: str) -> int | None:
    labeled = re.search(r"قیمت\s*([0-9]{3,6})", line)
    if labeled:
        return int(labeled.group(1))
    numbers = [int(n) for n in re.findall(r"(?<![0-9])([0-9]{3,6})(?![0-9])", line)]
    # سال و کارکرد را کنار بگذار: 1402، 2025، 5000 کیلومتر جداگانه گرفته می‌شود
    candidates = []
    for n in numbers:
        if 1300 <= n <= 1500 or 1900 <= n <= 2100:
            continue
        if re.search(rf"کارکرد\s*{n}|{n}\s*کیلومتر|{n}\s*هزار", line):
            continue
        candidates.append(n)
    if not candidates:
        return None
    return candidates[-1]


def _model_of(line: str) -> str:
    text = line
    text = re.sub(r"قیمت\s*[0-9]+", " ", text)
    text = re.sub(r"موجود در شعبه\s+\S+", " ", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"کارکرد\s*[0-9]+\s*(کیلومتر|هزار)?", " ", text)
    text = re.sub(r"[0-9]+\s*هزار", " ", text)
    text = re.sub(r"مدل\s*[0-9]+", " ", text)
    text = re.sub(r"\b(140[0-9]|403|404|405|202[0-9])\b", " ", text)
    for color in _COLORS:
        text = text.replace(color, " ")
    for noise in (
        "تحویل یک ماه کاری",
        "تعهد پلاک",
        "پلاک 10 روز",
        "پلاک ۱۰ روز",
        "تحویل فوری",
        "کارکرده",
        "بدون چرم و تاشو",
        "بادی فنس شده",
        "دو دف",
    ):
        text = text.replace(to_latin_digits(noise), " ")
    text = re.sub(r"[0-9]{3,}", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -–،")
    return text


def _color_of(line: str) -> str | None:
    if "سفید و مشکی" in line:
        return "سفید و مشکی"
    for color in _COLORS:
        if color in line or to_latin_digits(color) in line:
            return color
    return None


def _year_of(line: str) -> int | None:
    miladi = re.search(r"\b(20[0-9]{2})\b", line)
    if miladi:
        return int(miladi.group(1))
    shamsi = re.search(r"\b(14[0-9]{2})\b", line)
    if shamsi:
        return int(shamsi.group(1))
    short = re.search(r"(?:مدل\s*)?(40[0-9])\b", line)
    if short and not re.search(rf"قیمت\s*{short.group(1)}", line):
        return 1000 + int(short.group(1))
    return None


def _mileage_of(line: str) -> int | None:
    thousand = re.search(r"کارکرد\s*([0-9]+)\s*هزار", line)
    if thousand:
        return int(thousand.group(1)) * 1000
    km = re.search(r"کارکرد\s*([0-9]+)", line)
    if km:
        return int(km.group(1))
    return None


def _branch_of(line: str) -> str | None:
    match = re.search(r"شعبه\s+([^\s(]+)", line)
    return match.group(1) if match else None


def _delivery_of(line: str) -> str | None:
    notes = []
    if "تحویل یک ماه" in line:
        notes.append("تحویل یک ماه کاری")
    if "تعهد پلاک" in line:
        notes.append("تعهد پلاک")
    if "پلاک 10 روز" in line or "10 روز" in line:
        notes.append("پلاک ۱۰ روز، تحویل فوری")
    if "تحویل فوری" in line and "پلاک" not in "".join(notes):
        notes.append("تحویل فوری")
    return "، ".join(notes) or None


def _norm(value: str | None) -> str:
    return re.sub(r"\s+", "", (value or "").replace("‌", "")).lower()


async def build_preview(db, organization_id, text: str) -> dict:
    from sqlalchemy import select

    from app.models.inventory import Vehicle

    parsed = parse_stock_message(text)
    vehicles = list(
        (
            await db.scalars(select(Vehicle).where(Vehicle.organization_id == organization_id))
        ).all()
    )
    used: set = set()
    rows = []
    for item in parsed:
        match = _match(vehicles, item, used)
        if match is None:
            action = "new"
        elif match.sale_price != item["sale_price"]:
            action = "price_changed"
        else:
            action = "unchanged"
        if match:
            used.add(match.id)
        rows.append({**item, "action": action, "vehicle_id": str(match.id) if match else None, "apply": action != "unchanged"})
    missing = []
    for vehicle in vehicles:
        status = vehicle.status.value if hasattr(vehicle.status, "value") else vehicle.status
        if vehicle.id in used or status != "IN_STOCK":
            continue
        if status == "IN_STOCK":
            missing.append(
                {
                    "action": "missing",
                    "vehicle_id": str(vehicle.id),
                    "brand": vehicle.brand,
                    "model": vehicle.model,
                    "sale_price": vehicle.sale_price,
                    "apply": False,
                    "raw": f"{vehicle.brand} {vehicle.model}",
                }
            )
    return {"rows": rows, "missing": missing}


def _match(vehicles, item, used):
    want_model = _norm(item["model"])
    want_color = _norm(item.get("color"))
    best = None
    for vehicle in vehicles:
        if vehicle.id in used:
            continue
        model = _norm(vehicle.model)
        if not model or (want_model not in model and model not in want_model):
            continue
        if want_color and _norm(vehicle.color) and want_color not in _norm(vehicle.color) and _norm(vehicle.color) not in want_color:
            continue
        if item.get("year") and vehicle.year and item["year"] != vehicle.year:
            continue
        best = vehicle
        break
    return best


async def apply_preview(db, *, organization_id, actor_id, actor_permissions, rows: list[dict]) -> dict:
    from datetime import UTC, datetime
    from uuid import UUID, uuid4

    from sqlalchemy import select

    from app.core.permissions import PermissionCode
    from app.models import Branch
    from app.models.enums import VehicleStatus
    from app.models.inventory import Vehicle
    from app.services.inventory import InventoryService
    from app.services.pricing import PricingService

    inv = InventoryService(db)
    pricing = PricingService(db)
    can_price = PermissionCode.PRICE_WRITE in actor_permissions or PermissionCode.ORG_ADMIN in actor_permissions
    now = datetime.now(UTC)
    created = updated = proposed = sold = 0
    branches = list((await db.scalars(select(Branch).where(Branch.organization_id == organization_id))).all())

    def branch_id(name: str | None):
        if not name:
            return None
        for branch in branches:
            if name in branch.name or branch.name in name:
                return branch.id
        return None

    for row in rows:
        if not row.get("apply"):
            continue
        action = row.get("action")
        if action == "new":
            vehicle = await inv.create_vehicle(
                organization_id=organization_id,
                vin=f"PASTE-{uuid4().hex[:10].upper()}",
                brand=row.get("brand") or "نامشخص",
                model=row.get("model") or "نامشخص",
                year=int(row.get("year") or 1400),
                actor_id=actor_id,
                actor_permissions=actor_permissions,
                color=row.get("color"),
                mileage=row.get("mileage"),
                sale_price=row.get("sale_price") if can_price else None,
                delivery_note=row.get("delivery_note"),
                branch_id=branch_id(row.get("branch_name")),
                status=VehicleStatus.IN_STOCK,
            )
            created += 1
            if not can_price and row.get("sale_price"):
                await pricing.queue_price_proposal(
                    organization_id=organization_id,
                    vehicle_id=vehicle.id,
                    amount=int(row["sale_price"]),
                    requester_id=actor_id,
                )
                proposed += 1
        elif action in ("price_changed", "unchanged") and row.get("vehicle_id"):
            vehicle = await db.get(Vehicle, UUID(str(row["vehicle_id"])))
            if not vehicle:
                continue
            vehicle.stock_updated_at = now
            vehicle.stock_updated_by = actor_id
            if row.get("delivery_note"):
                vehicle.delivery_note = row["delivery_note"]
            if action == "price_changed":
                if can_price:
                    await pricing.set_price(
                        organization_id=organization_id,
                        vehicle_id=vehicle.id,
                        amount=int(row["sale_price"]),
                        actor_id=actor_id,
                        actor_permissions=actor_permissions,
                        note="به‌روزرسانی موجودی",
                    )
                    updated += 1
                else:
                    await pricing.queue_price_proposal(
                        organization_id=organization_id,
                        vehicle_id=vehicle.id,
                        amount=int(row["sale_price"]),
                        requester_id=actor_id,
                    )
                    proposed += 1
        elif action == "missing" and row.get("vehicle_id"):
            vehicle = await db.get(Vehicle, UUID(str(row["vehicle_id"])))
            if vehicle:
                vehicle.status = VehicleStatus.SOLD
                vehicle.stock_updated_at = now
                vehicle.stock_updated_by = actor_id
                sold += 1
    await db.flush()
    return {"created": created, "updated": updated, "proposed": proposed, "sold": sold}


def _brand_guess(line: str) -> str:
    known = ("آئودی", "تیگو", "آریزو", "بیجینگ", "کرمان موتور", "لوکانو")
    for name in known:
        if name in line:
            return name
    return ""
