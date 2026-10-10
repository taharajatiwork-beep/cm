"""وضعیت اتصال‌ها. توکن میزیتو از پنل ذخیره می‌شود و در پاسخ برنمی‌گردد."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.perf.models import PmIntegration, PmPanel
from app.perf.services.common import now
from app.perf.services.sheets import _access_token, _credentials, spreadsheet_id


def _mask(token: str) -> str:
    text = token.strip()
    if len(text) < 8:
        return ""
    return f"…{text[-4:]}"


# قفل ورود آی‌اس‌ام‌اس درون این پردازه نگه داشته می‌شود؛ بعد از ری‌استارت پاک می‌شود.
_ISMS_LOCKED: dict[str, datetime] = {}


async def mizito_token_for(db: AsyncSession, organization_id: UUID) -> str:
    row = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
    saved = (row.mizito_token if row else "").strip()
    if saved:
        return saved
    return get_settings().perf_mizito_token.strip()


async def save_mizito_token(db: AsyncSession, organization_id: UUID, token: str) -> str:
    row = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
    if row is None:
        row = PmIntegration(organization_id=organization_id, mizito_token=token.strip())
        db.add(row)
    else:
        row.mizito_token = token.strip()
    row.updated_at = now()
    await db.flush()
    return _mask(row.mizito_token)


def _mizito_status(token: str, snapshot: dict) -> dict:
    last_error = str(snapshot.get("last_error") or "").strip()
    if not token:
        reason = "توکن میزیتو ذخیره نشده است. بدون x-token هیچ کارتی خوانده نمی‌شود."
        connected = False
    elif snapshot.get("probed_at"):
        connected = bool(snapshot.get("probed_ok"))
        reason = "" if connected else str(snapshot.get("probe_reason") or "میزیتو جواب نداد.")
    elif last_error:
        reason = last_error
        connected = False
    elif snapshot.get("connected"):
        reason = ""
        connected = True
    else:
        reason = str(snapshot.get("reason") or "هنوز از میزیتو خوانده نشده است.")
        connected = False
    return {
        "saved": bool(token),
        "hint": _mask(token),
        "connected": connected,
        "reason": reason,
        "read_at": snapshot.get("read_at"),
        "last_error_at": snapshot.get("last_error_at"),
        "checked_at": snapshot.get("probed_at") or snapshot.get("last_error_at") or snapshot.get("read_at"),
        "open_count": int(snapshot.get("open_count") or 0),
    }


def google_sheet_reason(status: int, body: object) -> str:
    """خطای گوگل را با کد وضعیت و متن خود گوگل برمی‌گرداند. توکن داخلش نیست."""
    message = ""
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "")[:240]
        elif error:
            message = str(error)[:240]
    if status == 401:
        text = "توکن گوگل پذیرفته نشد (۴۰۱). فایل حساب سرویس باطل است یا ساعت سرور اشتباه است."
    elif status == 403:
        text = "دسترسی رد شد (۴۰۳). این شیت با حساب سرویس به اشتراک گذاشته نشده، یا Sheets API در پروژهٔ گوگل خاموش است."
    elif status == 404:
        text = "شیت پیدا نشد (۴۰۴). شناسه اشتباه است یا شیت حذف شده."
    else:
        text = f"شیت باز نشد (کد {status})."
    return f"{text} {message}".strip()


async def _sheet(client: httpx.AsyncClient, token: str, sheet_id: str) -> dict:
    if not sheet_id:
        return {"configured": False, "connected": False, "title": "", "reason": "شناسهٔ این شیت در تنظیم سرور خالی است."}
    response = await client.get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}",
        headers={"Authorization": f"Bearer {token}"},
        params={"fields": "properties.title"},
    )
    if response.status_code != 200:
        try:
            body = response.json()
        except ValueError:
            body = {}
        return {"configured": True, "connected": False, "title": "", "reason": google_sheet_reason(response.status_code, body)}
    title = str(response.json().get("properties", {}).get("title") or "")
    return {"configured": True, "connected": True, "title": title, "reason": ""}


async def connection_status(db: AsyncSession, organization_id: UUID, *, live: bool) -> dict:
    settings = get_settings()
    creds = _credentials()
    email = str(creds.get("client_email") or "") if creds else ""
    sheets_ready = bool(spreadsheet_id(settings.perf_sheets_spreadsheet_id) and creds)
    books = {
        "report": spreadsheet_id(settings.perf_sheets_spreadsheet_id),
        "register": spreadsheet_id(settings.perf_sheets_register_campaign_id),
        "costs": spreadsheet_id(settings.perf_sheets_cost_tracking_id),
        "reporter": spreadsheet_id(settings.perf_sheets_reporter_id),
    }
    if creds:
        idle = "شناسه در تنظیم سرور هست. عنوان شیت خوانده می‌شود و ردیفی نوشته نمی‌شود."
        missing_id = "شناسهٔ این شیت در تنظیم سرور خالی است."
    else:
        idle = "فایل حساب سرویس روی سرور پیدا نشد. بدون آن هیچ شیتی خوانده نمی‌شود."
        missing_id = "فایل حساب سرویس پیدا نشد و شناسهٔ این شیت هم خالی است."
    checked: dict[str, dict] = {
        key: {
            "configured": bool(value) and bool(creds),
            "connected": False,
            "title": "",
            "reason": idle if value else missing_id,
        }
        for key, value in books.items()
    }
    if live and creds and any(books.values()):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                access = await _access_token(client, creds)
                for key, sheet_id in books.items():
                    checked[key] = await _sheet(client, access, sheet_id)
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            detail = str(exc)[:240]
            for item in checked.values():
                if item["configured"] and not item["connected"]:
                    item["reason"] = f"بررسی زنده انجام نشد: {detail}"
    token = await mizito_token_for(db, organization_id)
    from app.perf.services.mizito import probe_mizito, saved_mizito

    if live and token:
        await probe_mizito(db, organization_id)
    snapshot = await saved_mizito(db, organization_id)
    panels = list(
        (await db.scalars(select(PmPanel).where(PmPanel.organization_id == organization_id))).all()
    )
    probeable = [row for row in panels if all(_panel_auth(row))]
    isms_style = [
        row for row in panels
        if row not in probeable and (row.api_username or "").strip() and (row.api_secret or "").strip()
    ]
    panel_live: dict[str, dict] = {}
    if live and probeable:
        async with httpx.AsyncClient(timeout=20) as client:
            for row in probeable:
                panel_live[row.code] = await probe_panel(client, row)
    if live and isms_style:
        async with httpx.AsyncClient(timeout=20) as client:
            for row in isms_style:
                panel_live[row.code] = await probe_isms_credit(client, row)
    return {
        "sheets_ready": sheets_ready,
        "service_account": email,
        "sheets": checked,
        "mizito": _mizito_status(token, snapshot),
        "panels": [
            {
                "id": str(row.id),
                "name": row.name,
                "code": row.code,
                "ready": bool((row.api_username or "").strip() or (row.api_token or "").strip() or (row.api_secret or "").strip()),
                "has_token": bool(_panel_auth(row)[1]),
                "api_base": _panel_auth(row)[0],
                "live": panel_live.get(row.code),
                "detail": (
                    "نام کاربری یا توکن API در پنل ذخیره شده است."
                    if (row.api_username or "").strip() or (row.api_token or "").strip() or (row.api_secret or "").strip()
                    else "نام کاربری، توکن و رمز API هر سه خالی‌اند. ارسال از این پنل انجام نمی‌شود."
                ),
            }
            for row in panels
        ],
        "insight": {"ready": bool(settings.llm_api_key.strip()), "provider": settings.llm_provider},
    }


def _panel_auth(row: PmPanel) -> tuple[str, str]:
    """آدرس و توکن API پنل؛ فقط پنل پیشگامان از تنظیمات سرور fallback می‌گیرد (توکن در .env است)."""
    settings = get_settings()
    if (row.code or "").strip() == "pishgam":
        base = (row.api_base or "").strip() or settings.pishgam_sms_api_url.strip()
        token = (row.api_token or "").strip() or settings.pishgam_sms_token.strip()
        return base, token
    return (row.api_base or "").strip(), (row.api_token or "").strip()


async def probe_panel(client: httpx.AsyncClient, row: PmPanel) -> dict:
    """اعتبار و خطوط پنل پیشگامان با مسیرهای رسمی swagger خوانده می‌شود؛ چیزی نوشته نمی‌شود.

    توکن خام در هدر Authorization می‌رود. کد وضعیت پاسخ: 0 موفق، 34 توکن اشتباه، 35 آی‌پی نامعتبر…
    """
    settings = get_settings()
    base, token = _panel_auth(row)
    try:
        response = await client.get(
            base.rstrip("/") + settings.pishgam_balance_path,
            headers={"Authorization": token},
        )
    except httpx.HTTPError as exc:
        return {"ok": False, "reason": f"کال زنده انجام نشد: {str(exc)[:200]}", "balance": "", "lines": []}
    try:
        data = response.json()
    except ValueError:
        data = {}
    code = int(data.get("statusCode") or 0) if response.status_code == 200 else -1
    if response.status_code != 200 or code != 0:
        reason = f"کد {response.status_code}: {response.text[:150]}" if code < 0 else pishgam_reason(code)
        return {"ok": False, "reason": reason, "balance": "", "lines": []}
    from app.perf.services.reports import fa_num

    credit = int(data.get("credit") or 0)
    lines: list[str] = []
    try:
        lines_response = await client.get(
            base.rstrip("/") + settings.pishgam_lines_path,
            headers={"Authorization": token},
        )
        if lines_response.status_code == 200:
            body = lines_response.json()
            for item in body.get("numbers") or []:
                number = str(item.get("number") or "").strip()
                if number and number not in lines:
                    lines.append(number)
    except (httpx.HTTPError, ValueError):
        lines = []
    # موجودی واقعی پنل در دفتر CM می‌نشیند تا هشدار کمبود موجودی و کارت پنل‌ها درست باشد.
    row.balance_toman = credit // 10
    return {
        "ok": True,
        "reason": "",
        "balance": f"{fa_num(credit)} ریال",
        "credit_rial": credit,
        "lines": lines,
    }


_PISHGAM_CODES = {
    8: "سازمان یافت نشد یا احراز هویت نشده",
    9: "سازمان غیرفعال است",
    10: "سازمان منقضی شده است",
    11: "سازمان جاری یا والدش احراز هویت نشده یا غیرفعال است",
    13: "ارسال کاربر غیرفعال است",
    14: "کاربر منقضی شده است",
    15: "اطلاعات کاربر پیدا نشد یا احراز هویت نشده",
    25: "ناموفق",
    33: "توکن وارد نشده است",
    34: "توکن یافت نشد یا اشتباه است",
    35: "آی‌پی این سرور در پنل ثبت نشده است؛ IP جدید را در پنل پیشگامان ثبت کنید",
    62: "عدم دسترسی",
}


def pishgam_reason(code: int) -> str:
    """کد وضعیت swagger پیشگامان را به جملهٔ فارسی برمی‌گرداند."""
    return _PISHGAM_CODES.get(code) or f"پنل کد {code} برگرداند"


async def probe_isms_credit(client: httpx.AsyncClient, row: PmPanel) -> dict:
    """موجودی آی‌اس‌ام‌اس با creditWS و همان نام کاربری/رمز ارسال خوانده می‌شود؛ فقط خواندن.

    پنل بعد از ۳ ورود ناموفق ۱۰ دقیقه قفل می‌کند (کد 102)؛ تا پایان قفل دوباره کال نمی‌زنیم.
    """
    settings = get_settings()
    key = f"{row.organization_id}:{row.code}"
    until = _ISMS_LOCKED.get(key)
    if until and now() < until:
        return {"ok": False, "reason": f"پنل تا ۱۰ دقیقه قفل شده است ({until:%H:%M}). بعد از اصلاح نام کاربری/رمز دوباره بررسی کنید.", "balance": ""}
    params = {"username": (row.api_username or "").strip(), "password": (row.api_secret or "").strip()}
    try:
        response = await client.get(settings.isms_credit_url, params=params)
    except httpx.HTTPError as exc:
        return {"ok": False, "reason": f"کال زنده انجام نشد: {str(exc)[:200]}", "balance": ""}
    if response.status_code >= 400:
        return {"ok": False, "reason": f"کد {response.status_code}: {response.text[:200]}", "balance": ""}
    try:
        data = response.json()
    except ValueError:
        return {"ok": False, "reason": f"پاسخ نامفهوم: {response.text[:200]}", "balance": ""}
    code = data.get("code")
    if code == 102:
        _ISMS_LOCKED[key] = now() + timedelta(minutes=10)
        return {"ok": False, "reason": f"ورود سه بار ناموفق؛ پنل ۱۰ دقیقه قفل است: {data.get('message') or ''}", "balance": ""}
    if code == 0:
        return {"ok": True, "reason": "", "balance": response.text[:200]}
    return {"ok": False, "reason": f"کد {code}: {data.get('message') or response.text[:150]}", "balance": ""}
