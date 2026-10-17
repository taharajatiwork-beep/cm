"""نوین‌هاب: فقط GET — برای بررسی اتصال و بعداً همگام‌سازی."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.perf.models import PmIntegration
from app.perf.services.common import iso, now


def _offline(reason: str) -> dict:
    return {"probed_ok": False, "probe_reason": reason, "probed_at": None, "account_count": 0}


def _list_items(body: Any) -> list:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("data", "accounts", "items", "result"):
            val = body.get(key)
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                for inner in ("data", "accounts", "items"):
                    nested = val.get(inner)
                    if isinstance(nested, list):
                        return nested
    return []


def _account_row(item: dict) -> dict:
    login_required = item.get("login_required")
    if login_required in (1, "1", True):
        needs_login = True
    elif login_required in (0, "0", False):
        needs_login = False
    else:
        needs_login = bool(login_required) if login_required is not None else False
    can_direct = item.get("can_send_direct")
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or item.get("username") or "—"),
        "type": str(item.get("type") or ""),
        "login_required": needs_login,
        "automation_status": str(item.get("automation_status") or ""),
        "can_send_direct": bool(can_direct) if can_direct is not None else None,
    }


def _http_reason(status: int) -> str:
    if status == 401:
        return "توکن نوین‌هاب پذیرفته نشد (۴۰۱). توکن منقضی یا اشتباه است."
    if status == 429:
        return "نوین‌هاب محدودیت نرخ (۴۲۹) گذاشت. کمی بعد دوباره بررسی کنید."
    return f"نوین‌هاب پاسخ {status} داد."


async def saved_novinhub(db: AsyncSession, organization_id: UUID) -> dict:
    row = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
    raw = (row.novinhub_snapshot if row else "") or ""
    if not raw.strip():
        return _offline("هنوز نوین‌هاب بررسی نشده است.")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return _offline("وضعیت ذخیره‌شدهٔ نوین‌هاب خوانا نیست.")
    if not isinstance(parsed, dict):
        return _offline("وضعیت ذخیره‌شدهٔ نوین‌هاب خوانا نیست.")
    return parsed


async def probe_novinhub(db: AsyncSession, organization_id: UUID) -> dict:
    from app.perf.services.connections import novinhub_token_for

    token = await novinhub_token_for(db, organization_id)
    if not token:
        return {"ok": False, "reason": "توکن نوین‌هاب ذخیره نشده است.", "at": None}
    settings = get_settings()
    base = settings.perf_novinhub_api_base.rstrip("/")
    ok = False
    reason = ""
    account_count = 0
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{base}/account",
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code == 200:
            items = _list_items(response.json())
            account_count = len(items)
            ok = True
        else:
            reason = _http_reason(response.status_code)
    except httpx.HTTPError as exc:
        reason = f"به نوین‌هاب وصل نشدیم: {str(exc)[:200]}"
    except (ValueError, TypeError, KeyError) as exc:
        reason = f"پاسخ نوین‌هاب خوانا نبود: {str(exc)[:200]}"
    if token and token in reason:
        reason = reason.replace(token, "…")

    row = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
    if row is None:
        row = PmIntegration(organization_id=organization_id)
        db.add(row)
    stored: dict | None = None
    if (row.novinhub_snapshot or "").strip():
        try:
            parsed = json.loads(row.novinhub_snapshot)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            stored = parsed
    if stored is None:
        stored = _offline("هنوز نوین‌هاب بررسی نشده است.")
    stamped = iso(now())
    stored["probed_ok"] = ok
    stored["probe_reason"] = reason
    stored["probed_at"] = stamped
    stored["account_count"] = account_count
    if not ok:
        stored["last_error"] = reason
        stored["last_error_at"] = stamped
    else:
        stored.pop("last_error", None)
        stored.pop("last_error_at", None)
    row.novinhub_snapshot = json.dumps(stored, ensure_ascii=False)
    await db.flush()
    return {"ok": ok, "reason": reason, "at": stamped, "account_count": account_count}


async def read_novinhub(db: AsyncSession, organization_id: UUID) -> dict:
    from app.perf.services.connections import novinhub_token_for

    token = await novinhub_token_for(db, organization_id)
    if not token:
        return {"connected": False, "reason": "توکن نوین‌هاب ذخیره نشده است.", "accounts": []}
    settings = get_settings()
    base = settings.perf_novinhub_api_base.rstrip("/")
    accounts: list[dict] = []
    reason = ""
    connected = False
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{base}/account",
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code != 200:
            reason = _http_reason(response.status_code)
        else:
            for item in _list_items(response.json()):
                if isinstance(item, dict):
                    accounts.append(_account_row(item))
            connected = True
    except httpx.HTTPError as exc:
        reason = f"به نوین‌هاب وصل نشدیم: {str(exc)[:200]}"
    except (ValueError, TypeError) as exc:
        reason = f"پاسخ نوین‌هاب خوانا نبود: {str(exc)[:200]}"
    if token and token in reason:
        reason = reason.replace(token, "…")
    if not connected and not reason:
        reason = "نوین‌هاب جواب نداد."
    return {"connected": connected, "reason": reason, "accounts": accounts}


async def _nh_get(
    client: httpx.AsyncClient,
    base: str,
    token: str,
    path: str,
    params: dict | None = None,
) -> httpx.Response:
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    return await client.get(url, headers={"Authorization": f"Bearer {token}"}, params=params or {})


def _cursor_items(body: Any) -> tuple[list, int | None]:
    if isinstance(body, dict):
        paging = body.get("paging")
        total = paging.get("total") if isinstance(paging, dict) else None
        data = body.get("data")
        if isinstance(data, list):
            return data, int(total) if total is not None else None
    return _list_items(body), None


def _comment_row(item: dict) -> dict:
    account = item.get("account") if isinstance(item.get("account"), dict) else {}
    return {
        "id": str(item.get("id") or ""),
        "text": str(item.get("text") or "")[:240],
        "date": str(item.get("date") or ""),
        "account_id": str(item.get("account_id") or account.get("id") or ""),
        "account_name": str(account.get("name") or ""),
        "status": item.get("status"),
        "social": str(item.get("social") or ""),
    }


def _conversation_row(item: dict) -> dict:
    account = item.get("account") if isinstance(item.get("account"), dict) else {}
    return {
        "id": str(item.get("id") or ""),
        "last_message": str(item.get("last_message") or "")[:240],
        "update_date": str(item.get("update_date") or ""),
        "account_id": str(item.get("account_id") or account.get("id") or ""),
        "account_name": str(account.get("name") or ""),
        "status": item.get("status"),
    }


async def list_novinhub_comments(
    db: AsyncSession,
    organization_id: UUID,
    *,
    status: str | None = None,
    limit: int = 30,
) -> dict:
    from app.perf.services.connections import novinhub_token_for

    token = await novinhub_token_for(db, organization_id)
    if not token:
        return {"ok": False, "reason": "توکن نوین‌هاب ذخیره نشده است.", "items": [], "total": None}
    settings = get_settings()
    base = settings.perf_novinhub_api_base.rstrip("/")
    params: dict[str, str | int] = {"with": "account", "limit": max(1, min(limit, 50))}
    if status:
        params["status"] = status
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await _nh_get(client, base, token, "/comment", params)
        if response.status_code != 200:
            return {"ok": False, "reason": _http_reason(response.status_code), "items": [], "total": None}
        raw, total = _cursor_items(response.json())
        items = [_comment_row(row) for row in raw if isinstance(row, dict)]
        return {"ok": True, "reason": "", "items": items, "total": total}
    except httpx.HTTPError as exc:
        return {"ok": False, "reason": f"به نوین‌هاب وصل نشدیم: {str(exc)[:200]}", "items": [], "total": None}


async def list_novinhub_conversations(
    db: AsyncSession,
    organization_id: UUID,
    *,
    status: str | None = None,
    limit: int = 30,
) -> dict:
    from app.perf.services.connections import novinhub_token_for

    token = await novinhub_token_for(db, organization_id)
    if not token:
        return {"ok": False, "reason": "توکن نوین‌هاب ذخیره نشده است.", "items": [], "total": None}
    settings = get_settings()
    base = settings.perf_novinhub_api_base.rstrip("/")
    params: dict[str, str | int] = {"with": "account", "limit": max(1, min(limit, 50))}
    if status:
        params["status"] = status
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await _nh_get(client, base, token, "/conversation", params)
        if response.status_code != 200:
            return {"ok": False, "reason": _http_reason(response.status_code), "items": [], "total": None}
        raw, total = _cursor_items(response.json())
        items = [_conversation_row(row) for row in raw if isinstance(row, dict)]
        return {"ok": True, "reason": "", "items": items, "total": total}
    except httpx.HTTPError as exc:
        return {"ok": False, "reason": f"به نوین‌هاب وصل نشدیم: {str(exc)[:200]}", "items": [], "total": None}


async def novinhub_automation_summary(db: AsyncSession, organization_id: UUID) -> dict:
    comments = await list_novinhub_comments(db, organization_id, limit=15)
    conversations = await list_novinhub_conversations(db, organization_id, limit=15)
    return {
        "comments": comments,
        "conversations": conversations,
        "fetched_at": iso(now()),
    }
