"""آخرین لیست کارت‌های میزیتو که از صفحهٔ پول خوانده شده."""

from alembic import op
import sqlalchemy as sa

from app.db.migration_guard import column_exists, table_exists

revision = "0017_mizito_snapshot"
down_revision = "0016_perf_integration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "pm_integration"):
        return
    if not column_exists(bind, "pm_integration", "mizito_snapshot"):
        op.add_column("pm_integration", sa.Column("mizito_snapshot", sa.Text(), nullable=False, server_default=""))
    if not column_exists(bind, "pm_integration", "mizito_read_at"):
        op.add_column("pm_integration", sa.Column("mizito_read_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if column_exists(bind, "pm_integration", "mizito_read_at"):
        op.drop_column("pm_integration", "mizito_read_at")
    if column_exists(bind, "pm_integration", "mizito_snapshot"):
        op.drop_column("pm_integration", "mizito_snapshot")
