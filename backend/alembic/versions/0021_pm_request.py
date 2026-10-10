"""درخواست مدیر به تیم: جدول pm_request."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import table_exists

revision = "0021_pm_request"
down_revision = "0020_sms_message_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "pm_request"):
        op.create_table(
            "pm_request",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("code", sa.String(length=40), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("kind", sa.String(length=40), nullable=False, server_default="عمومی"),
            sa.Column("priority", sa.String(length=20), nullable=False, server_default="normal"),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("requested_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id"), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="new"),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("organization_id", "code", name="uq_pm_request_code"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "pm_request"):
        op.drop_table("pm_request")