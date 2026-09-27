"""Parse CSV/Excel rows into vehicle create payloads."""

from __future__ import annotations

import csv
import io
from typing import Any

from openpyxl import Workbook, load_workbook

from app.models.enums import VehicleStatus

# Canonical column → accepted header aliases (EN + FA)
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "vin": ("vin", "شاسی", "شماره شاسی", "chassis"),
    "brand": ("brand", "برند", "make", "سازنده"),
    "model": ("model", "مدل"),
    "year": ("year", "سال", "model_year", "سال ساخت"),
    "stock_number": ("stock_number", "stock", "stock #", "شماره انبار", "کد انبار"),
    "color": ("color", "رنگ"),
    "trim": ("trim", "تریم", "نسخه", "تیپ"),
    "mileage": ("mileage", "کیلومتر", "km", "کارکرد"),
    "purchase_price": ("purchase_price", "قیمت خرید", "خرید"),
    "sale_price": ("sale_price", "قیمت فروش", "فروش", "قیمت"),
    "currency": ("currency", "ارز"),
    "description": ("description", "توضیحات", "شرح", "desc"),
    "notes": ("notes", "یادداشت", "نکات"),
    "body_type": ("body_type", "بدنه", "نوع بدنه"),
    "transmission": ("transmission", "گیربکس", "جعبه دنده"),
    "fuel_type": ("fuel_type", "سوخت", "نوع سوخت"),
    "engine": ("engine", "موتور", "حجم موتور"),
    "plate_number": ("plate_number", "پلاک", "شماره پلاک"),
    "doors": ("doors", "در", "تعداد در"),
    "seats": ("seats", "صندلی", "ظرفیت"),
    "options": ("options", "آپشن", "امکانات"),
    "exterior_condition": ("exterior_condition", "وضعیت بیرونی", "بدنه وضعیت"),
    "interior_condition": ("interior_condition", "وضعیت داخلی", "کابین"),
    "status": ("status", "وضعیت"),
}

TEMPLATE_COLUMNS = [
    "vin",
    "brand",
    "model",
    "year",
    "stock_number",
    "color",
    "trim",
    "mileage",
    "purchase_price",
    "sale_price",
    "currency",
    "description",
    "notes",
    "body_type",
    "transmission",
    "fuel_type",
    "engine",
    "plate_number",
    "doors",
    "seats",
    "options",
    "exterior_condition",
    "interior_condition",
    "status",
]

REQUIRED = ("vin", "brand", "model", "year")


def _norm_header(value: Any) -> str:
    return str(value or "").strip().lower().replace("\ufeff", "")


def _alias_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for a in aliases:
            out[_norm_header(a)] = canonical
    return out


def build_import_template_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "vehicles"
    ws.append(TEMPLATE_COLUMNS)
    ws.append(
        [
            "JTDBEXAMPLE000001",
            "Toyota",
            "Camry",
            2020,
            "1001",
            "White",
            "LE",
            45000,
            2000000000,
            2500000000,
            "IRR",
            "تمیز، سرویس‌شده، مناسب خانواده",
            "کلید یدک دارد",
            "sedan",
            "automatic",
            "petrol",
            "2.5L",
            "12ب34567",
            4,
            5,
            "سانروف، دوربین عقب",
            "خوب",
            "عالی",
            "IN_STOCK",
        ]
    )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_import_template_csv() -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(TEMPLATE_COLUMNS)
    writer.writerow(
        [
            "JTDBEXAMPLE000001",
            "Toyota",
            "Camry",
            2020,
            "1001",
            "White",
            "LE",
            45000,
            2000000000,
            2500000000,
            "IRR",
            "Clean family sedan, serviced",
            "Spare key included",
            "sedan",
            "automatic",
            "petrol",
            "2.5L",
            "12B34567",
            4,
            5,
            "sunroof, rear camera",
            "good",
            "excellent",
            "IN_STOCK",
        ]
    )
    return buf.getvalue().encode("utf-8-sig")


def _parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().replace(",", "").replace("٬", "")
    if not text:
        return None
    return int(float(text))


def _parse_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_status(value: Any) -> VehicleStatus:
    text = _parse_str(value)
    if not text:
        return VehicleStatus.IN_STOCK
    key = text.upper().replace(" ", "_").replace("-", "_")
    fa_map = {
        "موجود": "IN_STOCK",
        "رزرو": "RESERVED",
        "فروخته": "SOLD",
        "فروخته_شده": "SOLD",
        "در_انتقال": "IN_TRANSFER",
        "انتقال": "IN_TRANSFER",
    }
    key = fa_map.get(text, fa_map.get(key, key))
    try:
        return VehicleStatus(key)
    except ValueError:
        return VehicleStatus.IN_STOCK


