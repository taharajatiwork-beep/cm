"""زنجیرهٔ هش لاگ ممیزی — رکورد قابل‌دستکاری نباشد.

پیش از این، `audit_logs` فقط append-only در سطح API بود، ولی هر کسی با
دسترسی دیتابیس می‌توانست سطرها را UPDATE یا DELETE کند و هیچ اثری نمی‌ماند.
حالا هر سطر `row_hash` دارد که از محتوای سطر + `prev_hash` (هش سطر قبلی در
همان سازمان) ساخته می‌شود: تغییر یا حذف هر سطر، زنجیره را می‌شکند.
"""

import asyncio

import pytest
from sqlalchemy import select, update

from app.models import AuditLog
from app.services import audit_row_hash, write_audit


async def _verify_chain(db, organization_id) -> tuple[bool, str]:
    """کل زنجیرهٔ یک سازمان را بازمحاسبه می‌کند. (ok, first_broken_action)"""
    # فقط سطرهای هش‌دار: سطرهای قدیمی (قبل از 0011) ممیزی تاریخی‌اند و
    # زنجیره از اولین سطر هش‌دار شروع می‌شود.
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
        ).scalars().all()
    )
    prev: str | None = None
    expected_seq = 1
    for r in rows:
        fields = {
            "id": str(r.id),
            "organization_id": str(r.organization_id),
            "actor_id": str(r.actor_id) if r.actor_id else "",
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": str(r.entity_id),
            "details": r.details or "",
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "chain_seq": str(r.chain_seq),
        }
        if r.chain_seq != expected_seq:
            return False, f"chain_seq gap at {r.action}"
        if (r.prev_hash or None) != prev:
            return False, f"prev_hash mismatch at {r.action}"
        if r.row_hash != audit_row_hash(fields, prev):
            return False, f"row_hash mismatch at {r.action}"
        prev = r.row_hash
        expected_seq += 1
    return True, ""


