"""Multi-instance worker coordination with Redis (optional fallback to DB/in-memory).

Functions are factored so they can be wired to a task queue (arq, Celery, etc.) later.
When REDIS_URL is set, uses Redis for:
  - leader election lock (outbox/poll/sla digest)
  - Telegram polling offset persistence
When Redis is absent, falls back to in-memory locks for single-process mode
and DB-backed locks for multi-process mode without Redis.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.locks import release_lock, try_lock
from app.db.session import AsyncSessionLocal

log = get_logger(__name__)

# Redis client (optional)
try:
    import redis.asyncio as redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None  # type: ignore

REDIS_KEY_PREFIX = "cm:worker:"
POLL_OFFSET_KEY = REDIS_KEY_PREFIX + "poll_offset:{provider}"
LEADER_LOCK_KEY = REDIS_KEY_PREFIX + "leader:{job_name}"


# ============================================================
# In-memory fallback locks (for single-process / dev mode)
# ============================================================

class _InMemoryLockManager:
    """Simple in-memory lock manager for dev mode without Redis/DB."""
    
    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}
        self._owners: dict[str, str] = {}
    
    def _get_lock(self, name: str) -> asyncio.Lock:
        if name not in self._locks:
            self._locks[name] = asyncio.Lock()
        return self._locks[name]
    
    async def acquire(self, name: str, owner: str, ttl_seconds: int) -> bool:
        lock = self._get_lock(name)
        # Non-blocking try_acquire
        if lock.locked():
            return False
        await lock.acquire()
        self._owners[name] = owner
        # Auto-release after TTL
        asyncio.create_task(self._auto_release(name, owner, ttl_seconds))
        return True
    
    async def _auto_release(self, name: str, owner: str, ttl_seconds: int):
        await asyncio.sleep(ttl_seconds)
        lock = self._locks.get(name)
        if lock and lock.locked() and self._owners.get(name) == owner:
            lock.release()
            self._owners.pop(name, None)
    
    async def release(self, name: str, owner: str) -> None:
        lock = self._locks.get(name)
        if lock and lock.locked() and self._owners.get(name) == owner:
            lock.release()
            self._owners.pop(name, None)
    
    def is_locked(self, name: str) -> bool:
        lock = self._locks.get(name)
        return lock.locked() if lock else False


# Global in-memory lock manager (process-local)
_in_memory_locks = _InMemoryLockManager()


# ============================================================
# Redis helpers (when available)
# ============================================================

def _get_redis():
    settings = get_settings()
    if redis is not None and settings.redis_url:
        try:
            return redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        except Exception as e:  # pragma: no cover
            log.warning("redis_connect_failed", error=str(e))
    return None


async def _redis_try_lock(job_name: str, ttl_seconds: int) -> bool:
    r = _get_redis()
    if r is None:
        return False
    key = LEADER_LOCK_KEY.format(job_name=job_name)
    try:
        acquired = await r.set(key, "1", nx=True, ex=ttl_seconds)
        return bool(acquired)
    except Exception as e:
        log.warning("leader_lock_error", job=job_name, error=str(e))
        return False


async def _redis_release_lock(job_name: str) -> None:
    r = _get_redis()
    if r is None:
        return
    key = LEADER_LOCK_KEY.format(job_name=job_name)
    try:
        await r.delete(key)
    except Exception:
        pass


async def get_poll_offset(provider: str) -> int:
    r = _get_redis()
    if r is None:
        # Fallback to in-memory (not persistent across restarts)
        return _poll_offsets_memory.get(provider, 0)
    key = POLL_OFFSET_KEY.format(provider=provider)
    try:
        val = await r.get(key)
        return int(val) if val else 0
    except Exception:
        return 0


async def set_poll_offset(provider: str, offset: int) -> None:
    r = _get_redis()
    if r is None:
        _poll_offsets_memory[provider] = offset
        return
    key = POLL_OFFSET_KEY.format(provider=provider)
    try:
        await r.set(key, str(offset))
    except Exception:
        pass


# In-memory poll offsets (fallback when no Redis)
_poll_offsets_memory: dict[str, int] = {}


# ============================================================
# Unified lock acquisition with fallback chain
# ============================================================

async def try_acquire_leader_lock(job_name: str, ttl_seconds: int = 30) -> bool:
    """Attempt to become the leader for a named job.
    Tries Redis first, then in-memory lock.
    Returns True if this instance acquired the lock.
    """
    # 1. Try Redis
    if await _redis_try_lock(job_name, ttl_seconds):
        return True
    
    # 2. Fallback to in-memory lock (single process)
    task = asyncio.current_task()
    task_name = task.get_name() if task else "main"
    owner = f"{os.getpid()}-{task_name}"
    return await _in_memory_locks.acquire(job_name, owner, ttl_seconds)


async def release_leader_lock(job_name: str) -> None:
    # Try Redis
    await _redis_release_lock(job_name)
    # In-memory release (best effort - we don't track owner globally)
    # For simplicity, we release if we hold it
    lock = _in_memory_locks._locks.get(job_name)
    if lock and lock.locked():
        # Can't verify owner in simple impl, but this is dev-mode only
        lock.release()
        _in_memory_locks._owners.pop(job_name, None)


# ============================================================
# DB-backed lock for multi-process without Redis (external worker)
# ============================================================

async def try_acquire_db_lock(job_name: str, ttl_seconds: int = 120) -> str | None:
    """Acquire a DB-backed lock using JobLock table.
    Returns owner token if acquired, None otherwise.
    """
    async with AsyncSessionLocal() as db:
        owner = await try_lock(db, job_name, ttl_seconds)
        await db.commit()
        return owner


async def release_db_lock(job_name: str, owner: str) -> None:
    async with AsyncSessionLocal() as db:
        await release_lock(db, job_name, owner)
        await db.commit()


_job_owners: dict[str, tuple[str, str]] = {}
_redis_state: str | None = None


async def _redis_mode() -> str:
    """ok if Redis answers, down if configured but unreachable, absent if unused."""
    global _redis_state
    if _redis_state:
        return _redis_state
    if redis is None or not get_settings().redis_url:
        _redis_state = "absent"
        return _redis_state
    client = _get_redis()
    if client is None:
        _redis_state = "absent"
        return _redis_state
    try:
        await asyncio.wait_for(client.ping(), timeout=0.3)
        _redis_state = "ok"
    except Exception:
        _redis_state = "down"
    finally:
        try:
            await client.aclose()
        except Exception:
            pass
    return _redis_state


async def acquire_job(name: str, ttl_seconds: int) -> bool:
    """Redis when it answers; otherwise a committed DB JobLock; in-memory last.

    If Redis is configured and reachable, a missed lock means another process
    holds it — do not fall through to a process-local lock.
    """
    mode = await _redis_mode()
    if mode == "ok":
        if await _redis_try_lock(name, ttl_seconds):
            _job_owners[name] = ("redis", "1")
            return True
        return False
    try:
        owner = await asyncio.wait_for(try_acquire_db_lock(name, ttl_seconds), timeout=1.0)
    except Exception:
        owner = None
    if owner:
        _job_owners[name] = ("db", owner)
        return True
    task = asyncio.current_task()
    mem_owner = f"{os.getpid()}-{task.get_name() if task else 'main'}"
    if await _in_memory_locks.acquire(name, mem_owner, ttl_seconds):
        _job_owners[name] = ("memory", mem_owner)
        return True
    return False


async def release_job(name: str) -> None:
    backend, owner = _job_owners.pop(name, ("", ""))
    if backend == "redis":
        await _redis_release_lock(name)
    elif backend == "db" and owner:
        try:
            await release_db_lock(name, owner)
        except Exception:
            log.warning("db_lock_release_failed", name=name)
    elif backend == "memory" and owner:
        await _in_memory_locks.release(name, owner)


# ============================================================
# Factored job functions — these are the units that can later be
# enqueued to a distributed queue (arq / Celery / etc.).
# ============================================================

async def run_outbox_dispatch(
    session_factory: async_sessionmaker[AsyncSession], max_items: int = 100
) -> int:
    """Dispatch pending outbox messages. Returns number sent."""
    from app.integrations.telegram.outbox import dispatch_pending
    from app.integrations.telegram.runtime import build_clients

    settings = get_settings()
    clients = build_clients()
    if not clients:
        return 0

    async with session_factory() as db:
        n = await dispatch_pending(db, clients, limit=max_items)
        if n:
            await db.commit()
            log.info("telegram_outbox_sent", count=n)
        else:
            await db.rollback()
    return n


async def run_poll_provider(
    provider: str,
    session_factory: async_sessionmaker[AsyncSession],
    max_updates: int = 50,
) -> int:
    """Long-poll updates for a provider (telegram/bale). Returns processed count."""
    from app.integrations.telegram.adapter import TelegramAdapter
    from app.integrations.telegram.runtime import build_clients

    clients = build_clients()
    client = clients.get(provider)
    if not client:
        return 0

    offset = await get_poll_offset(provider)
    processed = 0

    try:
        updates = await client.get_updates(offset=offset or None, timeout=25)
        for upd in updates[:max_updates]:
            uid = int(upd.get("update_id", 0))
            offset = uid + 1
            await set_poll_offset(provider, offset)
            async with session_factory() as db:
                try:
                    adapter = TelegramAdapter(db, client=client, provider=provider)
                    await adapter.handle_update(upd)
                    await db.commit()
                    processed += 1
                except Exception as e:
                    await db.rollback()
                    log.warning("telegram_poll_handle_error", provider=provider, error=str(e))
    except Exception as e:
        log.warning("telegram_poll_error", provider=provider, error=str(e))

    return processed


async def run_sla_and_digest(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, int]:
    """Evaluate SLA on open tasks and send morning digest. Returns counts."""
    from app.integrations.telegram.runtime import _send_digests
    from app.models import Task
    from app.models.enums import TaskStatus
    from app.services import SlaService

    evaluated = 0
    digests = 0

    async with session_factory() as db:
        tasks = (
            await db.execute(
                select(Task).where(Task.status != TaskStatus.COMPLETED).limit(200)
            )
        ).scalars().all()
        sla = SlaService(db)
        for t in tasks:
            try:
                await sla.evaluate_task(t.id)
                evaluated += 1
            except Exception:
                continue
        await db.commit()

        await _send_digests(db)
        await db.commit()
        digests = 1

    return {"sla_evaluated": evaluated, "digests_sent": digests}


async def run_kpi_snapshot_weekly(session_factory: async_sessionmaker[AsyncSession]) -> int:
    """هر هفته یک KPI snapshot برای هر سازمان می‌سازد (روند ۸ هفته‌ای نمای کلی ادمین)."""
    import json as _json

    from app.models import Organization
    from app.models.enterprise import KpiSnapshot
    from app.services.enterprise_ops import EnterpriseService

    created = 0
    async with session_factory() as db:
        org_ids = list((await db.execute(select(Organization.id))).scalars().all())
        for org_id in org_ids:
            last = await db.scalar(
                select(KpiSnapshot.created_at)
                .where(KpiSnapshot.organization_id == org_id)
                .order_by(KpiSnapshot.created_at.desc())
                .limit(1)
            )
            if last and last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            if last and (datetime.now(UTC) - last) < timedelta(days=7):
                continue
            data = await EnterpriseService(db).kpis(org_id)
            db.add(KpiSnapshot(organization_id=org_id, payload_json=_json.dumps(data)))
            created += 1
        await db.commit()
    if created:
        log.info("kpi_snapshot_created", count=created)
    return created


async def run_telegram_setup() -> None:
    """One-time setup: set commands / webhook."""
    from app.integrations.telegram.runtime import build_clients, setup_telegram

    clients = build_clients()
    if clients:
        await setup_telegram(clients)


# ============================================================
# High-level loops (used by lifespan when worker_mode=embedded)
# ============================================================

class Worker:
    """Encapsulates background loops; used by lifespan when embedded."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
        self._tasks: list[asyncio.Task[Any]] = []

    async def start(self) -> None:
        settings = get_settings()
        # One-time setup
        await run_telegram_setup()

        # Leader loops — only the instance that holds the lock runs them.
        async def _outbox_loop():
            settings = get_settings()
            while True:
                try:
                    if await acquire_job("outbox", ttl_seconds=35):
                        try:
                            await run_outbox_dispatch(self.session_factory)
                        finally:
                            await release_job("outbox")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.warning("worker_outbox_loop_error", error=str(e))
                await asyncio.sleep(settings.telegram_outbox_poll_seconds)

        async def _sla_loop():
            settings = get_settings()
            while True:
                try:
                    if await acquire_job("sla", ttl_seconds=65):
                        try:
                            await run_sla_and_digest(self.session_factory)
                        finally:
                            await release_job("sla")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.warning("worker_sla_loop_error", error=str(e))
                await asyncio.sleep(settings.telegram_sla_poll_seconds)

        async def _poll_loop(provider: str):
            settings = get_settings()
            while True:
                try:
                    # Hold the lock for the whole getUpdates long-poll (up to 25s).
                    if await acquire_job(f"poll_{provider}", ttl_seconds=90):
                        try:
                            await run_poll_provider(provider, self.session_factory)
                        finally:
                            await release_job(f"poll_{provider}")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.warning("worker_poll_loop_error", provider=provider, error=str(e))
                await asyncio.sleep(3)  # backoff on error

        async def _snapshot_loop():
            while True:
                try:
                    if await acquire_job("kpi_snapshot", ttl_seconds=1800):
                        try:
                            await run_kpi_snapshot_weekly(self.session_factory)
                        finally:
                            await release_job("kpi_snapshot")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.warning("worker_kpi_snapshot_loop_error", error=str(e))
                await asyncio.sleep(3600)

        self._tasks.append(asyncio.create_task(_outbox_loop(), name="worker-outbox"))
        self._tasks.append(asyncio.create_task(_sla_loop(), name="worker-sla"))
        self._tasks.append(asyncio.create_task(_snapshot_loop(), name="worker-kpi-snapshot"))

        clients = build_clients()
        if settings.telegram_mode == "polling" and "telegram" in clients:
            self._tasks.append(
                asyncio.create_task(_poll_loop("telegram"), name="worker-poll-telegram")
            )
        if settings.bale_mode == "polling" and "bale" in clients:
            self._tasks.append(
                asyncio.create_task(_poll_loop("bale"), name="worker-poll-bale")
            )

        log.info("worker_started", tasks=[t.get_name() for t in self._tasks])

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        self._tasks.clear()
        log.info("worker_stopped")


