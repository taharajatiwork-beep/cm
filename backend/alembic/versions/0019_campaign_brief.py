"""بریف کمپین: ستون JSON روی pm_campaign."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import table_exists

revision = "0019_campaign_brief"
down_revision = "0018_mizito_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "pm_campaign"):
        return
    cols = {item["name"] for item in sa.inspect(bind).get_columns("pm_campaign")}
    if "brief" not in cols:
        op.add_column("pm_campaign", sa.Column("brief", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "pm_campaign"):
        return
    cols = {item["name"] for item in sa.inspect(bind).get_columns("pm_campaign")}
    if "brief" in cols:
        op.drop_column("pm_campaign", "brief")