class TestHashChain:
    @pytest.mark.asyncio
    async def test_new_rows_get_hashes(self, seeded, db):
        org = seeded["org"].id
        row = await write_audit(
            db,
            organization_id=org,
            action="test.write",
            entity_type="case",
            entity_id=seeded["org"].id,
        )
        assert row.row_hash and len(row.row_hash) == 64
        assert row.prev_hash is None  # اولین سطر سازمان

    @pytest.mark.asyncio
    async def test_chain_links_rows(self, seeded, db):
        org = seeded["org"].id
        first = await write_audit(
            db, organization_id=org, action="a.one", entity_type="x", entity_id=seeded["org"].id
        )
        second = await write_audit(
            db, organization_id=org, action="a.two", entity_type="x", entity_id=seeded["org"].id
        )
        assert second.prev_hash == first.row_hash

    @pytest.mark.asyncio
    async def test_chain_is_per_organization(self, seeded, db):
        """زنجیرهٔ سازمان الف نباید به سازمان ب گره بخورد."""
        from app.services import OrgService

        org_b = await OrgService(db).create_organization("Beta", "beta")
        a1 = await write_audit(
            db, organization_id=seeded["org"].id, action="a", entity_type="x", entity_id=seeded["org"].id
        )
        b1 = await write_audit(
            db, organization_id=org_b.id, action="b", entity_type="x", entity_id=org_b.id
        )
        assert b1.prev_hash is None, "زنجیرهٔ سازمان ب باید مستقل باشد"
        assert a1.row_hash != b1.row_hash

    @pytest.mark.asyncio
    async def test_valid_chain_verifies(self, seeded, db):
        org = seeded["org"].id
        for i in range(4):
            await write_audit(
                db,
                organization_id=org,
                action=f"act.{i}",
                entity_type="x",
                entity_id=seeded["org"].id,
                details={"i": i},
            )
        ok, why = await _verify_chain(db, org)
        assert ok, why

    @pytest.mark.asyncio
    async def test_tampering_is_detected(self, seeded, db):
        """تغییر محتوای یک سطر قدیمی باید زنجیره را بشکند."""
        org = seeded["org"].id
        for i in range(3):
            await write_audit(
                db, organization_id=org, action=f"act.{i}", entity_type="x", entity_id=seeded["org"].id
            )

        target = await db.scalar(
            select(AuditLog)
            .where(AuditLog.organization_id == org, AuditLog.action == "act.1")
            .order_by(AuditLog.chain_seq)
        )
        # شبیه‌سازی دستکاری مستقیم در دیتابیس (دور زدن لایهٔ سرویس)
        target.action = "act.1_EDITED"
        await db.flush()

        ok, why = await _verify_chain(db, org)
        assert not ok
        assert "act.1_EDITED" in why

    @pytest.mark.asyncio
    async def test_deletion_breaks_chain(self, seeded, db):
        """حذف یک سطر میانی، prev_hash سطر بعدی را نامعتبر می‌کند."""
        org = seeded["org"].id
        for i in range(3):
            await write_audit(
                db, organization_id=org, action=f"act.{i}", entity_type="x", entity_id=seeded["org"].id
            )
        target = await db.scalar(
            select(AuditLog)
            .where(AuditLog.organization_id == org, AuditLog.action == "act.1")
            .order_by(AuditLog.chain_seq)
        )
        await db.delete(target)
        await db.flush()

        ok, why = await _verify_chain(db, org)
        assert not ok, "حذف سطر نباید بی‌سروصدا بماند"

    @pytest.mark.asyncio
    async def test_hash_is_deterministic_and_order_independent(self):
        a = audit_row_hash({"x": "1", "y": "2"}, "prev")
        b = audit_row_hash({"y": "2", "x": "1"}, "prev")
        assert a == b, "ترتیب کلیدها نباید هش را عوض کند"
        assert len(a) == 64

    @pytest.mark.asyncio
    async def test_different_prev_gives_different_hash(self):
        assert audit_row_hash({"x": "1"}, "a") != audit_row_hash({"x": "1"}, "b")

    @pytest.mark.asyncio
    async def test_actor_change_detected(self, seeded, db):
        """عوض کردن actor_id هم باید شناسایی شود."""
        org = seeded["org"].id
        r = await write_audit(
            db,
            organization_id=org,
            action="a",
            entity_type="x",
            entity_id=seeded["org"].id,
            actor_id=seeded["ali"].id,
        )
        await db.execute(
            update(AuditLog).where(AuditLog.id == r.id).values(actor_id=seeded["sara"].id)
        )
        await db.flush()
        ok, _ = await _verify_chain(db, org)
        assert not ok


class TestAuditChainUnderConcurrency:
    """دو تراکنش هم‌زمان نباید chain_seq یکسان بگیرند وگرنه زنجیره می‌شکند.

    ریشهٔ باگ: خواندن «آخرین سطر» و نوشتن سطر جدید بین دو تراکنش race داشت،
    پس هر دو `chain_seq = N+1` می‌گرفتند و پس از آن زنجیره نامعتبر می‌شد.
    """

    @pytest.mark.asyncio
    async def test_concurrent_writes_keep_chain_intact(self, seeded, db, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from app.services import verify_audit_chain

        # sessionmaker را از engine فیکسچر می‌سازیم نه از ماژول، وگرنه
        # به DATABASE_URL پیش‌فرض (Postgres) می‌رود و اتصال رد می‌شود
        factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

        org_id = seeded["org"].id
        users = [seeded["ali"], seeded["sara"], seeded["reza"]]

        async def writer(actor_id, n: int) -> None:
            async with factory() as s:
                for i in range(n):
                    await write_audit(
                        s,
                        organization_id=org_id,
                        action="concurrency.test",
                        entity_type="case",
                        entity_id=org_id,
                        actor_id=actor_id,
                        details={"i": i},
                    )
                await s.commit()

        await asyncio.gather(*(writer(u.id, 3) for u in users))

        result = await verify_audit_chain(db, org_id)
        assert result["ok"], result
        assert result["rows_checked"] >= 9
        # شماره‌های ترتیبی یکتا و بدون حفره‌اند
        seqs = list(
            (
                await db.execute(
                    select(AuditLog.chain_seq)
                    .where(
                        AuditLog.organization_id == org_id,
                        AuditLog.row_hash.isnot(None),
                    )
                    .order_by(AuditLog.chain_seq)
                )
            ).scalars()
        )
        assert seqs == list(range(1, len(seqs) + 1))
