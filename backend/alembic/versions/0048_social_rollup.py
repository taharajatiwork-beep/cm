"""خلاصهٔ تحلیلی نوین‌هاب/وردست در pm_integration."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import column_exists, table_exists

revision = "0048_social_rollup"
down_revision = "0047_vardast_integration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "pm_integration"):
        return
    if not column_exists(bind, "pm_integration", "social_rollup_json"):
        op.add_column("pm_integration", sa.Column("social_rollup_json", sa.Text(), nullable=False, server_default=""))
    if not column_exists(bind, "pm_integration", "social_rollup_at"):
        op.add_column("pm_integration", sa.Column("social_rollup_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if column_exists(bind, "pm_integration", "social_rollup_at"):
        op.drop_column("pm_integration", "social_rollup_at")
    if column_exists(bind, "pm_integration", "social_rollup_json"):
        op.drop_column("pm_integration", "social_rollup_json")
