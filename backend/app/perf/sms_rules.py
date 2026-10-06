"""قواعد متن پیامک تبلیغاتی: صفحه، لغو۱۱، شماره، لینک و برند."""

from __future__ import annotations

import math
import re

_DIGIT = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_PERSIAN = re.compile(r"[\u0600-\u06FF]")
_PHONE = re.compile(r"(0\d{10}|98\d{10}|\d{8,})")
_LINK = re.compile(r"(https?://|www\.|\.(?:ir|com)\b)", re.IGNORECASE)
OPT_OUT = "لغو11"


def latin_digits(text: str) -> str:
    return (text or "").translate(_DIGIT)


# مجموعهٔ GSM 7-bit. بیرون از این مجموعه، حتی یک حرف، کل پیام را یونیکد می‌کند.
_GSM = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
_GSM_EXT = set("^{}\\[~]|€")


def is_persian(text: str) -> bool:
    return uses_ucs2(text)


def uses_ucs2(text: str) -> bool:
    """فارسی، عربی یا ایموجی کل پیام را ۱۶بیتی می‌کند؛ آن‌وقت سقف ۷۰ است نه ۱۶۰."""
    if _PERSIAN.search(text or ""):
        return True
    return any(ch not in _GSM and ch not in _GSM_EXT for ch in (text or ""))


def billed_len(text: str) -> int:
    """نویسهٔ قابل‌صورتحساب. ایموجی دو واحد است. نویسهٔ توسعه‌ای لاتین هم دو واحد."""
    raw = text or ""
    if not raw:
        return 0
    if uses_ucs2(raw):
        return len(raw.encode("utf-16-le")) // 2
    return sum(2 if ch in _GSM_EXT else 1 for ch in raw)


def page_limits(text: str) -> tuple[int, int]:
    """سقف صفحهٔ اول و سقف هر صفحهٔ بعدی. مرز دو صفحه برای فارسی ۱۳۴ است، نه ۱۳۷."""
    if uses_ucs2(text):
        return 70, 67
    return 160, 153


def page_count(text: str) -> int:
    n = billed_len(text)
    if n == 0:
        return 0
    single, part = page_limits(text)
    if n <= single:
        return 1
    return math.ceil(n / part)


def page_shape(text: str) -> dict:
    n = billed_len(text)
    single, part = page_limits(text)
    pages = page_count(text)
    capacity = single if pages <= 1 else part * pages
    return {
        "pages": pages,
        "chars": n,
        "persian": uses_ucs2(text),
        "language": "فارسی" if uses_ucs2(text) else "انگلیسی",
        "single_limit": single,
        "part_limit": part,
        "capacity": capacity if n else single,
        "room": (single if n == 0 else capacity) - n,
    }


def has_opt_out(text: str) -> bool:
    compact = latin_digits(text).replace(" ", "").replace("\n", "").replace("\u200c", "")
    return compact.endswith("لغو11")


def ensure_opt_out(text: str) -> str:
    body = (text or "").rstrip()
    if has_opt_out(body):
        return body
    return f"{body}\n{OPT_OUT}" if body else OPT_OUT


def check_sms(text: str, *, brand: str = "") -> dict:
    shape = page_shape(text)
    pages = shape["pages"]
    issues: list[str] = []
    warnings: list[str] = []
    if not has_opt_out(text):
        issues.append("عبارت لغو11 باید آخر متن باشد")
    if pages > 10:
        issues.append("متن بیش از ۱۰ صفحه است")
    if pages == 0:
        issues.append("متن خالی است")
    if not _PHONE.search(latin_digits(text)):
        issues.append("شماره تماس در متن نیست")
    if not _LINK.search(text or ""):
        warnings.append("لینک در متن نیست. در ارسال‌های شیت هم اغلب فقط تلفن و نام ستوده آمده است.")
    if brand and brand.strip() not in (text or ""):
        issues.append("نام برند در متن نیست")
    if pages == 1:
        warnings.append(f"یک صفحه است. نویسهٔ {shape['single_limit'] + 1} هزینه را دو برابر می‌کند.")
    elif pages == 2:
        warnings.append("دو صفحه است. هزینهٔ هر گیرنده دو برابر یک صفحه است.")
    elif pages > 2:
        warnings.append(f"{pages} صفحه است. هر صفحه یک واحد شارژ جدا می‌گیرد.")
    return {
        **shape,
        "opt_out": has_opt_out(text),
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
    }


def estimate_cost(pages: int, recipients: int, tariff_toman: int) -> int:
    if pages < 1 or recipients < 1 or tariff_toman < 1:
        return 0
    return pages * recipients * tariff_toman
