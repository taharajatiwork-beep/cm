"""درخواست‌ها ماژول مستقل شد: جدول pm_request به work_request تغییر نام یافت."""

from alembic import op
from app.db.migration_guard import table_exists

revision = "0022_work_request"
down_revision = "0021_pm_request"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "pm_request") and not table_exists(bind, "work_request"):
        op.rename_table("pm_request", "work_request")


def downgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "work_request") and not table_exists(bind, "pm_request"):
        op.rename_table("work_request", "pm_request")