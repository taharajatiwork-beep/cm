"""Persian labels for vehicle brand/model tokens stored in English in the DB."""

from __future__ import annotations

_VALUE_LABELS: dict[str, str] = {
    "white": "سفید",
    "red": "قرمز",
    "black": "مشکی",
    "silver": "نقره‌ای",
    "gray": "خاکستری",
    "grey": "خاکستری",
    "blue": "آبی",
    "toyota": "تویوتا",
    "hyundai": "هیوندای",
    "kia": "کیا",
    "peugeot": "پژو",
    "renault": "رنو",
    "mercedes": "مرسدس بنز",
    "mercedes-benz": "مرسدس بنز",
    "bmw": "بی‌ام‌و",
    "nissan": "نیسان",
    "mazda": "مزدا",
    "suzuki": "سوزوکی",
    "mg": "ام‌جی",
    "chery": "چری",
    "geely": "جیلی",
    "haval": "هاوال",
    "jac": "جک",
    "mvm": "ام‌وی‌ام",
    "camry": "کمری",
    "tucson": "توسان",
    "sportage": "اسپورتیج",
    "cerato": "سراتو",
    "elantra": "النترا",
}


def fa_vehicle_label(value: str | None) -> str:
    if not value:
        return ""
    raw = value.strip()
    return _VALUE_LABELS.get(raw.lower(), raw)


def fa_vehicle_name(brand: str | None, model: str | None) -> str:
    parts = [fa_vehicle_label(brand), fa_vehicle_label(model)]
    return " ".join(part for part in parts if part).strip()
