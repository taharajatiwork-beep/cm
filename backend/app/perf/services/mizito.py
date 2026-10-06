"""خواندن میزیتو. بدون توکن هیچ تماسی زده نمی‌شود و چیزی نوشته نمی‌شود."""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.perf.models import PmIntegration
from app.perf.services.common import PerfError, iso, now

_CODE = re.compile(r"\b([A-Z]{1,3}\d{1,3}(?:-\d+)?)\b")
_PROJECTS = ("پرفورمنس", "کمپین", "مالی")
_QUIET = ("پرداخت شده", "کنسل", "انجام شد", "قوانین", "اطلاعیه", "روش")


def wanted_project(title: str) -> bool:
    text = title or ""
    return any(name in text for name in _PROJECTS)


def _id(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("_id") or value.get("id") or "")
    return str(value or "")


def _boards(project: dict) -> dict[str, str]:
    raw = project.get("kanban_boards") or project.get("boards") or []
    found: dict[str, str] = {}
    if isinstance(raw, dict):
        raw = raw.values()
    if not isinstance(raw, list):
        return found
    for item in raw:
        if not isinstance(item, dict):
            continue
        found[_id(item)] = str(item.get("title") or item.get("name") or "")
    return found


def _tasks(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("tasks", "items", "list"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [item for item in rows if isinstance(item, dict)]
    return []


def _projects(payload: Any) -> list[dict]:
    if isinstance(payload, dict):
        rows = payload.get("projects")
        if isinstance(rows, list):
            return [item for item in rows if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def campaign_code(title: str) -> str:
    match = _CODE.search(title or "")
    return match.group(1) if match else ""


def read_cards(projects_payload: Any, tasks_payload: Any) -> dict:
    """کارت‌های بازِ سه پروژهٔ مارکتینگ را از پاسخ میزیتو جدا می‌کند."""
    projects = [row for row in _projects(projects_payload) if wanted_project(str(row.get("title") or ""))]
    by_id = {_id(row): row for row in projects}
    boards = {pid: _boards(row) for pid, row in by_id.items()}
    cards = []
    for task in _tasks(tasks_payload):
        project_id = _id(task.get("project"))
        project = by_id.get(project_id)
        if project is None or task.get("deleted") or task.get("completed"):
            continue
        board_id = _id(task.get("kanban_board") or task.get("board"))
        board = boards.get(project_id, {}).get(board_id, "")
        if any(part in board for part in _QUIET):
            continue
        title = str(task.get("title") or "")
        cards.append(
            {
                "project": str(project.get("title") or ""),
                "board": board,
                "title": title,
                "code": campaign_code(title),
            }
        )
    cards.sort(key=lambda row: (row["project"], row["board"], row["title"]))
    return {
        "projects": [{"title": str(row.get("title") or ""), "id": _id(row)} for row in projects],
        "cards": cards[:80],
        "open_count": len(cards),
    }


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and "status" in payload and "data" in payload:
        status = payload.get("status")
        if status not in (1, True, "1"):
            raise PerfError(str(payload.get("msg") or "میزیتو پاسخ نداد"))
        return payload.get("data")
    return payload


async def mizito_snapshot(token: str | None = None) -> dict:
    settings = get_settings()
    token = settings.perf_mizito_token.strip() if token is None else token.strip()
    if not token:
        return {
            "connected": False,
            "reason": "توکن میزیتو تنظیم نشده است",
            "projects": [],
            "cards": [],
            "open_count": 0,
        }
    base = settings.perf_mizito_base.rstrip("/")
    headers = {"x-token": token, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            projects = await client.post(f"{base}/api/projects/getList", headers=headers, json={})
            projects.raise_for_status()
            tasks = await client.post(f"{base}/api/tasks/getAll", headers=headers, json={})
            tasks.raise_for_status()
    except httpx.HTTPError as exc:
        return {
            "connected": False,
            "reason": f"میزیتو خوانده نشد: {exc}",
            "projects": [],
            "cards": [],
            "open_count": 0,
        }
    try:
        parsed = read_cards(_unwrap(projects.json()), _unwrap(tasks.json()))
    except (PerfError, ValueError) as exc:
        return {
            "connected": False,
            "reason": str(exc),
            "projects": [],
            "cards": [],
            "open_count": 0,
        }
    return {"connected": True, "reason": "", **parsed}


_EMPTY = {
    "connected": False,
    "reason": "هنوز از میزیتو خوانده نشده است",
    "projects": [],
    "cards": [],
    "open_count": 0,
    "read_at": None,
}


async def saved_mizito(db: AsyncSession, organization_id: UUID) -> dict:
    row = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
    raw = (row.mizito_snapshot if row else "").strip()
    if not raw:
        return dict(_EMPTY)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return dict(_EMPTY)
    if not isinstance(data, dict):
        return dict(_EMPTY)
    data["read_at"] = iso(row.mizito_read_at) if row and row.mizito_read_at else None
    return data


async def refresh_mizito(db: AsyncSession, organization_id: UUID) -> dict:
    from app.perf.services.connections import mizito_token_for

    fresh = await mizito_snapshot(await mizito_token_for(db, organization_id))
    if not fresh.get("connected"):
        previous = await saved_mizito(db, organization_id)
        fresh["read_at"] = previous.get("read_at")
        return fresh
    row = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
    if row is None:
        row = PmIntegration(organization_id=organization_id)
        db.add(row)
    payload = {
        "connected": True,
        "reason": "",
        "projects": fresh["projects"],
        "cards": fresh["cards"],
        "open_count": fresh["open_count"],
    }
    row.mizito_snapshot = json.dumps(payload, ensure_ascii=False)
    row.mizito_read_at = now()
    await db.flush()
    payload["read_at"] = iso(row.mizito_read_at)
    return payload