def _row_to_payload(raw: dict[str, Any], *, import_source: str) -> dict[str, Any]:
    missing = [f for f in REQUIRED if not raw.get(f)]
    if missing:
        raise ValueError(f"missing required: {', '.join(missing)}")

    year = _parse_int(raw.get("year"))
    if year is None:
        raise ValueError("year must be a number")

    vin = str(raw["vin"]).strip().upper()
    if len(vin) < 5:
        raise ValueError("vin too short")

    return {
        "vin": vin,
        "brand": str(raw["brand"]).strip(),
        "model": str(raw["model"]).strip(),
        "year": year,
        "stock_number": _parse_str(raw.get("stock_number")),
        "color": _parse_str(raw.get("color")),
        "trim": _parse_str(raw.get("trim")),
        "mileage": _parse_int(raw.get("mileage")),
        "purchase_price": _parse_int(raw.get("purchase_price")),
        "sale_price": _parse_int(raw.get("sale_price")),
        "currency": _parse_str(raw.get("currency")) or "IRR",
        "description": _parse_str(raw.get("description")),
        "notes": _parse_str(raw.get("notes")),
        "body_type": _parse_str(raw.get("body_type")),
        "transmission": _parse_str(raw.get("transmission")),
        "fuel_type": _parse_str(raw.get("fuel_type")),
        "engine": _parse_str(raw.get("engine")),
        "plate_number": _parse_str(raw.get("plate_number")),
        "doors": _parse_int(raw.get("doors")),
        "seats": _parse_int(raw.get("seats")),
        "options": _parse_str(raw.get("options")),
        "exterior_condition": _parse_str(raw.get("exterior_condition")),
        "interior_condition": _parse_str(raw.get("interior_condition")),
        "import_source": import_source,
        "status": _parse_status(raw.get("status")),
    }


def _map_headers(headers: list[Any]) -> dict[int, str]:
    aliases = _alias_map()
    mapping: dict[int, str] = {}
    for idx, h in enumerate(headers):
        key = aliases.get(_norm_header(h))
        if key:
            mapping[idx] = key
    return mapping


def _rows_from_csv(data: bytes) -> list[dict[str, Any]]:
    text = data.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows_list = list(reader)
    if not rows_list:
        return []
    mapping = _map_headers(rows_list[0])
    if not mapping:
        raise ValueError("No recognized column headers")
    out: list[dict[str, Any]] = []
    for row in rows_list[1:]:
        if not any(str(c).strip() for c in row):
            continue
        raw: dict[str, Any] = {}
        for idx, key in mapping.items():
            if idx < len(row):
                raw[key] = row[idx]
        out.append(raw)
    return out


def _rows_from_xlsx(data: bytes) -> list[dict[str, Any]]:
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header = next(rows_iter)
    except StopIteration:
        return []
    mapping = _map_headers(list(header))
    if not mapping:
        raise ValueError("No recognized column headers")
    out: list[dict[str, Any]] = []
    for row in rows_iter:
        if row is None or not any(c is not None and str(c).strip() for c in row):
            continue
        raw: dict[str, Any] = {}
        for idx, key in mapping.items():
            if idx < len(row):
                raw[key] = row[idx]
        out.append(raw)
    return out


def parse_vehicle_file(filename: str, data: bytes) -> list[dict[str, Any]]:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        raw_rows = _rows_from_csv(data)
        source = f"csv:{filename}"
    elif name.endswith(".xlsx") or name.endswith(".xlsm"):
        raw_rows = _rows_from_xlsx(data)
        source = f"xlsx:{filename}"
    else:
        raise ValueError("Unsupported file type. Use .csv or .xlsx")

    payloads: list[dict[str, Any]] = []
    errors: list[str] = []
    for i, raw in enumerate(raw_rows, start=2):  # 1-based + header
        try:
            payloads.append(_row_to_payload(raw, import_source=source))
        except Exception as e:  # noqa: BLE001 — collect row errors
            errors.append(f"row {i}: {e}")
    if errors and not payloads:
        raise ValueError("; ".join(errors[:5]))
    # Attach soft errors as empty skip — caller handles via return meta
    if errors:
        # Re-raise with partial? Better return tuple. Keep simple: raise if any hard.
        pass
    return payloads


def parse_vehicle_file_with_errors(
    filename: str, data: bytes
) -> tuple[list[dict[str, Any]], list[str]]:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        raw_rows = _rows_from_csv(data)
        source = f"csv:{filename}"
    elif name.endswith(".xlsx") or name.endswith(".xlsm"):
        raw_rows = _rows_from_xlsx(data)
        source = f"xlsx:{filename}"
    else:
        raise ValueError("Unsupported file type. Use .csv or .xlsx")

    payloads: list[dict[str, Any]] = []
    errors: list[str] = []
    for i, raw in enumerate(raw_rows, start=2):
        try:
            payloads.append(_row_to_payload(raw, import_source=source))
        except Exception as e:  # noqa: BLE001
            errors.append(f"row {i}: {e}")
    return payloads, errors
