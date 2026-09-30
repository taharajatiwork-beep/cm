from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_settings = get_settings()
_is_sqlite = _settings.database_url.startswith("sqlite")

if _is_sqlite:
    # SQLite تنها یک نویسنده را هم‌زمان قبول می‌کند. بدون این سه تنظیم،
    # دو درخواست هم‌زمان روی فایل دیتابیس به «database is locked»
    # می‌خورند — حتی در محیط توسعه.
    #   timeout      — چقدر منتظر قفل بمانیم (ثانیه)
    #   journal_mode — WAL اجازهٔ خواندن حین نوشتن را می‌دهد
    #   busy_timeout — سطح SQLite، مکمل همان timeout
    _connect_args = {
        "check_same_thread": False,
        "timeout": 30,
    }
    _engine_kwargs: dict[str, object] = {"pool_pre_ping": True}
else:
    _connect_args = {}
    _engine_kwargs = {"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True}

engine = create_async_engine(
    _settings.database_url,
    echo=_settings.debug and not _is_sqlite,
    connect_args=_connect_args,
    **_engine_kwargs,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _tune_sqlite() -> None:
    """WAL و busy_timeout را برای هر اتصال فعال می‌کند.

    PRAGMAها به «اتصال» گره خورده‌اند نه به فایل، پس باید روی هر
    اتصال جدید اجرا شوند — وگرنه فقط اولین درخواست آن‌ها را دارد.
    """
    if not _is_sqlite:
        return
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA busy_timeout=30000")
        await conn.exec_driver_sql("PRAGMA synchronous=NORMAL")
    await engine.dispose()  # اتصال جدید با PRAGMAهای تازه برقرار می‌شود


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
