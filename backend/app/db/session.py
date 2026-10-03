from collections.abc import AsyncGenerator

from sqlalchemy import event
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

# PRAGMAهای SQLite به «اتصال» گره خورده‌اند نه به فایل، پس باید روی هر
# اتصال تازه اعمال شوند. اجرای یک‌بارهٔ آن‌ها در startup کافی نیست: استخر
# اتصال (به‌خاطر `pool_pre_ping`) اتصال‌های قدیمی را دوباره برمی‌گرداند و آن‌ها
# `busy_timeout` ندارند — نتیجه‌اش خطای گاه‌به‌گاه «database is locked» و
# «database is locked»/«no such table» زیر بار هم‌زمان است.
_SQLITE_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA busy_timeout=30000",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA foreign_keys=ON",
)

if _is_sqlite:

    def _install_sqlite_pragmas(target_engine) -> None:  # noqa: ANN001
        @event.listens_for(target_engine.sync_engine, "connect")
        def _sqlite_pragmas_on_connect(dbapi_conn, _record) -> None:  # noqa: ANN001
            cur = dbapi_conn.cursor()
            try:
                for pragma in _SQLITE_PRAGMAS:
                    cur.execute(pragma)
            finally:
                cur.close()

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_autocommit_on_connect(dbapi_conn, _record) -> None:  # noqa: ANN001
        # حالت autocommit: SQLAlchemy خودش BEGIN صادر می‌کند (رویداد begin
        # پایین) تا نوع شروع تراکنش قابل کنترل باشد.
        dbapi_conn.isolation_level = None

    @event.listens_for(engine.sync_engine, "begin")
    def _sqlite_begin_immediate(conn) -> None:  # noqa: ANN001
        # BEGIN (deferred) در SQLite کلاسیک: تراکنش اول SELECT می‌خواند و
        # بعد می‌خواهد بنویسد — اگر در این فاصله نویسندهٔ دیگری commit کرده
        # باشد، upgrade قفل با خطای فوری «database is locked» می‌میرد
        # (deadlock snapshot). با BEGIN IMMEDIATE قفل نوشتن از ابتدای تراکنش
        # گرفته می‌شود و نویسنده‌های رقیب تا ۳۰ ثانیه (busy_timeout) صف
        # می‌شوند؛ خواننده‌ها در WAL دست‌نخورده می‌مانند.
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    _install_sqlite_pragmas(engine)


AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# انجین جدا برای حلقه‌های پس‌زمینه: BEGIN عادی (deferred) نه IMMEDIATE.
# حلقه‌های worker عمدتاً می‌خوانند؛ با deferred قفل نوشتن فقط در اولین
# نوشتن گرفته می‌شود (حین انتظار شبکه بلاک نمی‌شود) و اگر بین خواندن و
# نوشتن نویسندهٔ دیگری commit کند، خطای فوری می‌گیرند که در سیکل بعدی
# جبران می‌شود — در عوض هرگز برای یک SELECT ساده قفل نوشتن نمی‌گیرند
# و درخواست‌های API را گرسنه نمی‌کنند.
if _is_sqlite:
    worker_engine = create_async_engine(
        _settings.database_url,
        echo=False,
        connect_args=_connect_args,
        **_engine_kwargs,
    )
    _install_sqlite_pragmas(worker_engine)
    WorkerSessionLocal = async_sessionmaker(
        worker_engine, class_=AsyncSession, expire_on_commit=False
    )
else:
    worker_engine = engine
    WorkerSessionLocal = AsyncSessionLocal


async def _tune_sqlite() -> None:
    """journal_mode روی فایل است (نه اتصال) و فقط توسط اتصال‌های تازه ست می‌شود.

    PRAGMAهای per-connection از طریق hook بالا اعمال می‌شوند؛ این تابع فقط
    تضمین می‌کند WAL یک‌بار روی فایل اعمال شده باشد و اتصال‌های از پیش
    ساخته‌شده دور ریخته شوند.
    """
    if not _is_sqlite:
        return
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    await engine.dispose()  # اتصال‌های تازه با PRAGMAهای درست برقرار می‌شوند
    await worker_engine.dispose()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
