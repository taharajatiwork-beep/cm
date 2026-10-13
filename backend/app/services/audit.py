from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Event


async def emit_event(
    db: AsyncSession,
    *,
    organization_id: UUID,
    event_type: str,
    entity_type: str,
    entity_id: UUID,
    actor_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> Event:
    event = Event(
        organization_id=organization_id,
        event_type=event_type,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=json.dumps(payload) if payload else None,
    )
    db.add(event)
    await db.flush()
    return event


AUDIT_HASH_VERSION = "cm-audit-v1"

# قفل نوشتن زنجیره، به‌ازای هر سازمان.
#
# در Postgres کافی است سطر آخر با FOR UPDATE قفل شود (پایین‌تر همین تابع)،
# ولی SQLite از FOR UPDATE پشتیبانی نمی‌کند و اجازهٔ دو writer هم‌زمان
# می‌دهد — در آن حالت هر دو `chain_seq = N+1` می‌گرفتند و زنجیره می‌شکست.
# این قفل هر دو مسیر را پوشش می‌دهد. در یک پروسه است؛ بین چند worker
# مستقل، FOR UPDATE در Postgres کافی است.
_AUDIT_CHAIN_LOCKS: dict[str, asyncio.Lock] = {}


def _audit_chain_lock(organization_id: UUID) -> asyncio.Lock:
    lock = _AUDIT_CHAIN_LOCKS.get(str(organization_id))
    if lock is None:
        lock = asyncio.Lock()
        _AUDIT_CHAIN_LOCKS[str(organization_id)] = lock
    return lock


def _audit_canonical(row_fields: dict[str, str]) -> str:
    """نمایش قطعی و پایدار از یک سطر لاگ ممیزی (ترتیب ثابت، بدون ابهام)."""
    return "|".join(f"{k}={row_fields[k]}" for k in sorted(row_fields))


def audit_row_hash(fields: dict[str, str], prev_hash: str | None) -> str:
    """SHA-256 روی نمایش قطعی سطر + هش سطر قبلی.

    زنجیره به‌ازای هر سازمان جداست؛ `prev_hash` هش آخرین سطر همان سازمان است.
    تغییر یا حذف هر سطری، هش همهٔ سطرهای بعدی را بی‌اعتبار می‌کند.
    """
    payload = f"{AUDIT_HASH_VERSION}|{prev_hash or ''}|{_audit_canonical(fields)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def audit_hash_fields(row: AuditLog) -> dict[str, str]:
    """همان فیلدهایی که write_audit برای ساخت هش یک سطر استفاده می‌کند."""
    return {
        "id": str(row.id),
        "organization_id": str(row.organization_id),
        "actor_id": str(row.actor_id) if row.actor_id else "",
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": str(row.entity_id),
        "details": row.details or "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "chain_seq": str(row.chain_seq),
    }


async def verify_audit_chain(
    db: AsyncSession, organization_id: UUID
) -> dict[str, Any]:
    """کل زنجیرهٔ هش یک سازمان را بازمحاسبه می‌کند.

    فقط سطرهای هش‌دار بررسی می‌شوند — سطرهای پیش از مهاجرت ۰۰۱۱ تاریخی‌اند
    و زنجیره از اولین سطر هش‌دار شروع می‌شود.

    خروجی: ``{"ok": bool, "rows_checked": int, "broken_at": str|None, "detail": str|None}``
    """
    rows = list(
        (
            await db.execute(
                select(AuditLog)
                .where(
                    AuditLog.organization_id == organization_id,
                    AuditLog.row_hash.isnot(None),
                )
                .order_by(AuditLog.chain_seq)
            )
        ).scalars()
    )
    prev: str | None = None
    expected_seq = 1
    for r in rows:
        if r.chain_seq != expected_seq:
            return {
                "ok": False,
                "rows_checked": len(rows),
                "broken_at": r.action,
                "detail": f"حذف یا درج سطر: chain_seq={r.chain_seq} ولی باید {expected_seq} باشد",
            }
        if (r.prev_hash or None) != prev:
            return {
                "ok": False,
                "rows_checked": len(rows),
                "broken_at": r.action,
                "detail": "prev_hash با سطر قبلی نمی‌خواند (سطری حذف یا جابه‌جا شده)",
            }
        if r.row_hash != audit_row_hash(audit_hash_fields(r), prev):
            return {
                "ok": False,
                "rows_checked": len(rows),
                "broken_at": r.action,
                "detail": "محتوای سطر تغییر کرده (row_hash با داده‌های فعلی نمی‌خواند)",
            }
        prev = r.row_hash
        expected_seq += 1
    return {"ok": True, "rows_checked": len(rows), "broken_at": None, "detail": None}


async def write_audit(
    db: AsyncSession,
    *,
    organization_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID,
    actor_id: UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    # زنجیرهٔ هش: آخرین سطرِ هش‌دار همین سازمان مبنای سطر جدید است.
    # بر اساس chain_seq مرتب می‌کنیم نه created_at، چون دقت created_at در
    # SQLite پایین است و چند سطر پشت‌سرهم می‌توانند زمان یکسان بگیرند.
    #
    # خواندن «آخرین سطر» و نوشتن سطر جدید باید اتمیک باشد، وگرنه دو تراکنش
    # هم‌زمان هر دو chain_seq یکسان می‌گیرند و زنجیره می‌شکند. در Postgres
    # قفل سطر (FOR UPDATE) این را تضمین می‌کند؛ در SQLite پشتیبانی نمی‌شود
    # و دو writer هم‌زمان مجازند، پس آنجا قفل درون‌پروسه‌ای لازم است.
    async with _audit_chain_lock(organization_id):
        return await _write_audit_locked(
            db,
            organization_id=organization_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            details=details,
        )


async def _write_audit_locked(
    db: AsyncSession,
    *,
    organization_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID,
    actor_id: UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """بدنهٔ write_audit — همیشه زیر قفل زنجیره صدا زده می‌شود."""
    with_for_update = db.bind is not None and db.bind.dialect.name == "postgresql"
    last_stmt = (
        select(AuditLog.row_hash, AuditLog.chain_seq)
        .where(AuditLog.organization_id == organization_id, AuditLog.row_hash.isnot(None))
        .order_by(AuditLog.chain_seq.desc())
        .limit(1)
    )
    if with_for_update:
        last_stmt = last_stmt.with_for_update()
    last = (await db.execute(last_stmt)).first()
    prev_hash = last[0] if last else None
    next_seq = (last[1] if last else 0) + 1

    row = AuditLog(
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=json.dumps(details) if details else None,
        prev_hash=prev_hash,
        chain_seq=next_seq,
    )
    db.add(row)
    await db.flush()
    # created_at بعد از flush مقدار می‌گیرد (server_default) → هش را همان‌جا می‌سازیم
    fields = {
        "id": str(row.id),
        "organization_id": str(organization_id),
        "actor_id": str(actor_id) if actor_id else "",
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "details": row.details or "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "chain_seq": str(row.chain_seq),
    }
    row.row_hash = audit_row_hash(fields, prev_hash)
    await db.flush()
    return row

