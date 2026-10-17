"""روزانهٔ سوشال، sync run، لینک اکانت/کانال."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import table_exists

revision = "0049_social_daily_sync"
down_revision = "0048_social_rollup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "pm_social_sync_run"):
        op.create_table(
            "pm_social_sync_run",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        )
    if not table_exists(bind, "pm_social_daily"):
        op.create_table(
            "pm_social_daily",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("day", sa.Date(), nullable=False),
            sa.Column("comments_open_est", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("conversations_open_est", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("comments_sampled", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("conversations_sampled", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("accounts_needing_login", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("vardast_chat_credit", sa.Integer(), nullable=True),
            sa.Column("vardast_channel_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metrics_json", sa.Text(), nullable=False, server_default=""),
            sa.UniqueConstraint("organization_id", "day", name="uq_pm_social_daily_org_day"),
        )
    if not table_exists(bind, "pm_social_account_link"):
        op.create_table(
            "pm_social_account_link",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("novinhub_account_id", sa.String(64), nullable=False),
            sa.Column("page_id", sa.Uuid(), sa.ForeignKey("pm_page.id", ondelete="SET NULL"), nullable=True),
            sa.UniqueConstraint("organization_id", "novinhub_account_id", name="uq_pm_social_account_link"),
        )
    if not table_exists(bind, "pm_vardast_channel_link"):
        op.create_table(
            "pm_vardast_channel_link",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("vardast_channel_id", sa.String(64), nullable=False),
            sa.Column("campaign_id", sa.Uuid(), sa.ForeignKey("pm_campaign.id", ondelete="SET NULL"), nullable=True),
            sa.UniqueConstraint("organization_id", "vardast_channel_id", name="uq_pm_vardast_channel_link"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "pm_vardast_channel_link"):
        op.drop_table("pm_vardast_channel_link")
    if table_exists(bind, "pm_social_account_link"):
        op.drop_table("pm_social_account_link")
    if table_exists(bind, "pm_social_daily"):
        op.drop_table("pm_social_daily")
    if table_exists(bind, "pm_social_sync_run"):
        op.drop_table("pm_social_sync_run")
