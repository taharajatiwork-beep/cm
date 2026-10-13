"""شمارندهٔ کد کمپین در DB؛ ستون export شیت منبع برای idempotency."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import column_exists, table_exists

revision = "0035_campaign_seq_export"
down_revision = "0034_finance_ok_status"
branch_labels = None
depends_on = None

_EXPORT_COL = "source_sheet_exported_at"


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "pm_campaign_sequence"):
        op.create_table(
            "pm_campaign_sequence",
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), primary_key=True),
            sa.Column("next_seq", sa.Integer(), nullable=False, server_default="0"),
        )
    for table in ("pm_campaign", "pm_cost", "pm_sms_send", "pm_story"):
        if table_exists(bind, table) and not column_exists(bind, table, _EXPORT_COL):
            op.add_column(table, sa.Column(_EXPORT_COL, sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("pm_story", "pm_sms_send", "pm_cost", "pm_campaign"):
        if table_exists(bind, table) and column_exists(bind, table, _EXPORT_COL):
            op.drop_column(table, _EXPORT_COL)
    if table_exists(bind, "pm_campaign_sequence"):
        op.drop_table("pm_campaign_sequence")
