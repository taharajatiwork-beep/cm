"""Map CM Vehicle → Divar pilot product payload (category=vehicles)."""

from __future__ import annotations

from typing import Any

from app.models.inventory import Vehicle

# Brand labels commonly used on Divar (Persian).
_BRAND_FA = {
    "toyota": "تویوتا",
    "honda": "هوندا",
    "hyundai": "هیوندای",
    "kia": "کیا",
    "peugeot": "پژو",
    "bmw": "بی‌ام‌و",
    "mercedes": "مرسدس",
}


def vehicle_to_divar_product(vehicle: Vehicle, *, city: str = "تهران") -> dict[str, Any]:
    brand = vehicle.brand or ""
    model = vehicle.model or ""
    brand_fa = _BRAND_FA.get(brand.lower(), brand)
    stock = f" #{vehicle.stock_number}" if vehicle.stock_number else ""
    title = f"{brand_fa} {model}{stock}".strip()
    year = str(vehicle.year) if vehicle.year else ""
    mileage = f"{vehicle.mileage:,} کیلومتر" if vehicle.mileage is not None else ""
    color = vehicle.color or ""
    price = int(vehicle.sale_price or vehicle.purchase_price or 0)

    lines = [
        f"{brand_fa} {model} مدل {year}".strip(),
        f"رنگ: {color}" if color else None,
        f"کارکرد: {mileage}" if mileage else None,
        f"VIN: {vehicle.vin}" if vehicle.vin else None,
        f"شماره انبار: {vehicle.stock_number}" if vehicle.stock_number else None,
        "آگهی از سامانه داخلی — تأیید نهایی توسط اپراتور.",
    ]
    description = "\n".join(x for x in lines if x)

    # Placeholder image so mapping validation can pass in assisted flow;
    # operator replaces / uploads real photos in Divar UI.
    images = [f"https://cdn.example.test/cm/{vehicle.id}/01.jpg"]

    return {
        "title": title,
        "description": description,
        "price": price,
        "category": "vehicles",
        "city": city,
        "attributes": {
            "brand": brand_fa,
            "model": model,
            "year": year,
            "mileage": mileage or "0 کیلومتر",
            "color": color,
            "gearbox": "",
            "trim": vehicle.trim or "",
            "vin": vehicle.vin,
            "stock_number": vehicle.stock_number or "",
        },
        "images": images,
        "external_vehicle_id": str(vehicle.id),
    }
