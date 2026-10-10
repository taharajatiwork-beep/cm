"""شناسهٔ ارسال پیشگام: ستون روی pm_sms_send برای حلقهٔ دلیوری."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import table_exists

revision = "0020_sms_message_id"
down_revision = "0019_campaign_brief"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "pm_sms_send"):
        return
    cols = {item["name"] for item in sa.inspect(bind).get_columns("pm_sms_send")}
    if "pishgam_message_id" not in cols:
        op.add_column("pm_sms_send", sa.Column("pishgam_message_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "pm_sms_send"):
        return
    cols = {item["name"] for item in sa.inspect(bind).get_columns("pm_sms_send")}
    if "pishgam_message_id" in cols:
        op.drop_column("pm_sms_send", "pishgam_message_id")