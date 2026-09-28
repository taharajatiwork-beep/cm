"""DB-backed lock so only one API/worker runs a job at a time."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enterprise import JobLock


async def try_lock(db: AsyncSession, name: str, ttl_seconds: int = 120) -> str | None:
    now = datetime.now(UTC)
    existing = await db.get(JobLock, name)
    if existing and existing.expires_at > now:
        return None
    if existing:
        await db.delete(existing)
        await db.flush()
    owner = uuid4().hex
    db.add(JobLock(name=name, owner=owner, expires_at=now + timedelta(seconds=ttl_seconds)))
    await db.flush()
    return owner


async def release_lock(db: AsyncSession, name: str, owner: str) -> None:
    row = await db.get(JobLock, name)
    if row and row.owner == owner:
        await db.execute(delete(JobLock).where(JobLock.name == name, JobLock.owner == owner))
        await db.flush()
