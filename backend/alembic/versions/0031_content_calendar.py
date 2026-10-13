"""تقویم محتوا: سربرگ ماه و ردیف روزانه."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import table_exists

revision = "0031_content_calendar"
down_revision = "0030_perf_sync_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "calendar_month"):
        op.create_table(
            "calendar_month",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("jalali_year", sa.Integer(), nullable=False),
            sa.Column("jalali_month", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(200), nullable=False, server_default=""),
            sa.Column("payload", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("organization_id", "jalali_year", "jalali_month", name="uq_calendar_month"),
        )
    if not table_exists(bind, "calendar_entry"):
        op.create_table(
            "calendar_entry",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("on_date", sa.Date(), nullable=False),
            sa.Column("tier", sa.String(20), nullable=False, server_default="long"),
            sa.Column("format", sa.String(80), nullable=False, server_default=""),
            sa.Column("channel", sa.String(120), nullable=False, server_default=""),
            sa.Column("topic", sa.String(400), nullable=False),
            sa.Column("cta", sa.String(200), nullable=False, server_default=""),
            sa.Column("kpi", sa.String(120), nullable=False, server_default=""),
            sa.Column("status", sa.String(20), nullable=False, server_default="todo"),
            sa.Column("campaign_id", sa.Uuid(), sa.ForeignKey("pm_campaign.id", ondelete="SET NULL"), nullable=True),
            sa.Column("assignee_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("project_id", sa.Uuid(), sa.ForeignKey("work_project.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_calendar_entry_org_date", "calendar_entry", ["organization_id", "on_date"])


def downgrade() -> None:
    op.drop_table("calendar_entry")
    op.drop_table("calendar_month")
