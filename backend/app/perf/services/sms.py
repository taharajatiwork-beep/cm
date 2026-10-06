"""نمونه پیام: سه نوع، هر کدام در سقف نویسهٔ خودش."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.perf.sms_rules import billed_len, check_sms, ensure_opt_out, latin_digits

_KINDS = (
    ("ad1", "تبلیغاتی، یک صفحه", 70),
    ("ad2", "تبلیغاتی، دو صفحه", 134),
    ("service", "خدماتی، یک صفحه", 70),
)


def _phone(phone: str) -> str:
    digits = re.sub(r"\D", "", latin_digits(phone or ""))
    if digits.startswith("98") and len(digits) >= 12:
        digits = "0" + digits[2:]
    if not digits:
        return "021-47677777"
    if digits.startswith(("021", "026")) and len(digits) > 4:
        return f"{digits[:3]}-{digits[3:]}"
    return digits


def _link(link: str) -> str:
    raw = (link or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.netloc or "").removeprefix("www.")
    path = (parsed.path or "").strip("/").split("/")[0]
    if host and path:
        short = f"{host}/{path}"
        if len(short) <= 22:
            return short
    return host or raw


def _fit_parts(head: str, middle: list[str], tail: list[str], cap: int) -> str:
    """برند، تلفن، لینک و لغو۱۱ می‌مانند. توضیح اضافه تا سقف نویسه کوتاه می‌شود."""
    mid = [line.strip() for line in middle if line and line.strip()]
    tail = [line.strip() for line in tail if line and line.strip()]
    head = (head or "").strip()
    while True:
        body = "\n".join(line for line in [head, *mid, *tail] if line)
        extra = billed_len(body) - cap
        if extra <= 0:
            return body
        if mid:
            if 0 < extra < billed_len(mid[-1]):
                mid[-1] = mid[-1][:-extra].rstrip()
                if billed_len(mid[-1]) < 4:
                    mid.pop()
            else:
                mid.pop()
            continue
        room = cap - billed_len("\n".join(tail)) - (1 if tail and head else 0)
        if 0 < room < billed_len(head):
            head = head[:room].rstrip()
            continue
        return "\n".join(line for line in [head, *tail] if line)


def _pack_one(kind: str, label: str, text: str, brand: str) -> dict:
    body = ensure_opt_out(text)
    checked = check_sms(body, brand=brand)
    cap = next(limit for key, _, limit in _KINDS if key == kind)
    if kind == "ad2" and checked["pages"] < 2:
        note = "هنوز در یک صفحه جا شد؛ هزینه دو برابر نشده است."
    elif checked["pages"] > 1 and cap <= 70:
        note = "در یک صفحه جا نشد؛ هزینه دو برابر یک صفحه است."
    elif checked["pages"] == 2:
        note = "دو صفحه. هزینهٔ هر گیرنده دو برابر نمونهٔ یک‌صفحه‌ای است."
    else:
        note = f"یک صفحه، {checked['room']} نویسه تا دو برابر شدن هزینه."
    return {"kind": kind, "label": label, "note": note, "text": body, "check": checked}


def _tail(phone: str, link: str, sign: str) -> list[str]:
    lines = [phone]
    if link:
        lines.append(link)
    lines.extend([sign, "لغو11"])
    return lines


def _templates(brand: str, cars: str, offer: str, phone: str, link: str) -> list[dict]:
    phone = _phone(phone)
    link = _link(link)
    brand = (brand or "").strip()
    cars = (cars or "").strip()
    offer = (offer or "تحویل فوری").strip()
    car_line = "، ".join(part for part in (cars, offer) if part)
    headline = " ".join(part for part in (brand, cars) if part) or "ستوده"
    short = _tail(phone, link, "ستوده")
    ad1 = _fit_parts(brand or headline, [car_line] if brand else [], short, 70)
    ad2 = _fit_parts(headline, [offer, "نقد و اقساط"], _tail(phone, link, "گروه خودرویی ستوده"), 134)
    service_line = f"{headline}، {offer}" if offer and offer not in headline else headline
    service = _fit_parts("مشتری عزیز", [service_line], short, 70)
    return [
        _pack_one("ad1", "تبلیغاتی، یک صفحه", ad1, brand),
        _pack_one("ad2", "تبلیغاتی، دو صفحه", ad2, brand),
        _pack_one("service", "خدماتی، یک صفحه", service, brand),
    ]


async def draft_messages(
    *,
    brand: str,
    cars: str,
    offer: str,
    phone: str,
    link: str,
    campaign_code: str = "",
) -> dict:
    return {
        "source": "template",
        "messages": _templates(brand, cars, offer, phone, link),
    }
