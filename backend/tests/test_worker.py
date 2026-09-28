"""Tests for worker coordination locks and fallback logic."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker import (
    Worker,
    _InMemoryLockManager,
    acquire_job,
    get_poll_offset,
    is_external_worker_mode,
    release_job,
    release_leader_lock,
    run_poll_provider,
    run_sla_and_digest,
    set_poll_offset,
    try_acquire_leader_lock,
)


class TestInMemoryLockManager:
    """Test the in-memory lock fallback."""

    @pytest.mark.asyncio
    async def test_acquire_release(self):
        mgr = _InMemoryLockManager()
        ok = await mgr.acquire("test-job", "owner1", ttl_seconds=10)
        assert ok is True
        # Second acquire should fail
        ok2 = await mgr.acquire("test-job", "owner2", ttl_seconds=10)
        assert ok2 is False
        # Release and re-acquire
        await mgr.release("test-job", "owner1")
        ok3 = await mgr.acquire("test-job", "owner2", ttl_seconds=10)
        assert ok3 is True

    @pytest.mark.asyncio
    async def test_ttl_auto_release(self):
        mgr = _InMemoryLockManager()
        ok = await mgr.acquire("ttl-job", "owner1", ttl_seconds=0)  # instant expiry
        assert ok is True
        # Wait for auto-release
        await asyncio.sleep(0.05)
        ok2 = await mgr.acquire("ttl-job", "owner2", ttl_seconds=10)
        assert ok2 is True


class TestLeaderLockFallback:
    """Test leader lock acquisition with Redis -> in-memory fallback."""

    @pytest.mark.asyncio
    async def test_try_acquire_without_redis(self, monkeypatch):
        """Without Redis, should fall back to in-memory lock."""
        monkeypatch.setattr("app.worker._get_redis", lambda: None)
        ok = await try_acquire_leader_lock("test-fallback", ttl_seconds=5)
        assert ok is True
        # Second call should fail (same process)
        ok2 = await try_acquire_leader_lock("test-fallback", ttl_seconds=5)
        assert ok2 is False
        await release_leader_lock("test-fallback")

    @pytest.mark.asyncio
    async def test_release_leader_lock(self, monkeypatch):
        monkeypatch.setattr("app.worker._get_redis", lambda: None)
        await try_acquire_leader_lock("rel-test", ttl_seconds=5)
        # Should not raise
        await release_leader_lock("rel-test")


class TestJobLock:
    @pytest.mark.asyncio
    async def test_redis_down_does_not_double_run(self, monkeypatch):
        monkeypatch.setattr("app.worker._redis_mode", AsyncMock(return_value="down"))
        monkeypatch.setattr("app.worker.try_acquire_db_lock", AsyncMock(return_value=None))
        assert await acquire_job("once", 30) is True
        assert await acquire_job("once", 30) is False
        await release_job("once")

    @pytest.mark.asyncio
    async def test_reachable_redis_does_not_fall_through(self, monkeypatch):
        monkeypatch.setattr("app.worker._redis_mode", AsyncMock(return_value="ok"))
        monkeypatch.setattr("app.worker._redis_try_lock", AsyncMock(return_value=False))
        assert await acquire_job("held", 30) is False


class TestPollOffset:
    """Test polling offset persistence."""

    @pytest.mark.asyncio
    async def test_get_set_offset_memory(self, monkeypatch):
        monkeypatch.setattr("app.worker._get_redis", lambda: None)
        await set_poll_offset("telegram", 123)
        offset = await get_poll_offset("telegram")
        assert offset == 123
        # Different provider
        offset2 = await get_poll_offset("bale")
        assert offset2 == 0


class TestWorkerLoops:
    """Test worker job functions."""

    @pytest.mark.asyncio
    async def test_run_sla_and_digest(self, db_engine):
        from app.worker import run_sla_and_digest
        from sqlalchemy.ext.asyncio import async_sessionmaker
        from sqlalchemy.pool import StaticPool
        from app.db.session import get_db

        # Create a session factory for the test database
        session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
        result = await run_sla_and_digest(session_factory)
        assert "sla_evaluated" in result
        assert "digests_sent" in result
        assert result["sla_evaluated"] >= 0

    @pytest.mark.asyncio
    async def test_run_poll_provider_no_client(self, monkeypatch):
        monkeypatch.setattr("app.worker.build_clients", lambda: {})
        from app.db.session import AsyncSessionLocal
        count = await run_poll_provider("telegram", AsyncSessionLocal)
        assert count == 0


class TestExternalWorkerMode:
    """Test WORKER_MODE=external helper."""

    def test_is_external_false_by_default(self):
        assert is_external_worker_mode() is False


class TestWorkerClass:
    """Test Worker high-level class."""

    @pytest.mark.asyncio
    async def test_start_stop(self, db_engine):
        from app.db.session import AsyncSessionLocal
        from sqlalchemy.ext.asyncio import async_sessionmaker

        session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
        from app.worker import Worker

        worker = Worker(session_factory)
        await worker.start()
        # Tasks should be created
        assert len(worker._tasks) >= 2  # outbox + sla at minimum
        await worker.stop()
        assert len(worker._tasks) == 0