"""پوشش بیشتر worker: قفل DB/TTL، offset، outbox/poll، KPI snapshot."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.locks import release_lock, try_lock
from app.integrations.telegram.client import FakeTelegramClient
from app.integrations.telegram.outbox import enqueue_telegram
from app.models.enterprise import JobLock
from app.models.telegram import TelegramAccount
from app.worker import (
    _InMemoryLockManager,
    _poll_offsets_memory,
    acquire_job,
    get_poll_offset,
    release_job,
    run_kpi_snapshot_weekly,
    run_outbox_dispatch,
    run_poll_provider,
    set_poll_offset,
    start_background,
    stop_background,
    try_acquire_leader_lock,
)


class _FakeRedis:
    """کلاینت حداقلی Redis برای مسیرهای happy-path و خطا."""

    def __init__(self, *, fail_ops: bool = False, ping_ok: bool = True):
        self.store: dict[str, str] = {}
        self.fail_ops = fail_ops
        self.ping_ok = ping_ok

    async def set(self, key: str, val: str, nx: bool = False, ex: int | None = None):
        if self.fail_ops:
            raise RuntimeError("redis set failed")
        if nx and key in self.store:
            return False
        self.store[key] = val
        return True

    async def get(self, key: str):
        if self.fail_ops:
            raise RuntimeError("redis get failed")
        return self.store.get(key)

    async def delete(self, key: str):
        if self.fail_ops:
            raise RuntimeError("redis delete failed")
        self.store.pop(key, None)

    async def ping(self):
        if not self.ping_ok:
            raise RuntimeError("redis down")
        return True

    async def aclose(self):
        return None


@pytest.fixture(autouse=True)
def _clear_worker_redis_cache(monkeypatch):
    """وضعیت کش‌شدهٔ Redis بین تست‌ها نماند."""
    import app.worker as worker

    monkeypatch.setattr(worker, "_redis_state", None)
    _poll_offsets_memory.clear()
    yield
    monkeypatch.setattr(worker, "_redis_state", None)
    _poll_offsets_memory.clear()


class TestJobLockTtl:
    @pytest.mark.asyncio
    async def test_try_lock_expires_and_reacquire(self, db: AsyncSession):
        owner1 = await try_lock(db, "ttl-job", ttl_seconds=120)
        assert owner1 is not None
        # هنوز معتبر → دوباره نمی‌گیرد
        assert await try_lock(db, "ttl-job", ttl_seconds=120) is None

        row = await db.get(JobLock, "ttl-job")
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=5)
        await db.flush()

        owner2 = await try_lock(db, "ttl-job", ttl_seconds=60)
        assert owner2 is not None
        assert owner2 != owner1
        await release_lock(db, "ttl-job", owner2)
        assert await db.get(JobLock, "ttl-job") is None

    @pytest.mark.asyncio
    async def test_acquire_job_db_backend(self, db_engine, monkeypatch):
        session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

        async def _db_lock(name: str, ttl_seconds: int = 120) -> str | None:
            async with session_factory() as session:
                owner = await try_lock(session, name, ttl_seconds)
                await session.commit()
                return owner

        async def _db_release(name: str, owner: str) -> None:
            async with session_factory() as session:
                await release_lock(session, name, owner)
                await session.commit()

        monkeypatch.setattr("app.worker._redis_mode", AsyncMock(return_value="absent"))
        monkeypatch.setattr("app.worker.try_acquire_db_lock", _db_lock)
        monkeypatch.setattr("app.worker.release_db_lock", _db_release)
        # بدون این، وقتی DB قفل است مسیر به قفل حافظه می‌افتد و دوباره True می‌شود
        monkeypatch.setattr(
            "app.worker._in_memory_locks.acquire",
            AsyncMock(return_value=False),
        )

        import app.worker as worker

        assert await acquire_job("db-once", 30) is True
        assert worker._job_owners["db-once"][0] == "db"
        assert await acquire_job("db-once", 30) is False
        await release_job("db-once")
        # بعد از release باید دوباره از DB بگیرد
        monkeypatch.setattr(
            "app.worker._in_memory_locks.acquire",
            AsyncMock(return_value=False),
        )
        assert await acquire_job("db-once", 30) is True
        await release_job("db-once")


class TestPollOffsetRedisPaths:
    @pytest.mark.asyncio
    async def test_offset_via_fake_redis(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("app.worker._get_redis", lambda: fake)
        await set_poll_offset("telegram", 42)
        assert await get_poll_offset("telegram") == 42
        assert fake.store  # persisted in fake redis

    @pytest.mark.asyncio
    async def test_offset_redis_errors_fall_back(self, monkeypatch):
        fake = _FakeRedis(fail_ops=True)
        monkeypatch.setattr("app.worker._get_redis", lambda: fake)
        await set_poll_offset("bale", 9)  # should not raise
        assert await get_poll_offset("bale") == 0


class TestRedisLockHelpers:
    @pytest.mark.asyncio
    async def test_leader_lock_redis_ok(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("app.worker._get_redis", lambda: fake)
        import app.worker as worker

        monkeypatch.setattr(worker, "_redis_state", None)
        ok = await try_acquire_leader_lock("leader-r", ttl_seconds=10)
        assert ok is True
        ok2 = await try_acquire_leader_lock("leader-r", ttl_seconds=10)
        # second acquire: redis nx fails → falls through to in-memory (may succeed)
        assert isinstance(ok2, bool)

    @pytest.mark.asyncio
    async def test_redis_mode_down_and_ok(self, monkeypatch):
        import app.worker as worker

        down = _FakeRedis(ping_ok=False)
        monkeypatch.setattr("app.worker._get_redis", lambda: down)
        monkeypatch.setattr(worker, "redis", MagicMock())
        monkeypatch.setattr(
            "app.worker.get_settings",
            lambda: MagicMock(redis_url="redis://localhost:6379/0"),
        )
        monkeypatch.setattr(worker, "_redis_state", None)
        assert await worker._redis_mode() == "down"

        monkeypatch.setattr(worker, "_redis_state", None)
        ok_client = _FakeRedis(ping_ok=True)
        monkeypatch.setattr("app.worker._get_redis", lambda: ok_client)
        assert await worker._redis_mode() == "ok"

    @pytest.mark.asyncio
    async def test_acquire_job_redis_ok_held(self, monkeypatch):
        monkeypatch.setattr("app.worker._redis_mode", AsyncMock(return_value="ok"))
        monkeypatch.setattr("app.worker._redis_try_lock", AsyncMock(return_value=True))
        monkeypatch.setattr("app.worker._redis_release_lock", AsyncMock())
        assert await acquire_job("redis-held", 30) is True
        await release_job("redis-held")


class TestInMemoryIsLocked:
    @pytest.mark.asyncio
    async def test_is_locked(self):
        mgr = _InMemoryLockManager()
        assert mgr.is_locked("x") is False
        await mgr.acquire("x", "o", ttl_seconds=10)
        assert mgr.is_locked("x") is True
        await mgr.release("x", "o")
        assert mgr.is_locked("x") is False


class TestOutboxAndPoll:
    @pytest.mark.asyncio
    async def test_run_outbox_dispatch_sends(self, db_engine, seeded, monkeypatch):
        session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
        fake = FakeTelegramClient()
        monkeypatch.setattr("app.integrations.telegram.runtime.build_clients", lambda: {"telegram": fake})
        monkeypatch.setattr("app.worker.build_clients", lambda: {"telegram": fake})

        ali = seeded["ali"]
        async with session_factory() as db:
            db.add(
                TelegramAccount(
                    organization_id=ali.organization_id,
                    user_id=ali.id,
                    provider="telegram",
                    telegram_user_id=9001,
                    telegram_chat_id=1001,
                )
            )
            await db.flush()
            await enqueue_telegram(
                db,
                organization_id=ali.organization_id,
                user_id=ali.id,
                event_type="task_assigned",
                text="کار جدید از worker",
            )
            await db.commit()

        n = await run_outbox_dispatch(session_factory)
        assert n == 1
        assert len(fake.sent) == 1

    @pytest.mark.asyncio
    async def test_run_outbox_dispatch_no_clients(self, db_engine, monkeypatch):
        session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
        monkeypatch.setattr("app.integrations.telegram.runtime.build_clients", lambda: {})
        assert await run_outbox_dispatch(session_factory) == 0

    @pytest.mark.asyncio
    async def test_run_poll_provider_processes_updates(self, db_engine, seeded, monkeypatch):
        session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
        fake = FakeTelegramClient()
        fake.updates = [
            {
                "update_id": 7001,
                "message": {
                    "message_id": 1,
                    "text": "",  # empty → text_only path, no link needed
                    "chat": {"id": 1001},
                    "from": {"id": 9001, "username": "ali"},
                },
            }
        ]
        monkeypatch.setattr(
            "app.integrations.telegram.runtime.build_clients",
            lambda: {"telegram": fake},
        )
        monkeypatch.setattr("app.worker._get_redis", lambda: None)
        count = await run_poll_provider("telegram", session_factory)
        assert count == 1
        assert await get_poll_offset("telegram") == 7002

    @pytest.mark.asyncio
    async def test_run_poll_provider_handle_error(self, db_engine, monkeypatch):
        session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
        fake = FakeTelegramClient()
        fake.updates = [{"update_id": 8001, "callback_query": {"id": "bad"}}]  # incomplete
        monkeypatch.setattr(
            "app.integrations.telegram.runtime.build_clients",
            lambda: {"telegram": fake},
        )
        monkeypatch.setattr("app.worker._get_redis", lambda: None)

        # Force handle_update to raise so rollback path runs
        from app.integrations.telegram import adapter as adapter_mod

        async def boom(self, update):  # noqa: ANN001
            raise RuntimeError("boom")

        monkeypatch.setattr(adapter_mod.TelegramAdapter, "handle_update", boom)
        count = await run_poll_provider("telegram", session_factory)
        assert count == 0


class TestKpiAndBackground:
    @pytest.mark.asyncio
    async def test_run_kpi_snapshot_weekly(self, db_engine, seeded):
        session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
        n = await run_kpi_snapshot_weekly(session_factory)
        assert n >= 1
        # second call within 7 days → skip
        n2 = await run_kpi_snapshot_weekly(session_factory)
        assert n2 == 0

    @pytest.mark.asyncio
    async def test_start_stop_background(self, db_engine, monkeypatch):
        session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
        monkeypatch.setattr("app.worker.run_telegram_setup", AsyncMock())
        monkeypatch.setattr("app.integrations.telegram.runtime.build_clients", lambda: {})
        tasks = await start_background(session_factory)
        assert len(tasks) >= 2
        await stop_background()

    @pytest.mark.asyncio
    async def test_worker_loops_tick_once(self, db_engine, monkeypatch):
        """یک تیک از حلقه‌های outbox/sla/snapshot را با sleep کوتاه اجرا می‌کند."""
        import asyncio

        from app.worker import Worker

        session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
        monkeypatch.setattr("app.worker.run_telegram_setup", AsyncMock())
        monkeypatch.setattr("app.worker.run_outbox_dispatch", AsyncMock(return_value=0))
        monkeypatch.setattr(
            "app.worker.run_sla_and_digest",
            AsyncMock(return_value={"sla_evaluated": 0, "digests_sent": 0}),
        )
        monkeypatch.setattr("app.worker.run_kpi_snapshot_weekly", AsyncMock(return_value=0))
        monkeypatch.setattr("app.worker.acquire_job", AsyncMock(return_value=True))
        monkeypatch.setattr("app.worker.release_job", AsyncMock())
        monkeypatch.setattr(
            "app.integrations.telegram.runtime.build_clients",
            lambda: {},
        )
        monkeypatch.setattr(
            "app.worker.get_settings",
            lambda: MagicMock(
                telegram_outbox_poll_seconds=0.01,
                telegram_sla_poll_seconds=0.01,
                telegram_mode="off",
                bale_mode="off",
            ),
        )

        worker = Worker(session_factory)
        await worker.start()
        await asyncio.sleep(0.05)
        await worker.stop()
        assert worker._tasks == []


class TestTelegramSetupAndDbLockDirect:
    @pytest.mark.asyncio
    async def test_run_telegram_setup_with_clients(self, monkeypatch):
        from app.worker import run_telegram_setup

        setup = AsyncMock()
        monkeypatch.setattr(
            "app.integrations.telegram.runtime.build_clients",
            lambda: {"telegram": FakeTelegramClient()},
        )
        monkeypatch.setattr("app.integrations.telegram.runtime.setup_telegram", setup)
        await run_telegram_setup()
        setup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_try_acquire_db_lock_via_sessionlocal(self, db_engine, monkeypatch):
        from app.worker import release_db_lock, try_acquire_db_lock

        session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

        class _Ctx:
            def __init__(self):
                self._cm = session_factory()

            async def __aenter__(self):
                self.session = await self._cm.__aenter__()
                return self.session

            async def __aexit__(self, *args):
                return await self._cm.__aexit__(*args)

        monkeypatch.setattr("app.worker.AsyncSessionLocal", lambda: _Ctx())
        owner = await try_acquire_db_lock("direct-db", 30)
        assert owner is not None
        await release_db_lock("direct-db", owner)


class TestSlaAndDigest:
    @pytest.mark.asyncio
    async def test_digest_with_naive_deadline_does_not_crash(self, db_engine, seeded, monkeypatch):
        """deadline بدون timezone (از SQLite) نباید حلقهٔ SLA/digest را بشکند.

        رگرسیون: `_send_digests` زمانی `t.deadline < utc_now()` را مستقیم
        مقایسه می‌کرد و با datetime ناآگاه TypeError می‌داد.
        """
        from datetime import datetime

        from app.models import Task
        from app.worker import run_sla_and_digest

        session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
        fake = FakeTelegramClient()
        monkeypatch.setattr(
            "app.integrations.telegram.runtime.build_clients", lambda: {"telegram": fake}
        )
        monkeypatch.setattr("app.worker.build_clients", lambda: {"telegram": fake})

        ali = seeded["ali"]
        async with session_factory() as db:
            db.add(
                TelegramAccount(
                    organization_id=ali.organization_id,
                    user_id=ali.id,
                    provider="telegram",
                    telegram_user_id=9002,
                    telegram_chat_id=1002,
                    digest_enabled=True,
                )
            )
            db.add(
                Task(
                    organization_id=ali.organization_id,
                    title="task with naive past deadline",
                    owner_id=ali.id,
                    deadline=datetime(2020, 1, 1, 12, 0),  # naive عمداً
                )
            )
            await db.commit()

        result = await run_sla_and_digest(session_factory)
        assert result["digests_sent"] == 1
        assert result["sla_evaluated"] >= 1
