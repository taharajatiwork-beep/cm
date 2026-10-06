"""وضعیت اتصال‌ها. توکن میزیتو از پنل ذخیره می‌شود و در پاسخ برنمی‌گردد."""

from __future__ import annotations

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


async def _sheet(client: httpx.AsyncClient, token: str, sheet_id: str) -> dict:
    if not sheet_id:
        return {"configured": False, "connected": False, "title": "", "reason": "شناسه تنظیم نشده است"}
    response = await client.get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}",
        headers={"Authorization": f"Bearer {token}"},
        params={"fields": "properties.title"},
    )
    if response.status_code != 200:
        return {"configured": True, "connected": False, "title": "", "reason": "شیت باز نشد"}
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
    checked: dict[str, dict] = {
        key: {"configured": bool(value), "connected": False, "title": "", "reason": ""}
        for key, value in books.items()
    }
    if live and creds and any(books.values()):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                access = await _access_token(client, creds)
                for key, sheet_id in books.items():
                    checked[key] = await _sheet(client, access, sheet_id)
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            for item in checked.values():
                if item["configured"] and not item["connected"]:
                    item["reason"] = f"بررسی نشد: {exc}"
    token = await mizito_token_for(db, organization_id)
    panels = list(
        (await db.scalars(select(PmPanel).where(PmPanel.organization_id == organization_id))).all()
    )
    return {
        "sheets_ready": sheets_ready,
        "service_account": email,
        "sheets": checked,
        "mizito": {"saved": bool(token), "hint": _mask(token)},
        "panels": [
            {
                "name": row.name,
                "code": row.code,
                "ready": bool((row.api_username or "").strip() or (row.api_token or "").strip()),
            }
            for row in panels
        ],
        "insight": {"ready": bool(settings.llm_api_key.strip()), "provider": settings.llm_provider},
    }
