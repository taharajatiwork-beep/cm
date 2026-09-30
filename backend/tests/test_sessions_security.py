"""پوشش مسیرهای امنیتی نشست: چرخش refresh، تشخیص بازپخش، قفل ورود.

پیش از این این توابع فقط از مسیر HTTP غیرمستقیم لمس می‌شدند (پوشش ۵۰٪)
و قفل‌های DB فقط در test_worker. اینجا هر مسیر بیمه‌ای مستقیماً سنجیده
می‌شود — به‌ویژه بازپخش توکن refresh که سرقتِ آن را لو می‌دهد.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.locks import release_lock, try_lock
from app.models import User
from app.models.enterprise import JobLock, RefreshToken
from app.services.sessions import (
    issue_session,
    login_allowed,
    record_login_failure,
    record_login_success,
    revoke_all,
    rotate_refresh,
)

REUSE_LIMIT = 30


class TestIssueSession:
    @pytest.mark.asyncio
    async def test_issue_session_stores_hash_not_raw(self, seeded, db):
        """توکن خام هرگز نباید در دیتابیس بماند — فقط هش."""
        user = await db.get(User, seeded["ali"].id)
        access, raw = await issue_session(db, user)
        await db.commit()

        assert access and raw
        rows = list(
            (await db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))).scalars()
        )
        assert len(rows) == 1
        stored = rows[0].token_hash
        assert stored != raw
        assert len(stored) == 64  # sha256 hex
        assert raw not in stored

    @pytest.mark.asyncio
    async def test_issue_session_expiry_is_configured(self, seeded, db):
        user = await db.get(User, seeded["ali"].id)
        await issue_session(db, user)
        await db.commit()
        row = (await db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))).scalars().first()
        expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
        days = get_settings().refresh_token_expire_days
        # باید در همین نزدیکی منقضی شود (نقطهٔ امروز + N روز)
        expected = datetime.now(UTC) + timedelta(days=days)
        assert abs((expires - expected).total_seconds()) < 3600


class TestRotateRefresh:
    @pytest.mark.asyncio
    async def test_rotation_revokes_old_and_issues_new(self, seeded, db):
        user = await db.get(User, seeded["ali"].id)
        _, raw1 = await issue_session(db, user)
        await db.commit()

        result = await rotate_refresh(db, raw1)
        await db.commit()
        assert result is not None
        access2, raw2 = result
        assert access2 and raw2
        assert raw2 != raw1  # توکن جدید، نه بازپخش همان قدیمی

        rows = list(
            (await db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))).scalars()
        )
        assert len(rows) == 2
        # توکن اول لغو شده، توکن دوم فعال
        assert rows[0].revoked_at is not None

    @pytest.mark.asyncio
    async def test_replaying_a_rotated_token_is_refused(self, seeded, db):
        """بازپخش همان توکن بعد از چرخش باید رد شود — نشانهٔ سرقت توکن."""
        user = await db.get(User, seeded["ali"].id)
        _, raw = await issue_session(db, user)
        await db.commit()

        first = await rotate_refresh(db, raw)
        await db.commit()
        assert first is not None

        replay = await rotate_refresh(db, raw)
        await db.commit()
        assert replay is None, "توکن مصرف‌شده نباید دوباره قابل چرخش باشد"

    @pytest.mark.asyncio
    async def test_unknown_token_is_refused(self, seeded, db):
        assert await rotate_refresh(db, "never-issued-token-value") is None

    @pytest.mark.asyncio
    async def test_expired_token_is_refused(self, seeded, db):
        user = await db.get(User, seeded["ali"].id)
        _, raw = await issue_session(db, user)
        await db.commit()
        row = (await db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))).scalars().first()
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db.flush()
        assert await rotate_refresh(db, raw) is None

    @pytest.mark.asyncio
    async def test_revoke_only_logs_out_without_new_token(self, seeded, db):
        """مسیر logout: توکن لغو می‌شود ولی توکن جدیدی صادر نمی‌شود."""
        user = await db.get(User, seeded["ali"].id)
        _, raw = await issue_session(db, user)
        await db.commit()

        assert await rotate_refresh(db, raw, revoke_only=True) is None
        await db.commit()
        row = (await db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))).scalars().first()
        assert row.revoked_at is not None

    @pytest.mark.asyncio
    async def test_inactive_user_cannot_rotate(self, seeded, db):
        user = await db.get(User, seeded["ali"].id)
        _, raw = await issue_session(db, user)
        await db.commit()
        user.is_active = False
        await db.flush()
        assert await rotate_refresh(db, raw) is None


class TestRevokeAll:
    @pytest.mark.asyncio
    async def test_revoke_all_kills_every_active_token(self, seeded, db):
        user = await db.get(User, seeded["ali"].id)
        _, t1 = await issue_session(db, user)
        _, t2 = await issue_session(db, user)
        await db.commit()

        await revoke_all(db, user.id)
        await db.commit()

        # هیچ‌کدام دیگر قابل استفاده نیستند
        assert await rotate_refresh(db, t1) is None
        assert await rotate_refresh(db, t2) is None

    @pytest.mark.asyncio
    async def test_revoke_all_writes_audit(self, seeded, db):
        user = await db.get(User, seeded["ali"].id)
        await revoke_all(db, user.id)
        await db.commit()
        from app.models import AuditLog

        actions = list(
            (
                await db.execute(
                    select(AuditLog.action).where(
                        AuditLog.entity_id == user.id, AuditLog.action == "auth.logout_all"
                    )
                )
            ).scalars()
        )
        assert actions


class TestLoginLockout:
    @pytest.mark.asyncio
    async def test_lockout_after_max_failures(self, seeded, db):
        org_id = seeded["org"].id
        email = seeded["ali"].email
        max_failures = get_settings().login_max_failures

        for _ in range(max_failures - 1):
            await record_login_failure(db, org_id, email)
        await db.commit()
        user = await db.get(User, seeded["ali"].id)
        assert user.failed_login_count == max_failures - 1
        assert user.locked_until is None, "زیر سقف نباید قفل شود"

        await record_login_failure(db, org_id, email)
        await db.commit()
        user = await db.get(User, seeded["ali"].id)
        assert user.failed_login_count == max_failures
        assert user.locked_until is not None, "در سقف باید قفل شود"

    @pytest.mark.asyncio
    async def test_success_clears_failures_and_lock(self, seeded, db):
        org_id = seeded["org"].id
        email = seeded["ali"].email
        for _ in range(get_settings().login_max_failures):
            await record_login_failure(db, org_id, email)
        await db.flush()

        user = await db.get(User, seeded["ali"].id)
        await record_login_success(db, user)
        await db.commit()

        user = await db.get(User, seeded["ali"].id)
        assert user.failed_login_count == 0
        assert user.locked_until is None

    @pytest.mark.asyncio
    async def test_failure_for_unknown_email_is_noop(self, seeded, db):
        # نباید استثنا بدهد (جریان حمله‌کنندهٔ ایمیل تصادفی)
        await record_login_failure(db, seeded["org"].id, "ghost@example.com")
        await db.commit()


class TestLoginAllowed:
    def test_allows_up_to_limit_then_blocks(self):
        from app.core import ratelimit

        ratelimit.reset()
        try:
            key_ok = ("10.0.0.9", "x@example.com")
            assert all(login_allowed(*key_ok, limit=5, window=60) for _ in range(5))
            assert login_allowed(*key_ok, limit=5, window=60) is False
        finally:
            ratelimit.reset()

    def test_email_is_case_insensitive(self):
        from app.core import ratelimit

        ratelimit.reset()
        try:
            assert login_allowed("10.0.0.10", "A@Example.com", limit=1, window=60)
            # همان ایمیل با حروف کوچک باید همان شمارنده را بزند
            assert login_allowed("10.0.0.10", "a@example.com", limit=1, window=60) is False
        finally:
            ratelimit.reset()

    def test_different_hosts_have_separate_counters(self):
        from app.core import ratelimit

        ratelimit.reset()
        try:
            assert login_allowed("10.0.0.1", "y@example.com", limit=1, window=60)
            assert login_allowed("10.0.0.2", "y@example.com", limit=1, window=60)
        finally:
            ratelimit.reset()


class TestDbLocks:
    @pytest.mark.asyncio
    async def test_lock_acquire_and_release(self, seeded, db):
        owner = await try_lock(db, "unit.lock", ttl_seconds=30)
        await db.commit()
        assert owner is not None

        # گرفتن دوم باید ناموفق باشد تا هم‌پوشانی نباشد
        second = await try_lock(db, "unit.lock", ttl_seconds=30)
        await db.commit()
        assert second is None

        await release_lock(db, "unit.lock", owner)
        await db.commit()
        third = await try_lock(db, "unit.lock", ttl_seconds=30)
        await db.commit()
        assert third is not None

    @pytest.mark.asyncio
    async def test_expired_lock_is_reacquirable(self, seeded, db):
        owner = await try_lock(db, "unit.ttl", ttl_seconds=1)
        await db.commit()
        assert owner is not None

        # تاریخ انقضا را دستی عقب می‌بریم تا منتظر زمان واقعی نمانیم
        row = (await db.execute(select(JobLock).where(JobLock.name == "unit.ttl"))).scalars().first()
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=5)
        await db.commit()
        reacquired = await try_lock(db, "unit.ttl", ttl_seconds=30)
        await db.commit()
        assert reacquired is not None

    @pytest.mark.asyncio
    async def test_release_by_wrong_owner_is_ignored(self, seeded, db):
        owner = await try_lock(db, "unit.owner", ttl_seconds=30)
        await db.commit()
        assert owner is not None
        await release_lock(db, "unit.owner", "someone-else")
        await db.commit()
        # قفل هنوز در دست صاحب واقعی است
        blocked = await try_lock(db, "unit.owner", ttl_seconds=30)
        await db.commit()
        assert blocked is None
        await release_lock(db, "unit.owner", owner)
        await db.commit()
