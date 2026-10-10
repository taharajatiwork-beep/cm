"""درخواست‌های تبلیغ از میزیتو → پیش‌نویس کمپین (برش A: فقط «بررسی دوباره»ی دستی).

قانون‌ها:
- فقط خواندن. هر تماس از mizito_post می‌گذرد که مسیر بیرون از ALLOWED_ENDPOINTS را رد می‌کند
  (هیچ seen، getChatView، tasks.get، نوشتن یا علامت خواندن).
- پیش‌نویس هرگز خودکار کمپین نمی‌شود؛ فقط کاربر مارکتینگ با «ساخت کمپین» تاییدش می‌کند.
- از هر پیام فقط فیلدهای استخراج‌شده و حداکثر ۳۰۰ نویسه خلاصه در پایگاه دادهٔ خود پنل می‌ماند.
  توکن‌ها (از جمله access_token هر کارت)، فهرست اعضا، منشن‌ها و پیوست‌ها نگه داشته نمی‌شوند.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.perf.campaign_register import TAGS
from app.perf.models import PmCampaign, PmMizitoCursor, PmMizitoRequest
from app.perf.services.common import PerfError, iso
from app.perf.services.common import now as utc_now
from app.perf.services.mizito import _id, _tasks, campaign_code, code_key, mizito_post

KINDS = ("start", "stop", "sms", "circular")
STATUSES = ("new", "approved", "rejected", "duplicate")
OPEN_STATUSES = ("new", "duplicate")
EXCERPT_CHARS = 300
HISTORY_PAGE = 15
_TASK_KINDS = frozenset(KINDS)
_LIST_LIMIT = 200

# ---------------------------------------------------------------- متن

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٬٫", "01234567890123456789,.")
_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "أ": "ا", "إ": "ا", "ـ": None})


def clean_text(text: Any) -> str:
    """رقم‌های فارسی/عربی → لاتین، ي/ك → ی/ک، نیم‌فاصله → فاصله، فاصله‌های پشت‌سرهم → یکی."""
    value = str(text or "").translate(_DIGITS).translate(_LETTERS)
    value = value.replace("\u200c", " ").replace("\u200f", "").replace("\u200e", "")
    return re.sub(r"\s+", " ", value).strip()


def fold(text: Any) -> str:
    return clean_text(text).lower()


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text) is not None


def _word(phrase: str) -> str:
    return rf"(?<!\w){re.escape(phrase)}(?!\w)"


# ---------------------------------------------------------------- نوع درخواست

_STOP = (
    r"متوقف",
    r"(?<!\w)توقف",
    r"(?<!\w)کنسل",
    r"(?<!\w)لغو",
    r"قطع (?:شود|گردد)",
    r"عدم تبلیغ",
    r"تبلیغ(?:ات)? (?:نشود|انجام نشود|نکنید)",
    r"ادامه (?:ندهید|نیابد|نشود)",
)
_START = (
    r"تبلیغ",
    r"کمپین",
    r"پیامک",
    r"(?<![a-z])(?:sms|lbs)(?![a-z])",
    r"استوری",
    r"بلاگر",
    r"تولید محتوا",
    r"(?:اجرا|انجام|بیشتر|شروع|آغاز) (?:شود|گردد)",
    r"(?<!\w)افزایش",
    r"ثبت ?نام",
    r"پیش ?فروش",
    r"(?<!\w)حواله",
    r"بخشنامه",
    r"شرایط فروش",
)
_EXECUTION = (
    r"(?:ارسال|منتشر|انجام|اجرا|بارگذاری|آپلود) (?:شد|شده|گردید)(?!\w)",
    r"(?<!\w)گزارش",
    r"تعداد (?:ارسال|کل|پیامک)",
)


def classify(text: str) -> str:
    """start | stop | info. توقف اولویت دارد («تبلیغات متوقف شود» توقف است، نه شروع)."""
    body = fold(text)
    if any(_has(body, pattern) for pattern in _STOP):
        return "stop"
    if any(_has(body, pattern) for pattern in _START):
        return "start"
    return "info"


def looks_like_execution_report(text: str) -> bool:
    """گزارش اجرای تیم پرفورمنس («پیامک ارسال شد»، «گزارش…») درخواست تازه نیست."""
    body = fold(text)
    return any(_has(body, pattern) for pattern in _EXECUTION)


# ---------------------------------------------------------------- تنظیم


@dataclass(frozen=True)
class Brand:
    tag: str
    name: str
    patterns: tuple[str, ...]


_GENERIC_TAGS = frozenset({"S", "AC", "I", "EV"})
_GENERIC_WORDS = frozenset({"همه", "برقی", "وارداتی", "ترکیبی", "خودرو", "موتور"})


def brands_from_register(rows: Iterable[dict] = TAGS) -> tuple[Brand, ...]:
    """برندها از دفتر شمارهٔ خود پنل؛ هم اسم کامل، هم کلمهٔ اول اگر خاص باشد («ماموت»)."""
    found: list[Brand] = []
    for row in rows:
        tag = str(row.get("tag") or "").strip().upper()
        name = clean_text(row.get("brand"))
        if not tag or not name or tag in _GENERIC_TAGS:
            continue
        names = {fold(name)}
        english = fold(row.get("en"))
        if english:
            names.add(english)
        first = fold(name).split(" ")[0]
        if len(first) >= 4 and first not in _GENERIC_WORDS:
            names.add(first)
        found.append(Brand(tag=tag, name=name, patterns=tuple(sorted(names, key=len, reverse=True))))
    return tuple(found)


def _split(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in re.split(r"[,،\n]", value or "") if part.strip())


def _boards(value: str) -> dict[str, str]:
    """ "<board_id>=circular,<board_id>=sms" → {board_id: kind}."""
    out: dict[str, str] = {}
    for part in _split(value):
        board, _, kind = part.partition("=")
        kind = kind.strip().lower() or "circular"
        if board.strip() and kind in _TASK_KINDS:
            out[board.strip()] = kind
    return out


@dataclass(frozen=True)
class RequestConfig:
    dialogs: tuple[str, ...] = ()
    task_boards: dict[str, str] = field(default_factory=dict)
    requester_ids: frozenset[str] = frozenset()
    ignore_ids: frozenset[str] = frozenset()
    brands: tuple[Brand, ...] = ()
    car_models: tuple[str, ...] = ()
    branches: tuple[str, ...] = ()
    lookback_days: int = 7
    respect_unread: bool = True
    max_pages: int = 20

    @classmethod
    def from_settings(cls) -> RequestConfig:
        s = get_settings()
        return cls(
            dialogs=_split(s.perf_mizito_request_dialogs),
            task_boards=_boards(s.perf_mizito_task_boards),
            requester_ids=frozenset(_split(s.perf_mizito_requester_ids)),
            ignore_ids=frozenset(_split(s.perf_mizito_ignore_ids)),
            brands=brands_from_register(),
            car_models=_split(s.perf_mizito_car_models),
            branches=_split(s.perf_mizito_branches),
            lookback_days=max(0, min(int(s.perf_mizito_lookback_days), 60)),
            respect_unread=bool(s.perf_mizito_respect_unread),
            max_pages=max(1, min(int(s.perf_mizito_history_pages), 100)),
        )


# ---------------------------------------------------------------- استخراج

_MONTHS = "فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|ابان|آذر|اذر|دی|بهمن|اسفند"
_DATE_WORDS = re.compile(rf"(?<!\d)(\d{{1,2}}) ?(?:ام )?({_MONTHS})(?!\w)(?: ?(?:ماه)? ?(1[34]\d\d))?")
_DATE_NUMERIC = re.compile(r"(?<!\d)(1[34]\d\d)[/\-.](\d{1,2})[/\-.](\d{1,2})(?!\d)")
_DATE_RELATIVE = (
    "از امروز",
    "از فردا",
    "هفته جاری",
    "هفته آینده",
    "هفته آتی",
    "تا پایان هفته",
    "تا اطلاع ثانوی",
    "روزانه",
    "هفتگی",
)
_AMOUNT = r"\d[\d,.]*(?: ?(?:میلیارد|میلیون|هزار))?(?: ?(?:تومان|ریال))?"
_PRICE = re.compile(
    r"(?<![\w.])(\d[\d,.]*) ?(میلیارد|میلیون)?(?: ?(تومان|ریال))(?!\w)|(?<![\w.])(\d[\d,.]*) ?(میلیارد|میلیون)(?!\w)"
)
_DELIVERY = re.compile(r"تحویل[^\d]{0,20}?(\d{1,3}) ?(?:روز|روزه)(?!\w)")
_PREPAY = re.compile(rf"پیش ?پرداخت[^\d]{{0,20}}?(\d{{1,2}} ?(?:%|درصد)|{_AMOUNT})")
_MODEL = re.compile(r"(?<![\w.])([A-Za-z]{1,6}[.\-]?\d{1,4}[A-Za-z+]{0,4})(?![\w.])")
_BRANCH = re.compile(r"(?<!\w)شعبه (?!های|ها|ی )([\u0621-\u064A\u067E\u0686\u0698\u06A9\u06AF\u06CC]{2,15})")
_BRANCH_SKIP = frozenset(
    {"پیش", "از", "در", "به", "با", "و", "را", "برای", "جدید", "محترم", "مربوطه", "مورد", "خود", "اصلی", "دیگر", "هم"}
)
_CODE_AFTER_WORD = re.compile(r"کمپین[^A-Za-z\n]{0,60}?\(?([A-Za-z]{1,3}\d{1,3})(?!\w)")
_CODE_IN_PARENS = re.compile(r"\(\s*([A-Za-z]{1,3}\d{1,3})\s*\)")
_BRAND_CARD = re.compile(r"^تبلیغات (?:برند )?(.+)$")

_CHANNELS: tuple[tuple[str, str], ...] = (
    ("sms", r"پیامک|(?<![a-z])sms(?![a-z])"),
    ("lbs", r"(?<![a-z])lbs(?![a-z])|پیامک منطقه|لوکیشن"),
    ("ig_story", r"استوری|اینستاگرام|(?<!\w)پیج|سوشال|(?<![a-z])social(?![a-z])"),
    ("influencer", r"بلاگر|اینفلوئنسر"),
    ("divar", r"(?<!\w)دیوار"),
    ("google", r"گوگل|(?<![a-z])google(?![a-z])"),
    ("banner", r"(?<!\w)بنر"),
    ("content", r"تولید محتوا|ویدیو|ویدئو"),
)
_PANEL_CHANNEL = {"sms": "sms", "lbs": "sms", "ig_story": "ig_story", "influencer": "ig_story", "content": "ig_story"}


def _unique(items: Iterable[str], limit: int) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
        if len(out) >= limit:
            break
    return out


def brand_card_name(title: str) -> str:
    """«تبلیغات X» یا «تبلیغات برند X» → X؛ بقیه → ""."""
    match = _BRAND_CARD.match(clean_text(title))
    return match.group(1).strip() if match else ""


def find_brand(text: str, title: str, brands: Iterable[Brand]) -> tuple[str, str]:
    """(برند، حرف دفتر). اول عنوان کارت، بعد متن. برند ناشناخته از «تبلیغات X» همان X می‌ماند."""
    ordered = sorted(brands, key=lambda item: max((len(p) for p in item.patterns), default=0), reverse=True)
    for haystack in (fold(title), fold(text)):
        for brand in ordered:
            if any(_has(haystack, _word(pattern)) for pattern in brand.patterns):
                return brand.name, brand.tag
    return brand_card_name(title), ""


def extract_code(notes: str, text: str = "") -> str:
    """فقط کد کمپین از یادداشت کارت (مثل «کمپین N90» یا «(U92)»)؛ بقیهٔ یادداشت نگه داشته نمی‌شود."""
    for source in (notes, text):
        body = clean_text(source)
        for pattern in (_CODE_AFTER_WORD, _CODE_IN_PARENS):
            match = pattern.search(body)
            if match:
                return code_key(match.group(1))
    fallback = campaign_code(clean_text(notes))
    return code_key(fallback) if fallback else ""


def find_cars(text: str, title: str, models: Iterable[str], skip: Iterable[str] = ()) -> list[str]:
    body = f"{clean_text(title)} {clean_text(text)}"
    folded = body.lower()
    hits: list[str] = []
    # اسم بلندتر اول؛ «کرولا» وقتی «کرولا کراس» پیدا شده دوباره نمی‌آید.
    for model in sorted((item for item in models if item), key=lambda item: len(fold(item)), reverse=True):
        key = fold(model)
        if _has(folded, _word(key)) and not any(_has(fold(hit), _word(key)) for hit in hits):
            hits.append(model)
    blocked = {code_key(item) for item in skip if item}
    known = " ".join(fold(hit) for hit in hits)
    for match in _MODEL.finditer(body):
        token = match.group(1)
        if code_key(token) not in blocked and not token.isdigit() and not _has(known, _word(token.lower())):
            hits.append(token)
    return _unique(hits, 8)


def find_offer(text: str) -> dict:
    body = clean_text(text)
    folded = body.lower()
    delivery = _DELIVERY.search(body)
    prepay = _PREPAY.search(body)
    prices = []
    for match in _PRICE.finditer(body):
        prices.append(" ".join(part for part in match.groups() if part))
    return {
        "no_price": "بدون قیمت" in folded,
        "delivery_days": int(delivery.group(1)) if delivery else None,
        "prices": _unique(prices, 5),
        "prepayment": prepay.group(1).strip() if prepay else "",
        "installments": _has(folded, r"اقساط|(?<!\w)قسط"),
        "no_budget_limit": _has(folded, r"بدون محدودیت"),
    }


def find_channels(text: str) -> list[str]:
    body = fold(text)
    return [key for key, pattern in _CHANNELS if _has(body, pattern)]


def find_branches(text: str, branches: Iterable[str]) -> list[str]:
    body = clean_text(text)
    folded = body.lower()
    hits = [name for name in branches if name and _has(folded, _word(fold(name)))]
    hits.extend(match.group(1) for match in _BRANCH.finditer(body) if match.group(1) not in _BRANCH_SKIP)
    return _unique(hits, 5)


def find_dates(text: str) -> list[str]:
    body = clean_text(text)
    hits = [" ".join(part for part in match.groups() if part) for match in _DATE_WORDS.finditer(body)]
    hits.extend("/".join(match.groups()) for match in _DATE_NUMERIC.finditer(body))
    hits.extend(phrase for phrase in _DATE_RELATIVE if phrase in body)
    return _unique(hits, 6)


def extract(text: str, *, title: str = "", notes: str = "", config: RequestConfig | None = None) -> dict:
    """همهٔ فیلدهای پیش‌نویس از متن درخواست. تابع خالص است (بدون شبکه و پایگاه داده)."""
    config = config or RequestConfig()
    code = extract_code(notes, text)
    brand, tag = find_brand(text, title, config.brands)
    return {
        "intent": classify(text),
        "brand": brand[:80],
        "tag": tag,
        "cars": find_cars(text, title, config.car_models, skip=[code]),
        "offer": find_offer(text),
        "channels": find_channels(text),
        "branches": find_branches(text, config.branches),
        "dates": find_dates(text),
        "code": code,
        "card_title": clean_text(title)[:120],
    }


def suggest(fields: dict, kind: str) -> dict:
    """پیشنهاد فرم «کمپین تازه»: عنوان، حرف برند، برند و کانال‌های پنل."""
    brand = str(fields.get("brand") or "")
    cars = [str(item) for item in fields.get("cars") or []][:3]
    subject = " ".join(part for part in (brand, "، ".join(cars)) if part) or str(fields.get("card_title") or "")
    prefix = "مینی کمپین بخشنامه" if kind == "circular" else "کمپین پیامک" if kind == "sms" else "کمپین"
    channels = _unique((_PANEL_CHANNEL.get(item, "") for item in fields.get("channels") or []), 2)
    if kind == "sms" and "sms" not in channels:
        channels.insert(0, "sms")
    return {
        "title": f"{prefix} {subject}".strip()[:120],
        "tag": str(fields.get("tag") or ""),
        "brand": brand,
        "channels": channels or ["sms"],
    }


def offer_summary(fields: dict) -> str:
    offer = fields.get("offer") or {}
    bits = []
    if offer.get("no_price"):
        bits.append("بدون قیمت")
    if offer.get("delivery_days"):
        bits.append(f"تحویل {offer['delivery_days']} روز")
    if offer.get("prepayment"):
        bits.append(f"پیش‌پرداخت {offer['prepayment']}")
    if offer.get("installments"):
        bits.append("اقساطی")
    bits.extend(fields.get("dates") or [])
    return " · ".join(bits)[:255]


# ---------------------------------------------------------------- تشخیص از پیام/کارت


@dataclass
class Candidate:
    source_key: str
    source_kind: str  # dialog | task
    source_id: str
    source_title: str
    kind: str
    text: str
    title: str = ""
    notes: str = ""
    author: str = ""
    msg_index: int | None = None
    happened_at: datetime | None = None


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


ROLES = ("cards", "texts", "both")


def message_candidate(message: Any, dialog: dict, role: str, config: RequestConfig) -> Candidate | None:
    """یک پیام گفتگو → درخواست یا None.

    role="cards": گزارش (REPORT) یا کارت تازه روی کارت «تبلیغات …» (یا از فرستندهٔ تعریف‌شده).
    role="texts": متن ساده (مثل گروه بخشنامه‌ها) → «بخشنامه».
    role="both": هر دو.
    """
    if not isinstance(message, dict) or message.get("deleted"):
        return None
    author = str(message.get("from") or "")
    if author and author in config.ignore_ids:
        return None
    index = message.get("msg_index")
    base = {
        "source_kind": "dialog",
        "source_id": str(dialog.get("_id") or ""),
        "source_title": clean_text(dialog.get("title"))[:120],
        "author": author,
        "msg_index": int(index) if isinstance(index, int) else None,
        "happened_at": parse_time(message.get("date")),
        "source_key": f"dialog:{dialog.get('_id')}:{index}",
    }
    media = message.get("media") if isinstance(message.get("media"), dict) else {}
    if role in ("texts", "both") and not media.get("_"):
        text = str(message.get("message") or "")
        if message.get("_") != "message" or len(clean_text(text)) < 15:
            return None
        return Candidate(kind="circular", text=text, **base)
    if role not in ("cards", "both"):
        return None
    if media.get("_") != "messageMediaTask" or not isinstance(media.get("task"), dict):
        return None
    task = media["task"]
    title = str(task.get("title") or "")
    notes = str(task.get("notes") or "")
    brand_card = bool(brand_card_name(title))
    requester = bool(author) and author in config.requester_ids
    if not (brand_card or requester):
        return None
    changes = media.get("changes")
    if not changes:
        return Candidate(kind="start", text=title, title=title, notes=notes, **base)
    after = changes.get("to") if isinstance(changes, dict) and isinstance(changes.get("to"), dict) else {}
    comment = after.get("user_comment")
    if not isinstance(comment, str) or not clean_text(comment):
        return None
    if not requester and looks_like_execution_report(comment):
        return None
    intent = classify(comment)
    if intent == "info":
        return None
    return Candidate(kind=intent, text=comment, title=title, notes=notes, **base)


def task_stamp(task: dict) -> datetime | None:
    comment = task.get("last_comment") if isinstance(task.get("last_comment"), dict) else {}
    stamps = [parse_time(task.get("created_at")), parse_time(comment.get("comment_at"))]
    found = [stamp for stamp in stamps if stamp]
    return max(found) if found else None


def task_candidate(task: Any, config: RequestConfig, since: datetime) -> Candidate | None:
    """کارت تازه یا گزارش تازه در بردهای تعریف‌شدهٔ کال سنتر (از tasks/getAll)."""
    if not isinstance(task, dict) or task.get("deleted"):
        return None
    kind = config.task_boards.get(str(task.get("kanban_board") or ""))
    stamp = task_stamp(task)
    if not kind or stamp is None or stamp <= since:
        return None
    comment = task.get("last_comment") if isinstance(task.get("last_comment"), dict) else {}
    title = str(task.get("title") or "")
    body = str(comment.get("comment") or "") if not comment.get("deleted") else ""
    author = str(comment.get("comment_owner") or task.get("owner") or "")
    if author and author in config.ignore_ids:
        return None
    return Candidate(
        source_key=f"task:{_id(task)}:{stamp.isoformat()}",
        source_kind="task",
        source_id=_id(task),
        source_title="کال سنتر",
        kind=kind,
        text=f"{title} — {body}" if body else title,
        title=title,
        notes=str(task.get("notes") or ""),
        author=author,
        happened_at=stamp,
    )


# ---------------------------------------------------------------- خواندن (فقط مسیرهای مجاز)


def _dialog_rows(payload: Any) -> list[dict]:
    rows = payload.get("dialogs") if isinstance(payload, dict) else payload
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _message_rows(payload: Any) -> list[dict]:
    rows = payload.get("messages") if isinstance(payload, dict) else payload
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def tracked(dialogs: list[dict], entries: Iterable[str]) -> list[tuple[dict, str]]:
    """گفتگوهای پیگیری‌شده با اسم پیدا می‌شوند. هر ورودی «اسم=نقش» است (cards، texts یا both).

    بدون نقش: گروه پروژه → cards، گروه ساده → texts. گروه «بخشنامه های فروش» خودش گروه پروژه است،
    پس نقشش در تنظیم پیش‌فرض صریحاً texts است.
    """
    wanted = []
    for entry in entries:
        title, _, role = entry.partition("=")
        if fold(title):
            wanted.append((fold(title), role.strip().lower()))
    out = []
    for dialog in dialogs:
        name = fold(dialog.get("title"))
        if not name or not _id(dialog):
            continue
        for title, role in wanted:
            if title in name:
                if role not in ROLES:
                    role = "cards" if dialog.get("is_project_group") or dialog.get("project_entity") else "texts"
                out.append((dialog, role))
                break
    return out


@dataclass
class Collected:
    candidates: list[Candidate] = field(default_factory=list)
    positions: dict[str, int] = field(default_factory=dict)
    stamps: dict[str, datetime] = field(default_factory=dict)
    dialogs: int = 0
    pages: int = 0
    tasks_checked: bool = False


class Reader:
    """تنها درگاه شبکه برای این بخش؛ همه چیز از mizito_post با فهرست مجاز می‌گذرد."""

    def __init__(self, client: httpx.AsyncClient, base: str, token: str):
        self.client = client
        self.base = base.rstrip("/")
        self.headers = {"x-token": token, "Content-Type": "application/json"}
        self.calls: list[str] = []

    async def call(self, path: str, body: dict) -> Any:
        self.calls.append(path)
        return await mizito_post(self.client, self.base, path, self.headers, body)


async def _read_dialog(
    reader: Reader, dialog: dict, role: str, cursor: int | None, config: RequestConfig, now: datetime, out: Collected
) -> None:
    key = f"dialog:{_id(dialog)}"
    total = int(dialog.get("messages_count") or 0)
    offset = int(dialog.get("unread_count") or 0) if config.respect_unread else 0
    offset = max(offset, 0)
    if cursor is None and config.lookback_days <= 0:
        out.positions[key] = max(total - offset, 0)  # اولین بار فقط نشانه می‌گذارد
        return
    if cursor is not None and total <= cursor:
        return
    cutoff = now - timedelta(days=config.lookback_days)
    newest: int | None = None
    for _ in range(config.max_pages):
        page = _message_rows(await reader.call("chat/getHistory", {"dialog": _id(dialog), "offset": offset}))
        out.pages += 1
        if not page:
            break
        reached = False
        for message in page:
            index = message.get("msg_index")
            index = index if isinstance(index, int) else 0
            newest = index if newest is None else max(newest, index)
            if cursor is not None and index <= cursor:
                reached = True
                continue
            if cursor is None:
                stamp = parse_time(message.get("date"))
                if stamp is not None and stamp < cutoff:
                    reached = True
                    continue
            found = message_candidate(message, dialog, role, config)
            if found:
                out.candidates.append(found)
        if reached or len(page) < HISTORY_PAGE:
            break
        offset += len(page)
    if newest is not None:
        out.positions[key] = max(newest, cursor or 0)
    elif cursor is None:
        out.positions[key] = max(total - offset, 0)


async def collect(
    reader: Reader,
    positions: dict[str, int],
    stamps: dict[str, datetime],
    config: RequestConfig,
    now: datetime,
) -> Collected:
    """پیام‌ها و کارت‌های تازه از آخرین نشانه. بار اول فقط به اندازهٔ lookback_days به عقب نگاه می‌کند."""
    out = Collected()
    if config.dialogs:
        dialogs = tracked(_dialog_rows(await reader.call("chat/getDialogs", {})), config.dialogs)
        out.dialogs = len(dialogs)
        for dialog, role in dialogs:
            await _read_dialog(reader, dialog, role, positions.get(f"dialog:{_id(dialog)}"), config, now, out)
    if config.task_boards:
        since = stamps.get("tasks") or now - timedelta(days=config.lookback_days)
        newest = since
        for task in _tasks(await reader.call("tasks/getAll", {})):
            found = task_candidate(task, config, since)
            if found:
                out.candidates.append(found)
                newest = max(newest, found.happened_at or newest)
        out.stamps["tasks"] = newest
        out.tasks_checked = True
    return out


# ---------------------------------------------------------------- پایگاه داده


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=45)


def digest(kind: str, text: str) -> str:
    return hashlib.sha1(f"{kind}|{fold(text)}".encode(), usedforsecurity=False).hexdigest()


async def _cursors(db: AsyncSession, organization_id: UUID) -> dict[str, PmMizitoCursor]:
    rows = (await db.scalars(select(PmMizitoCursor).where(PmMizitoCursor.organization_id == organization_id))).all()
    return {row.source_key: row for row in rows}


async def save_candidates(
    db: AsyncSession, organization_id: UUID, candidates: list[Candidate], config: RequestConfig
) -> int:
    """یکتا با source_key. متن تکراری (همان نوع و همان متن) با وضعیت duplicate ثبت می‌شود."""
    if not candidates:
        return 0
    keys = [item.source_key[:160] for item in candidates]
    known = set(
        (
            await db.scalars(
                select(PmMizitoRequest.source_key).where(
                    PmMizitoRequest.organization_id == organization_id, PmMizitoRequest.source_key.in_(keys)
                )
            )
        ).all()
    )
    digests = set(
        (
            await db.scalars(select(PmMizitoRequest.digest).where(PmMizitoRequest.organization_id == organization_id))
        ).all()
    )
    added = 0
    ordered = sorted(candidates, key=lambda item: item.happened_at or datetime.min.replace(tzinfo=UTC))
    for item in ordered:
        key = item.source_key[:160]
        if key in known:
            continue
        known.add(key)
        fields = extract(item.text, title=item.title, notes=item.notes, config=config)
        mark = digest(item.kind, item.text)
        db.add(
            PmMizitoRequest(
                organization_id=organization_id,
                source_key=key,
                source_kind=item.source_kind,
                source_id=item.source_id[:64],
                source_title=item.source_title[:120],
                msg_index=item.msg_index,
                kind=item.kind,
                status="duplicate" if mark in digests else "new",
                fields=json.dumps(fields, ensure_ascii=False),
                excerpt=clean_text(item.text)[:EXCERPT_CHARS],
                digest=mark,
                author_id=item.author[:64],
                happened_at=item.happened_at,
            )
        )
        digests.add(mark)
        added += 1
    return added


async def check_requests(
    db: AsyncSession,
    organization_id: UUID,
    *,
    config: RequestConfig | None = None,
    now: datetime | None = None,
) -> dict:
    """«بررسی دوباره»: فقط خواندن از میزیتو، پیش‌نویس‌ها و نشانه‌ها در پنل."""
    from app.perf.services.connections import mizito_token_for

    config = config or RequestConfig.from_settings()
    now = now or utc_now()
    token = await mizito_token_for(db, organization_id)
    if not token:
        return {"checked": False, "reason": "توکن میزیتو تنظیم نشده است", "added": 0}
    if not config.dialogs and not config.task_boards:
        return {"checked": False, "reason": "هیچ گفتگو یا بردی برای پیگیری تنظیم نشده است", "added": 0}
    saved = await _cursors(db, organization_id)
    positions = {key: row.position for key, row in saved.items() if row.position is not None}
    stamps = {key: parse_time(iso(row.stamp)) for key, row in saved.items() if row.stamp is not None}
    await db.commit()  # قفل نوشتن SQLite حین انتظار شبکه نگه داشته نشود
    try:
        async with _client() as client:
            reader = Reader(client, get_settings().perf_mizito_base, token)
            found = await collect(reader, positions, {k: v for k, v in stamps.items() if v}, config, now)
    except httpx.HTTPError as exc:
        return {"checked": False, "reason": f"میزیتو خوانده نشد: {type(exc).__name__}", "added": 0}
    except (PerfError, ValueError) as exc:
        return {"checked": False, "reason": str(exc), "added": 0}
    added = await save_candidates(db, organization_id, found.candidates, config)
    for key, value in [*found.positions.items(), *found.stamps.items()]:
        row = saved.get(key)
        if row is None:
            row = PmMizitoCursor(organization_id=organization_id, source_key=key)
            db.add(row)
            saved[key] = row
        if isinstance(value, datetime):
            row.stamp = value
        else:
            row.position = value
        row.updated_at = now
    await db.flush()
    return {
        "checked": True,
        "reason": "",
        "added": added,
        "found": len(found.candidates),
        "dialogs": found.dialogs,
        "pages": found.pages,
        "tasks_checked": found.tasks_checked,
        "checked_at": iso(now),
    }


def _fields(row: PmMizitoRequest) -> dict:
    try:
        data = json.loads(row.fields or "{}")
    except json.JSONDecodeError:
        data = {}
    return data if isinstance(data, dict) else {}


def _brief(row: PmCampaign | None) -> dict | None:
    if row is None:
        return None
    return {"id": str(row.id), "code": row.code, "title": row.title, "status": row.status}


def request_out(row: PmMizitoRequest, campaigns: dict[str, PmCampaign], by_id: dict[UUID, PmCampaign]) -> dict:
    fields = _fields(row)
    code = code_key(str(fields.get("code") or ""))
    return {
        "id": str(row.id),
        "kind": row.kind,
        "status": row.status,
        "source_kind": row.source_kind,
        "source_title": row.source_title,
        "msg_index": row.msg_index,
        "happened_at": iso(row.happened_at),
        "created_at": iso(row.created_at),
        "decided_at": iso(row.decided_at),
        "fields": fields,
        "excerpt": row.excerpt,
        "suggested": suggest(fields, row.kind),
        "campaign": _brief(by_id.get(row.campaign_id)) if row.campaign_id else None,
        "matched_campaign": _brief(campaigns.get(code)) if code else None,
    }


async def list_requests(db: AsyncSession, organization_id: UUID, status: str = "new") -> dict:
    query = select(PmMizitoRequest).where(PmMizitoRequest.organization_id == organization_id)
    if status == "new":
        query = query.where(PmMizitoRequest.status.in_(OPEN_STATUSES))
    elif status in STATUSES:
        query = query.where(PmMizitoRequest.status == status)
    rows = (
        await db.scalars(query.order_by(PmMizitoRequest.happened_at.desc(), PmMizitoRequest.created_at.desc()))
    ).all()[:_LIST_LIMIT]
    campaigns = (await db.scalars(select(PmCampaign).where(PmCampaign.organization_id == organization_id))).all()
    by_code = {code_key(row.code): row for row in campaigns}
    by_id = {row.id: row for row in campaigns}
    counted = (
        await db.execute(
            select(PmMizitoRequest.status, func.count())
            .where(PmMizitoRequest.organization_id == organization_id)
            .group_by(PmMizitoRequest.status)
        )
    ).all()
    checked = await db.scalar(
        select(func.max(PmMizitoCursor.updated_at)).where(PmMizitoCursor.organization_id == organization_id)
    )
    return {
        "requests": [request_out(row, by_code, by_id) for row in rows],
        "counts": {name: 0 for name in STATUSES} | {name: int(count) for name, count in counted},
        "checked_at": iso(checked),
    }


async def get_request(db: AsyncSession, organization_id: UUID, request_id: UUID) -> PmMizitoRequest | None:
    return await db.scalar(
        select(PmMizitoRequest).where(
            PmMizitoRequest.organization_id == organization_id, PmMizitoRequest.id == request_id
        )
    )


async def one_out(db: AsyncSession, row: PmMizitoRequest) -> dict:
    campaigns = (await db.scalars(select(PmCampaign).where(PmCampaign.organization_id == row.organization_id))).all()
    return request_out(row, {code_key(item.code): item for item in campaigns}, {item.id: item for item in campaigns})
