"""تست مایگریشن ایندکس.

هدف: مطمئن شویم مایگریشن 0010 ایندکس‌ها را واقعاً روی ستون‌های موجود
می‌سازد — و اگر روزی ستونی عوض شد، همین تست قبل از استقرار شکست بخورد.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0010_query_indexes.py"
)


def _load_migration():
    """مایگریشن را از فایل بارگذاری می‌کند (نامش با عدد شروع می‌شود و
    قابل import به‌صورت ماژول نیست)."""
    spec = importlib.util.spec_from_file_location("mig_0010", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migration():
    return _load_migration()


async def _run_upgrade(module, engine) -> None:
    """upgrade را روی دیتابیس تست اجرا می‌کند."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    async with engine.begin() as conn:
        def _apply(sync_conn) -> None:
            ctx = MigrationContext.configure(sync_conn)
            with Operations.context(ctx):
                module.upgrade()

        await conn.run_sync(_apply)


async def _index_names(engine) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
        )
        return {r[0] for r in rows}


async def _table_columns(engine, table: str) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t AND table_schema = 'public'"
            ),
            {"t": table},
        )
        return {r[0] for r in rows}


@pytest.mark.asyncio
async def test_upgrade_is_idempotent(migration, db_engine):
    """اجرای دوباره نباید خطا بدهد (idempotent)."""
    await _run_upgrade(migration, db_engine)
    await _run_upgrade(migration, db_engine)


@pytest.mark.asyncio
async def test_indexes_only_reference_real_columns(migration, db_engine):
    """هیچ ایندکسی نباید به ستون ناموجود اشاره کند.

    این تست عمداً سخت‌گیر است: اگر ستونی در مایگریشن اشتباه تایپ شده باشد،
    مایگریشن با guard آن را بی‌سروصدا رد می‌کند و ایندکس بی‌ساخت می‌ماند.
    پس اینجا باید صریح شکست بخورد تا کسی متوجه شود.
    """
    missing_any = []
    for table, index_name, columns in migration.INDEXES:
        existing = await _table_columns(db_engine, table)
        if not existing:
            continue  # این جدول در دیتابیس تست وجود ندارد
        missing = [c for c in columns if c not in existing]
        if missing:
            missing_any.append(f"{table}.{index_name} needs {missing}, has {sorted(existing)}")
    assert not missing_any, "indexes reference columns that do not exist:\n" + "\n".join(
        missing_any
    )


@pytest.mark.asyncio
async def test_core_indexes_are_created(migration, db_engine):
    """ایندکس‌های اصلی باید واقعاً در دیتابیس ساخته شده باشند."""
    await _run_upgrade(migration, db_engine)
    names = await _index_names(db_engine)
    for table, index_name, _columns in migration.INDEXES:
        if not await _table_columns(db_engine, table):
            continue
        assert index_name in names, f"{index_name} was not created on {table}"


@pytest.mark.asyncio
async def test_conversation_polling_queries_are_indexed(migration, db_engine):
    """کوئری‌هایی که هر ۱۰ ثانیه اجرا می‌شوند باید ایندکس داشته باشند."""
    await _run_upgrade(migration, db_engine)
    names = await _index_names(db_engine)
    assert "ix_messages_conversation_created" in names
    assert "ix_conversations_org_archived_created" in names


@pytest.mark.asyncio
async def test_downgrade_removes_indexes(migration, db_engine):
    """rollback باید ایندکس‌ها را پاک کند."""
    await _run_upgrade(migration, db_engine)
    async with db_engine.begin() as conn:
        def _apply(sync_conn) -> None:
            from alembic.migration import MigrationContext
            from alembic.operations import Operations

            ctx = MigrationContext.configure(sync_conn)
            with Operations.context(ctx):
                migration.downgrade()

        await conn.run_sync(_apply)
    names = await _index_names(db_engine)
    assert "ix_messages_conversation_created" not in names
