"""توکن وب‌سرویس نوین‌هاب در pm_integration."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import column_exists, table_exists

revision = "0046_novinhub_integration"
down_revision = "0045_calendar_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "pm_integration"):
        return
    if not column_exists(bind, "pm_integration", "novinhub_token"):
        op.add_column("pm_integration", sa.Column("novinhub_token", sa.Text(), nullable=False, server_default=""))
    if not column_exists(bind, "pm_integration", "novinhub_snapshot"):
        op.add_column("pm_integration", sa.Column("novinhub_snapshot", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    bind = op.get_bind()
    if column_exists(bind, "pm_integration", "novinhub_snapshot"):
        op.drop_column("pm_integration", "novinhub_snapshot")
    if column_exists(bind, "pm_integration", "novinhub_token"):
        op.drop_column("pm_integration", "novinhub_token")
