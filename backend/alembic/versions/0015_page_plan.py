"""وضعیت انتشار استوری: قرار قبلی‌ها منتشرشده می‌مانند."""

from alembic import op
import sqlalchemy as sa

from app.db.migration_guard import column_exists, table_exists

revision = "0015_page_plan"
down_revision = "0014_perf_marketing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "pm_story") and not column_exists(bind, "pm_story", "status"):
        op.add_column(
            "pm_story",
            sa.Column("status", sa.String(length=20), nullable=False, server_default="published"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if column_exists(bind, "pm_story", "status"):
        op.drop_column("pm_story", "status")
