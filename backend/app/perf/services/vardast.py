"""وردست: فقط GET — بررسی اتصال و نمایش کانال‌ها."""

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
    return {"probed_ok": False, "probe_reason": reason, "probed_at": None, "channel_count": 0}


def _list_items(body: Any) -> list:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("data", "items", "channels", "result"):
            val = body.get(key)
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                for inner in ("data", "items", "channels"):
                    nested = val.get(inner)
                    if isinstance(nested, list):
                        return nested
    return []


def _channel_row(item: dict) -> dict:
    return {
        "id": str(item.get("id") or item.get("channel_id") or ""),
        "name": str(item.get("name") or item.get("title") or item.get("username") or "—"),
        "platform": str(item.get("platform") or item.get("type") or ""),
    }


async def _get(client: httpx.AsyncClient, base: str, path: str, key: str) -> httpx.Response:
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    return await client.get(url, headers={"X-API-Key": key})


def _http_reason(status: int) -> str:
    if status == 401:
        return "کلید API وردست پذیرفته نشد (۴۰۱). کلید منقضی یا اشتباه است."
    if status == 403:
        return "دسترسی رد شد (۴۰۳). کلید Public API را از تنظیمات کانال وردست بگیرید."
    if status == 429:
        return "وردست محدودیت نرخ (۴۲۹) گذاشت. کمی بعد دوباره بررسی کنید."
    return f"وردست پاسخ {status} داد."


async def saved_vardast(db: AsyncSession, organization_id: UUID) -> dict:
    row = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
    raw = (row.vardast_snapshot if row else "") or ""
    if not raw.strip():
        return _offline("هنوز وردست بررسی نشده است.")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return _offline("وضعیت ذخیره‌شدهٔ وردست خوانا نیست.")
    if not isinstance(parsed, dict):
        return _offline("وضعیت ذخیره‌شدهٔ وردست خوانا نیست.")
    return parsed


async def probe_vardast(db: AsyncSession, organization_id: UUID) -> dict:
    from app.perf.services.connections import vardast_token_for

    key = await vardast_token_for(db, organization_id)
    if not key:
        return {"ok": False, "reason": "کلید API وردست ذخیره نشده است.", "at": None}
    settings = get_settings()
    base = settings.perf_vardast_api_base.rstrip("/")
    ok = False
    reason = ""
    channel_count = 0
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await _get(client, base, "/messenger/api/channel/", key)
        if response.status_code == 200:
            body = response.json()
            items = _list_items(body)
            channel_count = len(items)
            ok = True
        else:
            reason = _http_reason(response.status_code)
    except httpx.HTTPError as exc:
        reason = f"به وردست وصل نشدیم: {str(exc)[:200]}"
    except (ValueError, TypeError) as exc:
        reason = f"پاسخ وردست خوانا نبود: {str(exc)[:200]}"
    if key and key in reason:
        reason = reason.replace(key, "…")

    row = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
    if row is None:
        row = PmIntegration(organization_id=organization_id)
        db.add(row)
    stored: dict | None = None
    if (row.vardast_snapshot or "").strip():
        try:
            parsed = json.loads(row.vardast_snapshot)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            stored = parsed
    if stored is None:
        stored = _offline("هنوز وردست بررسی نشده است.")
    stamped = iso(now())
    stored["probed_ok"] = ok
    stored["probe_reason"] = reason
    stored["probed_at"] = stamped
    stored["channel_count"] = channel_count
    if not ok:
        stored["last_error"] = reason
        stored["last_error_at"] = stamped
    else:
        stored.pop("last_error", None)
        stored.pop("last_error_at", None)
    row.vardast_snapshot = json.dumps(stored, ensure_ascii=False)
    await db.flush()
    return {"ok": ok, "reason": reason, "at": stamped, "channel_count": channel_count}


async def read_vardast(db: AsyncSession, organization_id: UUID) -> dict:
    from app.perf.services.connections import vardast_token_for

    key = await vardast_token_for(db, organization_id)
    if not key:
        return {"connected": False, "reason": "کلید API وردست ذخیره نشده است.", "channels": [], "usage": None}
    settings = get_settings()
    base = settings.perf_vardast_api_base.rstrip("/")
    channels: list[dict] = []
    usage: dict | None = None
    reason = ""
    connected = False
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            ch_resp = await _get(client, base, "/messenger/api/channel/", key)
            if ch_resp.status_code != 200:
                reason = _http_reason(ch_resp.status_code)
            else:
                for item in _list_items(ch_resp.json()):
                    if isinstance(item, dict):
                        channels.append(_channel_row(item))
                connected = True
            if connected:
                usage_resp = await _get(client, base, "/payment/get-usage-info/", key)
                if usage_resp.status_code == 200:
                    try:
                        body = usage_resp.json()
                        if isinstance(body, dict):
                            usage = body
                    except ValueError:
                        usage = None
    except httpx.HTTPError as exc:
        reason = f"به وردست وصل نشدیم: {str(exc)[:200]}"
    except (ValueError, TypeError) as exc:
        reason = f"پاسخ وردست خوانا نبود: {str(exc)[:200]}"
    if key and key in reason:
        reason = reason.replace(key, "…")
    if not connected and not reason:
        reason = "وردست جواب نداد."
    return {"connected": connected, "reason": reason, "channels": channels, "usage": usage}
