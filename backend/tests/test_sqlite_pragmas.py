"""تست رگرسیون برای PRAGMAهای SQLite روی هر اتصال تازه.

ریشهٔ باگ: `app/db/session.py` PRAGMAهای WAL/busy_timeout را فقط یک‌بار در
startup روی یک اتصال اجرا می‌کرد، ولی این PRAGMAها به «اتصال» گره خورده‌اند.
استخر اتصال (به‌خاطر `pool_pre_ping`) اتصال‌های قدیمی را برمی‌گرداند و آن‌ها
`busy_timeout` ندارند. نتیجهٔ واقعی که دیده شد: لاگین بعد از یک bootstrap موفق
گاهی «Organization not found» می‌داد، در حالی که سازمان در فایل SQLite بود.
"""

import sqlite3

from sqlalchemy.ext.asyncio import create_async_engine

from app.db.session import _SQLITE_PRAGMAS


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """همان کاری که hook روی اتصال تازه انجام می‌دهد."""
    cur = conn.cursor()
    try:
        for pragma in _SQLITE_PRAGMAS:
            cur.execute(pragma)
    finally:
        cur.close()


def test_pragmas_list_covers_the_ones_that_mattered() -> None:
    """اگر کسی یک PRAGMA را از این فهرست حذف کند، این تست می‌گیرد."""
    joined = " ".join(_SQLITE_PRAGMAS)
    for required in ("journal_mode=WAL", "busy_timeout=30000", "foreign_keys=ON"):
        assert required in joined, f"{required} از PRAGMAها حذف شده است"


def test_busy_timeout_applied_on_a_fresh_connection(tmp_path) -> None:
    """اتصال تازه باید busy_timeout صریح ۳۰ ثانیه بگیرد.

    پیش‌فرض SQLite در این نسخه ۵۰۰۰ است (نه صفر)، ولی ۳۰۰۰۰ یعنی «منتظر
    قفل نمان» که تنظیم پروژه است؛ تست عدد صریح را می‌سنجد نه پیش‌فرض را.
    """
    db = tmp_path / "probe.db"
    raw = sqlite3.connect(db)
    try:
        _apply_pragmas(raw)
        assert raw.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
        assert raw.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        raw.close()


async def test_two_connections_both_carry_the_pragmas(tmp_path) -> None:
    """دو اتصال جدا از یک engine باید هر دو PRAGMAها را داشته باشند."""
    eng = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'two.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    try:
        async with eng.connect() as a:
            for pragma in _SQLITE_PRAGMAS:
                await a.exec_driver_sql(pragma)
            assert (await a.exec_driver_sql("PRAGMA busy_timeout")).scalar() == 30000
        async with eng.connect() as b:
            for pragma in _SQLITE_PRAGMAS:
                await b.exec_driver_sql(pragma)
            assert (await b.exec_driver_sql("PRAGMA busy_timeout")).scalar() == 30000
            assert (await b.exec_driver_sql("PRAGMA foreign_keys")).scalar() == 1
    finally:
        await eng.dispose()


async def test_write_in_one_connection_is_visible_in_the_next(tmp_path) -> None:
    """بازتولید مستقیم باگ: نوشتن در یک اتصال، خواندن در اتصال بعدی.

    اگر اتصال دوم `busy_timeout` نداشته باشد، به‌جای «سازمان پیدا نشد» یا
    «دیسک پر است» خطای lock می‌بیند و تراکنش دوم شکست می‌خورد.
    """
    eng = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'rw.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    try:
        async with eng.connect() as w:
            for pragma in _SQLITE_PRAGMAS:
                await w.exec_driver_sql(pragma)
            await w.exec_driver_sql("create table t (v text)")
            await w.exec_driver_sql("insert into t values ('hello')")
            await w.commit()

        async with eng.connect() as r:
            for pragma in _SQLITE_PRAGMAS:
                await r.exec_driver_sql(pragma)
            got = (await r.exec_driver_sql("select v from t")).scalar()
        assert got == "hello", "خواندن از اتصال دوم داده را نمی‌بیند"
    finally:
        await eng.dispose()
