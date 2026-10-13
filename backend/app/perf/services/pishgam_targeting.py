"""کلاینت هدف‌گیری پیشگام.

مسیرها یا فقط‌خواندنی‌اند، یا استعلام کلاس با هزینهٔ نامعلوم، یا تغییردهنده.
تغییردهنده بدون approved هرگز به شبکه نمی‌رود. توکن در ممیزی نوشته نمی‌شود.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta
from pathlib import Path
from uuid import UUID

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.field_crypto import decrypt_secret
from app.core.jalali import gregorian_to_jalali
from app.perf.models import (
    PmPanel,
    PmPishgamAudit,
    PmPishgamPreview,
    PmRefCity,
    PmRefDeviceBrand,
    PmRefDeviceType,
    PmRefProvince,
)
from app.perf.services.common import PerfError
from app.perf.services.connections import _panel_auth
from app.db.session import WorkerSessionLocal
from app.perf.services.pishgam_polygons import (
    MAX_POLYGONS_PER_CREATE,
    batch_rings,
    edge_lengths_km,
    fragment_count,
    split_ring,
)
from app.perf.sms_rules import check_sms

# method, path, title
_READ: tuple[tuple[str, str, str], ...] = (
    ("GET", "/Messages/GetCredit", "موجودی"),
    ("GET", "/Messages/PrivateNumberList", "خطوط"),
    ("GET", "/Messages/GetIp", "آی‌پی درخواست"),
    ("GET", "/Messages/GetIpCreditPrivateNumberPhonebook", "آی‌پی، خط، دفترچه، اعتبار"),
    ("GET", "/Messages/PhonebookList", "دفترچه تلفن"),
    ("GET", "/Messages/GetVoiceMessageGroups", "گروه‌های صوتی"),
    ("POST", "/Messages/GetDelivery", "وضعیت تحویل"),
    ("POST", "/Messages/GetMultipleSmsDeliveries", "تحویل چندگانه"),
    ("POST", "/Messages/GetMessage", "پیام‌های دریافتی"),
    ("POST", "/Messages/GetVoiceStatus", "وضعیت فایل صوتی"),
    ("GET", "/SmartSms/GetProvinces", "استان‌ها"),
    ("GET", "/SmartSms/GetCities", "شهرها"),
    ("GET", "/SmartSms/GetDeviceTypes", "انواع دستگاه"),
    ("GET", "/SmartSms/GetDeviceBrands", "برند دستگاه"),
    ("GET", "/SmartSms/GetAirports", "فرودگاه‌ها"),
    ("GET", "/SmartSms/GetSmartSmsPrivateNumbersByOperator", "خطوط ارسال هوشمند"),
    ("GET", "/SmartSms/GetCurrentOrganizationSmartSmsRequests", "درخواست‌های هوشمند"),
    ("GET", "/SmartSms/GetCurrentOrganizationSmartSmsCampaigns", "لیست‌های خاکستری"),
    ("GET", "/SmartSms/GetCurrentOrganizationSmartSmsClubs", "باشگاه‌های هوشمند"),
    ("GET", "/SmartSms/GetSmartSmsRequestById", "جزئیات و قیمت درخواست"),
    ("GET", "/SmartSms/GetPeriodicSmartSmsStatistics", "آمار دوره‌ای"),
    ("GET", "/SmartSms/GetSmartSmsRequestDailyStatistics", "آمار روزانه"),
    ("GET", "/SmartSms/GetSmartSmsFinancialStatistics", "هزینهٔ واقعی"),
    ("GET", "/SmartSms/GetSmartSmsCampaignCreateStatus", "وضعیت ساخت لیست خاکستری"),
    ("POST", "/SmartSms/CheckPolygonCells", "اعتبار پالیگان"),
    ("GET", "/SmartClasses/GetSmartClassGroups", "گروه‌های کلاس"),
    ("GET", "/SmartClasses/GetClassesByGroupId", "کلاس‌های یک گروه"),
    ("GET", "/SocialMedia/GetSocialMediaFiles", "فایل‌های شبکه اجتماعی"),
    ("GET", "/SocialMedia/GetSocialMediaPrivateNumbers", "خطوط شبکه اجتماعی"),
)

# ساخت مخاطب و Refresh: تغییر در پنل پیشگام اما بدون هزینهٔ ارسال؛ با approved اجرا می‌شود.
_BUILD: tuple[tuple[str, str, str], ...] = (
    ("POST", "/SmartSms/CreateSimpleSmartSmsRequest", "تعریف مخاطب (رایگان)"),
    ("POST", "/SmartSms/RefreshSmartSmsRequest", "به‌روزرسانی وضعیت درخواست"),
)

# خواندنی، ولی هزینه یا سقف‌شان در مستند نیامده. همگام‌سازی این‌ها را صدا نمی‌زند.
_GATED: tuple[tuple[str, str, str], ...] = (
    ("GET", "/SmartSms/CheckNumberClass", "کلاس یک شماره"),
    ("POST", "/SmartSms/CheckNumbersClass", "کلاس چند شماره"),
    ("GET", "/SmartSms/CheckDeviceClass", "کلاس دستگاه یک شماره"),
    ("POST", "/SmartSms/CheckDevicesClass", "کلاس دستگاه چند شماره"),
    ("POST", "/SmartSms/CheckNumbersAgeType", "سن چند شماره"),
    ("POST", "/SmartClasses/CheckNumbersClass", "کلاس شماره در گروه"),
)

_MUTATING: tuple[tuple[str, str, str], ...] = (
    ("POST", "/Messages/Send", "ارسال پیامک"),
    ("POST", "/Messages/SendOtp", "ارسال رمز"),
    ("POST", "/Messages/SendP2POtpSms", "رمز نظیر به نظیر"),
    ("POST", "/Messages/SendVoice", "پیام صوتی"),
    ("POST", "/Messages/SendVoiceOtp", "رمز صوتی"),
    ("POST", "/Messages/SendVoiceWithText", "صوت از متن"),
    ("POST", "/Messages/AddContact", "افزودن مخاطب"),
    ("POST", "/Messages/CreateVoiceMessageGroup", "گروه صوت"),
    ("POST", "/Messages/UploadVoiceMessage", "آپلود صوت"),
    ("POST", "/SocialMedia/CreateFile", "فایل شبکه اجتماعی"),
    ("DELETE", "/SocialMedia/DeleteFile", "حذف فایل شبکه اجتماعی"),
    ("POST", "/SocialMedia/SendBaleOtp", "رمز بله"),
    ("POST", "/SocialMedia/SendSocialMedia", "ارسال شبکه اجتماعی"),
    ("POST", "/SmartSms/CreatePeriodicSmartSmsRequest", "کمپین دوره‌ای"),
    ("POST", "/SmartSms/CreateWelcomeSmartSmsRequest", "خوش‌آمد"),
    ("POST", "/SmartSms/CreateWelcomeSmartSmsRequestWithCellList", "خوش‌آمد با سلول"),
    ("POST", "/SmartSms/CreateWelcomeCitySmartSmsRequest", "خوش‌آمد شهر"),
    ("POST", "/SmartSms/CreateWelcomeProvinceSmartSmsRequest", "خوش‌آمد استان"),
    ("POST", "/SmartSms/CreateWelcomeAirportSmartSmsRequest", "خوش‌آمد فرودگاه"),
    ("POST", "/SmartSms/CreateWelcomePeriodicSmartSmsRequest", "خوش‌آمد دوره‌ای"),
    ("POST", "/SmartSms/CreateWelcomePeriodicSmartSmsRequestWithCellList", "خوش‌آمد دوره‌ای با سلول"),
    ("POST", "/SmartSms/CreateWelcomeCityPeriodicSmartSmsRequest", "خوش‌آمد دوره‌ای شهر"),
    ("POST", "/SmartSms/CreateWelcomeProvincePeriodicSmartSmsRequest", "خوش‌آمد دوره‌ای استان"),
    ("POST", "/SmartSms/CreateWelcomeAirportPeriodicSmartSmsRequest", "خوش‌آمد دوره‌ای فرودگاه"),
    ("POST", "/SmartSms/CreateClubSmartSmsRequest", "ارسال باشگاه"),
    ("POST", "/SmartSms/CreateClubPeriodicSmartSmsRequest", "باشگاه دوره‌ای"),
    ("POST", "/SmartSms/SendSimpleSmartSms", "ارسال هوشمند"),
    ("POST", "/SmartSms/SendCountPeriodicSmartSms", "ارسال دوره‌ای تعدادی"),
    ("POST", "/SmartSms/SendPercentagePeriodicSmartSms", "ارسال دوره‌ای درصدی"),
    ("PUT", "/SmartSms/UpdateCountPeriodicSmartSms", "ویرایش ارسال تعدادی"),
    ("PUT", "/SmartSms/UpdatePercentagePeriodicSmartSms", "ویرایش ارسال درصدی"),
    ("PUT", "/SmartSms/UpdatePeriodicSmartSmsRequestActivation", "فعال‌سازی دوره‌ای"),
    ("DELETE", "/SmartSms/DeleteSmartSmsRequest", "حذف درخواست هوشمند"),
    ("POST", "/SmartSms/CreateSmartSmsClub", "ساخت باشگاه"),
    ("POST", "/SmartSms/AddNumbersToSmartSmsClub", "افزودن شماره به باشگاه"),
    ("DELETE", "/SmartSms/DeleteSmartSmsClub", "حذف باشگاه"),
    ("POST", "/SmartSms/CreateSmartSmsCampaign", "ساخت لیست خاکستری"),
    ("DELETE", "/SmartSms/DeleteSmartSmsCampaign", "حذف لیست خاکستری"),
    ("POST", "/SmartSms/CreateSmartSmsNumberClasses", "تعریف کلاس شهر"),
    ("POST", "/SmartSms/UpdateSmartSmsNumberClass", "ویرایش کلاس شهر"),
    ("POST", "/SmartSms/CreateOrUpdateSmartSmsDeviceClasses", "تعریف کلاس دستگاه"),
    ("POST", "/SmartClasses/CreateSmartClassGroup", "ساخت گروه کلاس"),
    ("POST", "/SmartClasses/CreateOrUpdateGroupClasses", "ویرایش کلاس‌های گروه"),
    ("DELETE", "/SmartClasses/DeleteSmartClassGroup", "حذف گروه کلاس"),
)

Kind = str  # read | gated | build | mutating | unknown
Fetch = Callable[..., Awaitable[tuple[int, str]]]

_BY_KEY: dict[tuple[str, str], tuple[Kind, str]] = {}
for _kind, _rows in (("read", _READ), ("gated", _GATED), ("build", _BUILD), ("mutating", _MUTATING)):
    for _method, _path, _title in _rows:
        _BY_KEY[(_method, _path)] = (_kind, _title)


def classify(method: str, path: str) -> tuple[Kind, str]:
    clean = path.split("?", 1)[0]
    return _BY_KEY.get((method.upper(), clean), ("unknown", ""))


def catalog() -> dict:
    def pack(rows: tuple[tuple[str, str, str], ...], kind: str) -> list[dict]:
        return [{"method": method, "path": path, "title": title, "kind": kind} for method, path, title in rows]

    return {
        "read": pack(_READ, "read"),
        "gated": pack(_GATED, "gated"),
        "build": pack(_BUILD, "build"),
        "mutating": pack(_MUTATING, "mutating"),
    }


def _areas_path() -> Path:
    return Path(__file__).resolve().parents[4] / "assets" / "target-areas-approx.geojson"


def load_areas() -> list[dict]:
    raw = json.loads(_areas_path().read_text(encoding="utf-8"))
    areas: list[dict] = []
    for feature in raw.get("features") or []:
        props = feature.get("properties") or {}
        rings = ((feature.get("geometry") or {}).get("coordinates") or [[]])[0]
        closed = bool(rings) and rings[0] == rings[-1] and len(rings) >= 4
        width_km, height_km = edge_lengths_km(rings) if closed else (0.0, 0.0)
        areas.append(
            {
                "key": str(props.get("key") or ""),
                "name_fa": str(props.get("name_fa") or ""),
                "tier": str(props.get("tier") or ""),
                "approximate": bool(props.get("approximate", True)),
                "verified": bool(props.get("verified", False)),
                "points": len(rings),
                "closed": closed,
                "fragment_count": fragment_count(rings) if closed else 0,
                "edge_km": {"width": round(width_km, 2), "height": round(height_km, 2)},
                "contact_code": str(props.get("key") or ""),
                "links_allowed": False,
            }
        )
    return areas


def request_hash(method: str, path: str, params: dict | None, payload: object) -> str:
    raw = json.dumps(
        {"method": method.upper(), "path": path, "params": params or {}, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _pishgam_status_error(payload: dict) -> PerfError:
    code = int(payload.get("statusCode") or 0)
    message = str(payload.get("message") or "")
    if code == 62:
        message = "دسترسی سرویس هوشمند روی توکن فعال نیست." + (f" ({message})" if message else "")
    text = f"پیشگام statusCode={code}"
    if message:
        text = f"{text}: {message}"
    return PerfError(text, 422, pishgam_status_code=code, pishgam_message=message)


def _ensure_pishgam_ok(payload: object) -> None:
    if isinstance(payload, dict):
        code = payload.get("statusCode")
        if code not in (None, 0, "0"):
            raise _pishgam_status_error(payload)


def _rows(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        raise PerfError("پاسخ پیشگام قابل خواندن نیست.")
    _ensure_pishgam_ok(payload)
    for key in ("data", "result", "items", "privateNumbers", "checks"):
        value = payload.get(key)
        if isinstance(value, list):
            out: list[dict] = []
            for row in value:
                if isinstance(row, dict):
                    out.append(row)
                elif isinstance(row, str) and row.strip():
                    out.append({"number": row.strip()})
            return out
    raise PerfError("فهرست در پاسخ پیشگام پیدا نشد.")


def _ident(row: dict) -> tuple[int, str] | None:
    raw_id = row.get("id", row.get("Id"))
    name = row.get("name", row.get("Name", row.get("title", "")))
    try:
        return int(raw_id), str(name or "")[:120]
    except (TypeError, ValueError):
        return None


async def fetch_http(method: str, url: str, token: str, params: dict | None, payload: object) -> tuple[int, str]:
    headers = {"Authorization": token}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.request(method, url, headers=headers, params=params, json=payload)
    return response.status_code, response.text


async def _audit(
    db: AsyncSession,
    *,
    organization_id: UUID,
    actor_id: UUID | None,
    method: str,
    path: str,
    is_mutating: bool,
    digest: str,
    status_code: int | None,
) -> None:
    db.add(
        PmPishgamAudit(
            organization_id=organization_id,
            actor_id=actor_id,
            method=method.upper(),
            endpoint=path,
            is_mutating=is_mutating,
            request_hash=digest,
            status_code=status_code,
        )
    )
    await db.flush()


async def execute(
    db: AsyncSession,
    *,
    organization_id: UUID,
    actor_id: UUID | None,
    method: str,
    path: str,
    token: str,
    api_base: str,
    params: dict | None = None,
    payload: object = None,
    approved: bool = False,
    allow_gated: bool = False,
    fetch: Fetch | None = None,
) -> object:
    """یک مسیر فهرست‌شده را صدا می‌زند. مسیر ناشناس یا تغییردهندهٔ بدون تأیید به شبکه نمی‌رود."""
    fetch = fetch or fetch_http
    kind, _title = classify(method, path)
    digest = request_hash(method, path, params, payload)
    mutating = kind == "mutating"
    needs_approval = kind in ("mutating", "build")
    if kind == "unknown" or (needs_approval and not approved) or (kind == "gated" and not allow_gated):
        await _audit(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            method=method,
            path=path.split("?", 1)[0],
            is_mutating=mutating,
            digest=digest,
            status_code=-1,
        )
        if mutating:
            raise PerfError("این مسیر تغییردهنده است و بدون تأیید اجرا نمی‌شود.", 403)
        if kind == "gated":
            raise PerfError("استعلام کلاس هزینهٔ نامعلوم دارد و در این مرحله صدا زده نمی‌شود.", 403)
        raise PerfError("این مسیر در فهرست API پیشگام نیست.", 404)

    if not api_base or not token:
        raise PerfError("آدرس یا توکن پیشگام در تنظیمات نیست.")
    url = api_base.rstrip("/") + path.split("?", 1)[0]
    try:
        status, text = await fetch(method.upper(), url, token, params, payload)
    except httpx.HTTPError as exc:
        await _audit(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            method=method,
            path=path.split("?", 1)[0],
            is_mutating=mutating,
            digest=digest,
            status_code=None,
        )
        raise PerfError("اتصال به پیشگام برقرار نشد.") from exc
    await _audit(
        db,
        organization_id=organization_id,
        actor_id=actor_id,
        method=method,
        path=path.split("?", 1)[0],
        is_mutating=mutating,
        digest=digest,
        status_code=status,
    )
    if status != 200:
        raise PerfError(f"پیشگام پاسخ {status} داد.")
    try:
        return json.loads(text) if text else {}
    except ValueError as exc:
        raise PerfError("پاسخ پیشگام JSON نیست.") from exc


async def credentials(db: AsyncSession, organization_id: UUID) -> tuple[str, str]:
    panel = await db.scalar(
        select(PmPanel).where(PmPanel.organization_id == organization_id, PmPanel.code == "pishgam")
    )
    settings = get_settings()
    if panel is not None:
        base, token = _panel_auth(panel)
    else:
        base, token = settings.pishgam_sms_api_url.strip(), settings.pishgam_sms_token.strip()
    return base, decrypt_secret(token)


async def sync_reference(
    db: AsyncSession,
    *,
    organization_id: UUID,
    actor_id: UUID | None,
    fetch: Fetch | None = None,
) -> dict:
    """استان، شهر، برند و نوع دستگاه را می‌خواند و جایگزین ردیف‌های قبلی همین سازمان می‌کند."""
    fetch = fetch or fetch_http
    base, token = await credentials(db, organization_id)
    common = {
        "organization_id": organization_id,
        "actor_id": actor_id,
        "token": token,
        "api_base": base,
        "fetch": fetch,
    }
    provinces_payload = await execute(db, method="GET", path="/SmartSms/GetProvinces", **common)
    provinces = [item for item in (_ident(row) for row in _rows(provinces_payload)) if item]
    if len(provinces) > 40:
        raise PerfError("تعداد استان‌ها غیرعادی است و شهرها خوانده نشد.")
    cities: list[tuple[int, int, str]] = []
    for province_id, _name in provinces:
        payload = await execute(
            db,
            method="GET",
            path="/SmartSms/GetCities",
            params={"ProvinceId": province_id},
            **common,
        )
        for item in (_ident(row) for row in _rows(payload)):
            if item:
                cities.append((item[0], province_id, item[1]))
    brands_payload = await execute(db, method="GET", path="/SmartSms/GetDeviceBrands", **common)
    types_payload = await execute(db, method="GET", path="/SmartSms/GetDeviceTypes", **common)
    brands = [item for item in (_ident(row) for row in _rows(brands_payload)) if item]
    types = [item for item in (_ident(row) for row in _rows(types_payload)) if item]

    await db.execute(delete(PmRefCity).where(PmRefCity.organization_id == organization_id))
    await db.execute(delete(PmRefProvince).where(PmRefProvince.organization_id == organization_id))
    await db.execute(delete(PmRefDeviceBrand).where(PmRefDeviceBrand.organization_id == organization_id))
    await db.execute(delete(PmRefDeviceType).where(PmRefDeviceType.organization_id == organization_id))
    for remote_id, name in provinces:
        db.add(PmRefProvince(organization_id=organization_id, remote_id=remote_id, name=name))
    for remote_id, province_id, name in cities:
        db.add(
            PmRefCity(
                organization_id=organization_id,
                remote_id=remote_id,
                province_remote_id=province_id,
                name=name,
            )
        )
    for remote_id, name in brands:
        db.add(PmRefDeviceBrand(organization_id=organization_id, remote_id=remote_id, name=name))
    for remote_id, name in types:
        db.add(PmRefDeviceType(organization_id=organization_id, remote_id=remote_id, name=name))
    await db.flush()
    return {"provinces": len(provinces), "cities": len(cities), "brands": len(brands), "types": len(types)}


async def snapshot(db: AsyncSession, organization_id: UUID) -> dict:
    async def count(model) -> int:
        return int(
            await db.scalar(select(func.count()).select_from(model).where(model.organization_id == organization_id))
            or 0
        )

    audits = list(
        (
            await db.scalars(
                select(PmPishgamAudit)
                .where(PmPishgamAudit.organization_id == organization_id)
                .order_by(PmPishgamAudit.created_at.desc())
                .limit(8)
            )
        ).all()
    )
    return {
        "areas": load_areas(),
        "catalog": {
            "read": len(_READ),
            "gated": len(_GATED),
            "build": len(_BUILD),
            "mutating": len(_MUTATING),
        },
        "refs": {
            "provinces": await count(PmRefProvince),
            "cities": await count(PmRefCity),
            "brands": await count(PmRefDeviceBrand),
            "types": await count(PmRefDeviceType),
        },
        "audit": [
            {
                "method": row.method,
                "endpoint": row.endpoint,
                "is_mutating": row.is_mutating,
                "status_code": row.status_code,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in audits
        ],
        "smart": _smart_meta(),
        "preview": await _load_preview(db, organization_id),
    }


_OPERATORS = {1: "همراه اول", 2: "ایرانسل", 3: "رایتل"}
OPERATOR_TARIFF_RIAL = {1: 504, 2: 403, 3: 304}
SEND_LOCKED_REASON = (
    "ارسال قفل است تا تأیید دستی شما. اولین ارسال واقعی با تعداد کم انجام شود."
)
_LINK_RE = re.compile(r"https?://|www\.", re.I)
_SMART_FAIL = {2, 3, 4}
_SMART_DONE = {0, 7}  # Done و PartOfRequestIsCompleted — GetById معمولاً عدد دارد


def _smart_meta() -> dict:
    return {
        "preview_enabled": True,
        "send_enabled": False,
        "send_reason": SEND_LOCKED_REASON,
        "tariffs_rial": OPERATOR_TARIFF_RIAL,
        "unit_note": "واحد تأیید نشده",
        "limits": {
            "max_polygons_per_request": MAX_POLYGONS_PER_CREATE,
            "max_edge_km": 2,
            "max_send_recipients": 500,
            "max_balance_percent": 25,
        },
    }


def _jalali_stamp(moment: datetime) -> str:
    y, m, d = gregorian_to_jalali(moment.year, moment.month, moment.day)
    return f"{y}/{m:02d}/{d:02d} {moment.hour:02d}:{moment.minute:02d}:{moment.second:02d}"


def default_smart_window() -> tuple[str, str]:
    """بازهٔ ۱۱ ساعته در گذشته؛ ترجیحاً ۲۱ تا ۰۸."""
    now = datetime.now()
    end = datetime.combine(now.date(), time(8, 0, 0))
    if now < end:
        end -= timedelta(days=1)
    start = end - timedelta(hours=11)
    return _jalali_stamp(start), _jalali_stamp(end)


async def _load_preview(db: AsyncSession, organization_id: UUID) -> dict | None:
    row = await db.scalar(select(PmPishgamPreview).where(PmPishgamPreview.organization_id == organization_id))
    if not row or not row.payload:
        return None
    try:
        payload = json.loads(row.payload)
    except ValueError:
        return None
    return _preview_for_client(organization_id, payload)


def _preview_for_client(organization_id: UUID, payload: dict) -> dict:
    """وضعیت گیرکرده بعد از ری‌لود سرور یا قطع تسک را برای UI روشن می‌کند."""
    if _preview_running(payload.get("status")) and organization_id not in _PREVIEW_RUNNING:
        return {
            **payload,
            "status": "error",
            "error": {
                "message": "شمارش نیمه‌کاره ماند (احتمالاً سرور API ری‌استارت شد). «شمارش دوباره» را بزنید.",
            },
        }
    return payload


async def _save_preview(
    db: AsyncSession,
    *,
    organization_id: UUID,
    actor_id: UUID | None,
    payload: dict,
) -> None:
    row = await db.scalar(select(PmPishgamPreview).where(PmPishgamPreview.organization_id == organization_id))
    text = json.dumps(payload, ensure_ascii=False)
    if row is None:
        db.add(PmPishgamPreview(organization_id=organization_id, actor_id=actor_id, payload=text))
    else:
        row.payload = text
        row.actor_id = actor_id
    await db.flush()


def _unique_title(area_key: str, batch_index: int) -> str:
    stem = (area_key or "cm")[:6]
    stamp = datetime.now().strftime("%m%d%H%M")
    suffix = chr(ord("a") + batch_index) if batch_index < 26 else str(batch_index)
    return f"cm-{stem}-{stamp}-{suffix}"[:32]


def _jalali_today() -> str:
    now = datetime.now()
    y, m, d = gregorian_to_jalali(now.year, now.month, now.day)
    return f"{y}/{m:02d}/{d:02d}"


def _expire_still_valid(expire: str | None) -> bool:
    if not expire:
        return True
    exp_date = str(expire).split()[0]
    return exp_date >= _jalali_today()


_PREVIEW_RUNNING: set[UUID] = set()


def _merge_checks(cell_checks: list[list[dict]]) -> list[dict]:
    by_op: dict[int, dict] = {}
    for checks in cell_checks:
        for row in checks:
            operator = int(row["operator"])
            current = by_op.get(operator)
            valid = row["is_valid"] and row["is_valid_area"]
            if current is None:
                by_op[operator] = {**row, "is_valid": valid, "is_valid_area": valid}
            else:
                current["is_valid"] = current["is_valid"] and valid
                current["is_valid_area"] = current["is_valid_area"] and valid
    return list(by_op.values())


def _recipient_rows(result: dict) -> list[dict]:
    rows: list[dict] = []
    for item in result.get("recipients") or []:
        if not isinstance(item, dict):
            continue
        operator = int(item.get("operator") or 0)
        rows.append(
            {
                "id": item.get("id"),
                "operator": operator,
                "operator_name": _OPERATORS.get(operator, str(operator)),
                "count": int(item.get("count") or 0),
                "persian_price": int(item.get("persianPrice") or 0),
                "english_price": int(item.get("englishPrice") or 0),
            }
        )
    return rows


def _merge_recipient_counts(rows: list[dict]) -> list[dict]:
    by_op: dict[int, dict] = {}
    for row in rows:
        operator = int(row["operator"])
        bucket = by_op.setdefault(
            operator,
            {
                "operator": operator,
                "operator_name": row["operator_name"],
                "count": 0,
                "persian_price": int(row.get("persian_price") or 0),
                "english_price": int(row.get("english_price") or 0),
            },
        )
        bucket["count"] += int(row.get("count") or 0)
        if not bucket["persian_price"] and row.get("persian_price"):
            bucket["persian_price"] = int(row["persian_price"])
    return list(by_op.values())


def _estimate_costs(recipients: list[dict], sms_parts: int) -> dict:
    api_total = 0
    tariff_total = 0
    total_count = 0
    lines: list[dict] = []
    for row in recipients:
        count = int(row.get("count") or 0)
        price = int(row.get("persian_price") or 0)
        operator = int(row.get("operator") or 0)
        tariff = OPERATOR_TARIFF_RIAL.get(operator, 0)
        api_one = count * price * sms_parts
        tariff_one = count * tariff * sms_parts
        api_total += api_one
        tariff_total += tariff_one
        total_count += count
        lines.append(
            {
                **row,
                "sms_parts": sms_parts,
                "api_one_part_total": api_one,
                "tariff_one_part_total": tariff_one,
                "tariff_rial": tariff,
            }
        )
    return {
        "lines": lines,
        "total_count": total_count,
        "api_total": api_total,
        "tariff_total": tariff_total,
        "sms_parts": sms_parts,
    }


def selected_polygons(keys: list[str]) -> list[dict]:
    """حلقهٔ بسته‌شدهٔ هر محلهٔ انتخاب‌شده، به ترتیب [lng, lat]."""
    wanted: list[str] = []
    seen: set[str] = set()
    for key in keys:
        text = str(key or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        wanted.append(text)
    if not wanted:
        raise PerfError("محله‌ای انتخاب نشده است.", 422)
    raw = json.loads(_areas_path().read_text(encoding="utf-8"))
    by_key: dict[str, dict] = {}
    for feature in raw.get("features") or []:
        props = feature.get("properties") or {}
        key = str(props.get("key") or "")
        ring = ((feature.get("geometry") or {}).get("coordinates") or [[]])[0]
        closed = bool(ring) and ring[0] == ring[-1] and len(ring) >= 4
        by_key[key] = {
            "key": key,
            "name_fa": str(props.get("name_fa") or ""),
            "verified": bool(props.get("verified", False)),
            "closed": closed,
            "ring": ring,
        }
    missing = [key for key in wanted if key not in by_key]
    if missing:
        raise PerfError("این محله در فایل پلیگان نیست.", 422)
    chosen = [by_key[key] for key in wanted]
    if any(not row["closed"] for row in chosen):
        raise PerfError("پلیگان یکی از محله‌ها بسته نیست.", 422)
    return chosen


def _polygon_checks(payload: object) -> list[dict]:
    checks: list[dict] = []
    for row in _rows(payload):
        try:
            operator = int(row.get("mobileOperator"))
        except (TypeError, ValueError):
            operator = 0
        checks.append(
            {
                "operator": operator,
                "operator_name": _OPERATORS.get(operator, str(row.get("mobileOperator") or "")),
                "is_valid": bool(row.get("isValid")),
                "is_valid_area": bool(row.get("isValidArea")),
            }
        )
    return checks


async def check_polygons(
    db: AsyncSession,
    *,
    organization_id: UUID,
    actor_id: UUID | None,
    keys: list[str],
    operators: list[int] | None = None,
    fetch: Fetch | None = None,
) -> dict:
    """هر تکهٔ پلیگان را با CheckPolygonCells می‌سنجد. چیزی ساخته یا ارسال نمی‌شود."""
    ops = operators or [1, 2]
    areas = selected_polygons(keys)
    base, token = await credentials(db, organization_id)
    results: list[dict] = []
    for area in areas:
        cells = split_ring(area["ring"])
        merged_checks: list[list[dict]] = []
        for cell in cells:
            payload = await execute(
                db,
                organization_id=organization_id,
                actor_id=actor_id,
                method="POST",
                path="/SmartSms/CheckPolygonCells",
                token=token,
                api_base=base,
                payload={"mobileOperators": ops, "polygon": cell},
                fetch=fetch,
            )
            merged_checks.append(_polygon_checks(payload))
        checks = _merge_checks(merged_checks)
        valid = all(row["is_valid"] and row["is_valid_area"] for row in checks)
        results.append(
            {
                "key": area["key"],
                "name_fa": area["name_fa"],
                "verified": area["verified"],
                "fragment_count": len(cells),
                "valid": valid,
                "checks": checks,
            }
        )
    return {"areas": results, "all_valid": all(row["valid"] for row in results)}


async def _poll_smart_done(
    db: AsyncSession,
    *,
    organization_id: UUID,
    actor_id: UUID | None,
    api_base: str,
    token: str,
    request_id: int,
    fetch: Fetch | None,
    on_tick: Callable[[int, int], Awaitable[None]] | None = None,
) -> int:
    for attempt in range(40):
        body = await execute(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            method="POST",
            path="/SmartSms/RefreshSmartSmsRequest",
            token=token,
            api_base=api_base,
            payload={"id": request_id},
            approved=True,
            fetch=fetch,
        )
        if not isinstance(body, dict):
            raise PerfError("پاسخ Refresh نامعتبر است.", 502)
        _ensure_pishgam_ok(body)
        status = body.get("smartSmsRequestStatus")
        if on_tick is not None:
            await on_tick(int(status or -1), attempt)
        if status in _SMART_DONE:
            return int(status)
        if status in _SMART_FAIL:
            raise PerfError(
                f"ساخت مخاطب ناموفق شد (وضعیت {status}).",
                422,
                pishgam_status_code=int(body.get("statusCode") or 0),
                pishgam_message=str(body.get("message") or ""),
            )
        await asyncio.sleep(5)
    raise PerfError("زمان انتظار برای آماده‌شدن مخاطب تمام شد.", 504)


def _preview_cache_key(
    keys: list[str],
    operators: list[int],
    start_dt: str,
    end_dt: str,
    residence_enabled: bool,
) -> str:
    raw = json.dumps(
        {
            "keys": sorted(keys),
            "operators": sorted(operators),
            "start": start_dt,
            "end": end_dt,
            "residence": residence_enabled,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _preview_running(status: str | None) -> bool:
    return status in {"checking", "creating", "waiting", "refreshing"}


def _apply_sms_estimates(payload: dict, sms_parts: int) -> dict:
    recipients = payload.get("recipients") or []
    estimates = _estimate_costs(recipients, sms_parts)
    credit = int(payload.get("credit") or 0)
    affordability: dict[str, int | None] = {}
    for row in estimates["lines"]:
        price = int(row.get("persian_price") or 0) * sms_parts
        if price > 0 and credit > 0:
            affordability[row["operator_name"]] = credit // price
        else:
            affordability[row["operator_name"]] = None
    payload["estimates"] = estimates
    payload["affordability_one_part"] = affordability
    payload["sms_parts"] = sms_parts
    return payload


def _smart_lines_rows(payload: object) -> list[dict]:
    lines: list[dict] = []
    for row in _rows(payload):
        try:
            operator = int(row.get("operator") or row.get("mobileOperator") or 0)
        except (TypeError, ValueError):
            operator = 0
        number = str(row.get("number") or row.get("privateNumber") or row.get("senderNumber") or "")
        lines.append(
            {
                "operator": operator,
                "operator_name": _OPERATORS.get(operator, str(operator)),
                "number": number,
            }
        )
    return lines


async def _run_preview_job(
    organization_id: UUID,
    actor_id: UUID | None,
    body: PreviewAudienceIn,
    fetch: Fetch | None = None,
) -> None:
    fetch = fetch or fetch_http
    try:
        async with WorkerSessionLocal() as db:
            start_dt, end_dt = body.start_datetime, body.end_datetime
            if not start_dt or not end_dt:
                start_dt, end_dt = default_smart_window()
            cache_key = _preview_cache_key(body.keys, body.operators, start_dt, end_dt, body.residence_enabled)
            sms_shape = check_sms(body.sms_body or "لغو11")
            sms_parts = max(int(sms_shape.get("pages") or 1), 1)

            async def touch(extra: dict) -> None:
                row = await _load_preview(db, organization_id) or {}
                merged = {**row, **extra}
                await _save_preview(db, organization_id=organization_id, actor_id=actor_id, payload=merged)
                await db.commit()

            await touch(
                {
                    "status": "checking",
                    "progress": {"phase": "checking", "area_index": 0, "area_total": len(body.keys), "message": "بررسی پلیگان"},
                    "cache_key": cache_key,
                    "keys": body.keys,
                    "operators": body.operators,
                    "window": {"start": start_dt, "end": end_dt},
                    "residence_enabled": body.residence_enabled,
                    "from_cache": False,
                }
            )

            check = await check_polygons(
                db,
                organization_id=organization_id,
                actor_id=actor_id,
                keys=body.keys,
                operators=body.operators,
                fetch=fetch,
            )
            if not check.get("all_valid"):
                await touch(
                    {
                        "status": "error",
                        "error": {"message": "پلیگان همهٔ محله‌های انتخاب‌شده معتبر نیست.", "areas": check.get("areas")},
                        "areas": check.get("areas"),
                    }
                )
                return

            base, token = await credentials(db, organization_id)
            common = {
                "organization_id": organization_id,
                "actor_id": actor_id,
                "token": token,
                "api_base": base,
                "fetch": fetch,
            }
            areas_out: list[dict] = []
            all_requests: list[dict] = []
            all_recipient_rows: list[dict] = []
            polygon_total = 0
            polygon_batches = 0
            check_by_key = {row["key"]: row for row in check.get("areas") or []}

            for area_index, area in enumerate(selected_polygons(body.keys)):
                cells = split_ring(area["ring"])
                polygon_total += len(cells)
                batches = batch_rings(cells)
                polygon_batches += len(batches)
                area_requests: list[dict] = []
                area_recipients: list[dict] = []

                await touch(
                    {
                        "status": "creating",
                        "progress": {
                            "phase": "creating",
                            "area_index": area_index,
                            "area_total": len(body.keys),
                            "area_key": area["key"],
                            "area_name": area["name_fa"],
                            "request_index": 0,
                            "request_total": len(batches),
                            "message": f"ساخت مخاطب {area['name_fa']}",
                        },
                        "areas": areas_out,
                    }
                )

                for batch_index, batch in enumerate(batches):
                    create_payload: dict = {
                        "title": _unique_title(area["key"], batch_index),
                        "operators": body.operators,
                        "polygons": batch,
                        "startDatetime": start_dt,
                        "endDatetime": end_dt,
                    }
                    if body.residence_enabled:
                        create_payload["residenceState"] = 0
                    raw = await execute(
                        db,
                        method="POST",
                        path="/SmartSms/CreateSimpleSmartSmsRequest",
                        approved=True,
                        payload=create_payload,
                        **common,
                    )
                    if not isinstance(raw, dict):
                        raise PerfError("پاسخ Create نامعتبر است.", 502)
                    _ensure_pishgam_ok(raw)
                    request_id = int(raw.get("smartSmsRequestId") or 0)
                    if not request_id:
                        raise PerfError("شناسهٔ درخواست هوشمند برگشت نشد.", 502)

                    progress_base = {
                        "phase": "waiting",
                        "area_index": area_index,
                        "area_total": len(body.keys),
                        "area_key": area["key"],
                        "area_name": area["name_fa"],
                        "request_index": batch_index,
                        "request_total": len(batches),
                        "smart_sms_request_id": request_id,
                        "message": "منتظر آماده‌شدن مخاطب در پیشگام",
                    }

                    async def on_refresh_tick(refresh_status: int, attempt: int) -> None:
                        await touch(
                            {
                                "status": "waiting",
                                "progress": {
                                    **progress_base,
                                    "refresh_status": refresh_status,
                                    "refresh_attempt": attempt + 1,
                                },
                            }
                        )

                    await touch({"status": "waiting", "progress": progress_base})
                    await _poll_smart_done(db, request_id=request_id, on_tick=on_refresh_tick, **common)
                    detail_raw = await execute(
                        db,
                        method="GET",
                        path="/SmartSms/GetSmartSmsRequestById",
                        params={"smartSmsRequestId": request_id},
                        **common,
                    )
                    if not isinstance(detail_raw, dict):
                        raise PerfError("پاسخ GetById نامعتبر است.", 502)
                    _ensure_pishgam_ok(detail_raw)
                    result = detail_raw.get("result") or {}
                    recipients = _recipient_rows(result if isinstance(result, dict) else {})
                    area_recipients.extend(recipients)
                    all_recipient_rows.extend(recipients)
                    req_row = {
                        "key": area["key"],
                        "name_fa": area["name_fa"],
                        "smart_sms_request_id": request_id,
                        "title": create_payload["title"],
                        "polygon_count": len(batch),
                        "expire_date": result.get("expireDate") if isinstance(result, dict) else None,
                        "status": result.get("status") if isinstance(result, dict) else None,
                        "recipients": recipients,
                    }
                    area_requests.append(req_row)
                    all_requests.append(req_row)

                check_row = check_by_key.get(area["key"], {})
                merged_area = _merge_recipient_counts(area_recipients)
                areas_out.append(
                    {
                        "key": area["key"],
                        "name_fa": area["name_fa"],
                        "verified": area["verified"],
                        "fragment_count": len(cells),
                        "valid": check_row.get("valid", True),
                        "checks": check_row.get("checks", []),
                        "requests": area_requests,
                        "recipients": merged_area,
                        "total_count": sum(int(r.get("count") or 0) for r in merged_area),
                    }
                )
                await touch({"areas": areas_out, "requests": all_requests})

            credit_raw = await execute(db, method="GET", path="/Messages/GetCredit", **common)
            credit = int(credit_raw.get("credit") or 0) if isinstance(credit_raw, dict) else 0
            lines_raw = await execute(
                db,
                method="GET",
                path="/SmartSms/GetSmartSmsPrivateNumbersByOperator",
                **common,
            )
            smart_lines = _smart_lines_rows(lines_raw)
            merged = _merge_recipient_counts(all_recipient_rows)
            expire_dates = [r.get("expire_date") for r in all_requests if r.get("expire_date")]
            expire_date = min(expire_dates) if expire_dates else None

            payload = {
                "status": "done",
                "progress": {"phase": "done", "message": "شمارش تمام شد"},
                "cache_key": cache_key,
                "from_cache": False,
                "keys": body.keys,
                "operators": body.operators,
                "window": {"start": start_dt, "end": end_dt},
                "residence_enabled": body.residence_enabled,
                "areas": areas_out,
                "requests": all_requests,
                "recipients": merged,
                "credit": credit,
                "smart_lines": smart_lines,
                "unit_note": "واحد تأیید نشده",
                "polygon_batches": polygon_batches,
                "polygon_total": polygon_total,
                "expire_date": expire_date,
                "counted_at": datetime.now().isoformat(timespec="seconds"),
                "error": None,
            }
            _apply_sms_estimates(payload, sms_parts)
            await _save_preview(db, organization_id=organization_id, actor_id=actor_id, payload=payload)
            await db.commit()
    except PerfError as exc:
        async with WorkerSessionLocal() as db:
            row = await _load_preview(db, organization_id) or {}
            row.update(
                {
                    "status": "error",
                    "error": {
                        "message": str(exc),
                        "pishgam_status_code": getattr(exc, "pishgam_status_code", None),
                        "pishgam_message": getattr(exc, "pishgam_message", None),
                    },
                }
            )
            await _save_preview(db, organization_id=organization_id, actor_id=actor_id, payload=row)
            await db.commit()
    except Exception as exc:
        async with WorkerSessionLocal() as db:
            row = await _load_preview(db, organization_id) or {}
            row.update({"status": "error", "error": {"message": str(exc)}})
            await _save_preview(db, organization_id=organization_id, actor_id=actor_id, payload=row)
            await db.commit()
    finally:
        _PREVIEW_RUNNING.discard(organization_id)


async def preview_audience(
    db: AsyncSession,
    *,
    organization_id: UUID,
    actor_id: UUID | None,
    body: PreviewAudienceIn,
    fetch: Fetch | None = None,
) -> dict:
    """شمارش را در پس‌زمینه شروع می‌کند یا نتیجهٔ کش را برمی‌گرداند. SendSimpleSmartSms صدا زده نمی‌شود."""
    if not body.keys:
        raise PerfError("محله‌ای انتخاب نشده است.", 422)
    if not body.operators:
        raise PerfError("حداقل یک اپراتور انتخاب شود.", 422)
    if _LINK_RE.search(body.sms_body or "") and not body.links_allowed:
        raise PerfError("تا رفع محدودیت لینک، متن نباید آدرس اینترنتی داشته باشد.", 422)

    start_dt, end_dt = body.start_datetime, body.end_datetime
    if not start_dt or not end_dt:
        start_dt, end_dt = default_smart_window()
    cache_key = _preview_cache_key(body.keys, body.operators, start_dt, end_dt, body.residence_enabled)
    sms_shape = check_sms(body.sms_body or "لغو11")
    sms_parts = max(int(sms_shape.get("pages") or 1), 1)

    existing = await _load_preview(db, organization_id)
    if organization_id in _PREVIEW_RUNNING:
        raise PerfError("شمارش مخاطب همین حالا در حال انجام است. چند ثانیه بعد دوباره ببینید.", 409)

    if not body.force_refresh and existing and existing.get("status") == "done" and existing.get("cache_key") == cache_key:
        if _expire_still_valid(existing.get("expire_date")):
            cached = dict(existing)
            cached["from_cache"] = True
            _apply_sms_estimates(cached, sms_parts)
            return {"started": False, "from_cache": True, "preview": cached}

    initial = {
        "status": "checking",
        "progress": {"phase": "checking", "message": "شروع بررسی و شمارش"},
        "cache_key": cache_key,
        "from_cache": False,
        "keys": body.keys,
        "operators": body.operators,
        "window": {"start": start_dt, "end": end_dt},
        "residence_enabled": body.residence_enabled,
        "sms_parts": sms_parts,
    }
    await _save_preview(db, organization_id=organization_id, actor_id=actor_id, payload=initial)
    _PREVIEW_RUNNING.add(organization_id)
    asyncio.create_task(_run_preview_job(organization_id, actor_id, body, fetch))
    return {"started": True, "from_cache": False, "preview": initial}


class AreaKeysIn(BaseModel):
    keys: list[str] = []
    operators: list[int] = Field(default_factory=lambda: [1, 2])


class PreviewAudienceIn(BaseModel):
    keys: list[str] = []
    operators: list[int] = Field(default_factory=lambda: [1, 2])
    residence_enabled: bool = True
    start_datetime: str | None = None
    end_datetime: str | None = None
    sms_body: str = ""
    links_allowed: bool = False
    force_refresh: bool = False
