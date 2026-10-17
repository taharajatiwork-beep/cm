"""کلید API وردست در pm_integration."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import column_exists, table_exists

revision = "0047_vardast_integration"
down_revision = "0046_novinhub_integration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "pm_integration"):
        return
    if not column_exists(bind, "pm_integration", "vardast_token"):
        op.add_column("pm_integration", sa.Column("vardast_token", sa.Text(), nullable=False, server_default=""))
    if not column_exists(bind, "pm_integration", "vardast_snapshot"):
        op.add_column("pm_integration", sa.Column("vardast_snapshot", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    bind = op.get_bind()
    if column_exists(bind, "pm_integration", "vardast_snapshot"):
        op.drop_column("pm_integration", "vardast_snapshot")
    if column_exists(bind, "pm_integration", "vardast_token"):
        op.drop_column("pm_integration", "vardast_token")