# ============================================================
# External worker entrypoint (WORKER_MODE=external)
# Uses DB-backed locks for multi-process coordination without Redis
# ============================================================

async def run_external_worker() -> None:
    """Run as standalone external worker process with DB-backed locks."""
    from app.core.logging import setup_logging
    setup_logging()
    
    session_factory = AsyncSessionLocal
    
    # Acquire persistent lock for this worker process
    owner = await try_acquire_db_lock("telegram-worker", ttl_seconds=3600)
    if not owner:
        raise SystemExit("another worker holds telegram-worker")
    
    log.info("external_worker_started", owner=owner)
    
    # Start the embedded worker loops
    worker = Worker(session_factory)
    await worker.start()
    
    try:
        # Keep alive and refresh lock periodically
        while True:
            await asyncio.sleep(300)  # 5 minutes
            # Refresh the DB lock
            async with AsyncSessionLocal() as db:
                from app.core.locks import try_lock, release_lock
                await release_lock(db, "telegram-worker", owner)
                await db.commit()
                new_owner = await try_lock(db, "telegram-worker", ttl_seconds=3600)
                await db.commit()
                if not new_owner:
                    log.warning("lost_worker_lock_shutting_down")
                    break
                owner = new_owner
    finally:
        await worker.stop()
        async with AsyncSessionLocal() as db:
            from app.core.locks import release_lock
            await release_lock(db, "telegram-worker", owner)
            await db.commit()
        log.info("external_worker_stopped")


# ============================================================
# Compatibility helpers used by main.py lifespan
# ============================================================

_worker_instance: Worker | None = None


async def start_background(session_factory: async_sessionmaker[AsyncSession]) -> list[asyncio.Task[Any]]:
    """Backward-compatible entry for main.py lifespan (embedded mode)."""
    global _worker_instance
    _worker_instance = Worker(session_factory)
    await _worker_instance.start()
    return _worker_instance._tasks


async def stop_background() -> None:
    global _worker_instance
    if _worker_instance:
        await _worker_instance.stop()
        _worker_instance = None


def build_clients() -> dict[str, Any]:
    """Re-export for backward compatibility."""
    from app.integrations.telegram.runtime import build_clients as _orig

    return _orig()


# ============================================================
# Test helpers
# ============================================================

def is_external_worker_mode() -> bool:
    """Used in tests to verify WORKER_MODE=external disables background."""
    return get_settings().worker_mode == "external"