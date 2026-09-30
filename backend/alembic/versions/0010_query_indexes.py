"""ایندکس برای جدول‌هایی که با رشد داده کوئری می‌خورند.

پیش از این مایگریشن، تنها یک ایندکس (`ai_audit`) در کل مدل‌ها وجود داشت.
جدول‌هایی مثل `messages` و `conversations` با هر پیام جدید بزرگ می‌شوند و
کوئری‌های اصلی روی `conversation_id` و `created_at` فیلتر و مرتب می‌کنند —
بدون ایندکس، هر بار اسکن کامل جدول انجام می‌شود.

SQLite-safe: اگر ایندکس از قبل وجود داشته باشد، `IF NOT EXISTS` می‌گوید.
"""

from alembic import op
from sqlalchemy import text

from app.db.migration_guard import table_exists

revision = "0010_query_indexes"
down_revision = "0009_ops_ux"
branch_labels = None
depends_on = None


# (جدول, ستون‌ها) — ترتیب ستون‌ها مهم است: ستونِ selective‌تر اول.
# ایندکس ترکیبی فقط وقتی مفید است که کوئری همان ترتیب را داشته باشد.
INDEXES: list[tuple[str, str, tuple[str, ...]]] = [
    # پیام‌های یک گفتگو، مرتب‌شده بر اساس زمان — هستهٔ صفحهٔ گفتگو
    ("messages", "ix_messages_conversation_created", ("conversation_id", "created_at")),
    # لیست گفتگوهای یک سازمان (فیلتر archived_at و مرتب‌سازی)
    ("conversations", "ix_conversations_org_archived_created",
     ("organization_id", "archived_at", "created_at")),
    # «کارهای من»: فیلتر بر اساس مالک و وضعیت
    ("tasks", "ix_tasks_owner_status", ("owner_id", "status")),
    ("tasks", "ix_tasks_work_item", ("work_item_id",)),
    ("tasks", "ix_tasks_case", ("case_id",)),
    # شرکت‌کنندگان یک گفتگو
    ("conversation_participants", "ix_conv_participants_user",
     ("user_id", "conversation_id")),
    # لاگ ممیزی: فیلتر بر اساس کنشگر، نوع موجودیت و بازهٔ زمانی
    ("audit_logs", "ix_audit_actor_created", ("actor_id", "created_at")),
    ("audit_logs", "ix_audit_entity_created", ("entity_type", "entity_id")),
    # اعلان‌های کاربر
    ("notifications", "ix_notifications_user_created", ("user_id", "created_at")),
    # outbox تلگرام: صف بر اساس وضعیت
    ("telegram_outbox", "ix_outbox_status_created", ("status", "created_at")),
    # idempotency: کلید یکتا باید سریع پیدا شود
    ("idempotency_records", "ix_idempotency_key", ("key",)),
    # آگهی‌های دیوار: فیلتر وضعیت و خطای آخر
    ("divar_listings", "ix_divar_status", ("status",)),
    # رزرو خودرو بین شعب — وضعیت روی خودِ vehicles است، نه روی این جدول پل
    ("vehicles", "ix_vehicles_status", ("status",)),
    ("vehicle_branches", "ix_vehicle_branches_branch_vehicle", ("branch_id", "vehicle_id")),
]


def _columns_exist(bind, table: str, columns: tuple[str, ...]) -> bool:
    """همهٔ ستون‌های ایندکس در جدول هستند؟

    محافظ لازم است چون مایگریشن‌های قدیمی ممکن است جدولی را با ستون‌های
    کمتر ساخته باشند (و مهاجرت‌های دیگر guard می‌گذارند). ساخت ایندکس روی
    ستون ناموجود، کل مهاجرت را می‌شکند.
    """
    from app.db.migration_guard import column_exists

    return all(column_exists(bind, table, column) for column in columns)


def upgrade() -> None:
    bind = op.get_bind()
    for table, index_name, columns in INDEXES:
        if not table_exists(bind, table):
            continue
        if not _columns_exist(bind, table, columns):
            continue
        cols = ", ".join(columns)
        bind.execute(
            text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({cols})")
        )


def downgrade() -> None:
    bind = op.get_bind()
    for _table, index_name, _columns in reversed(INDEXES):
        bind.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
