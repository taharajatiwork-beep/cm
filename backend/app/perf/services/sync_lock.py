"""قفل همگام‌سازی شیت تا دو نفر هم‌زمان ننویسند."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.perf.models import PerfSyncState


class SyncBusy(Exception):
    def __init__(self, name: str) -> None:
        self.name = name or "یک همکار"


async def begin_sync(db: AsyncSession, organization_id: UUID, user_id: UUID, name: str) -> None:
    row = await db.get(PerfSyncState, organization_id)
    if row and row.running:
        raise SyncBusy(row.actor_name)
    if row is None:
        row = PerfSyncState(organization_id=organization_id)
        db.add(row)
    row.running = True
    row.started_by = user_id
    row.actor_name = name
    row.started_at = datetime.now(UTC)
    row.error = ""
    row.result = "running"
    await db.flush()


async def finish_sync(db: AsyncSession, organization_id: UUID, *, ok: bool, error: str = "") -> None:
    row = await db.get(PerfSyncState, organization_id)
    if row is None:
        return
    row.running = False
    row.finished_at = datetime.now(UTC)
    row.result = "ok" if ok else "error"
    row.error = error[:500]
    await db.flush()


async def sync_status(db: AsyncSession, organization_id: UUID) -> dict:
    row = await db.get(PerfSyncState, organization_id)
    if row is None:
        return {"running": False, "actor_name": "", "started_at": None, "finished_at": None, "result": "", "error": ""}
    return {
        "running": bool(row.running),
        "actor_name": row.actor_name,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "result": row.result,
        "error": row.error,
    }
