"""نوین‌هاب: فقط GET — برای بررسی اتصال و بعداً همگام‌سازی."""

from __future__ import annotations

import json
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.perf.models import PmIntegration
from app.perf.services.common import iso, now


def _offline(reason: str) -> dict:
    return {"probed_ok": False, "probe_reason": reason, "probed_at": None, "account_count": 0}


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
            body = response.json()
            items = body if isinstance(body, list) else body.get("data") or body.get("accounts") or []
            if isinstance(items, dict):
                items = items.get("data") or items.get("accounts") or []
            account_count = len(items) if isinstance(items, list) else 0
            ok = True
        elif response.status_code == 401:
            reason = "توکن نوین‌هاب پذیرفته نشد (۴۰۱). توکن منقضی یا اشتباه است."
        elif response.status_code == 429:
            reason = "نوین‌هاب محدودیت نرخ (۴۲۹) گذاشت. کمی بعد دوباره بررسی کنید."
        else:
            reason = f"نوین‌هاب پاسخ {response.status_code} داد."
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
