"""پیش‌نویس‌های کمپین از درخواست‌های میزیتو و نشانهٔ خواندن هر گفتگو (فقط شماره، نه متن)."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import table_exists

revision = "0018_mizito_requests"
down_revision = "0017_mizito_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "pm_mizito_cursor"):
        op.create_table(
            "pm_mizito_cursor",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("source_key", sa.String(120), nullable=False),
            sa.Column("position", sa.Integer(), nullable=True),
            sa.Column("stamp", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("organization_id", "source_key", name="uq_pm_mizito_cursor_source"),
        )
    if not table_exists(bind, "pm_mizito_request"):
        op.create_table(
            "pm_mizito_request",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("source_key", sa.String(160), nullable=False),
            sa.Column("source_kind", sa.String(20), nullable=False, server_default="dialog"),
            sa.Column("source_id", sa.String(64), nullable=False, server_default=""),
            sa.Column("source_title", sa.String(120), nullable=False, server_default=""),
            sa.Column("msg_index", sa.Integer(), nullable=True),
            sa.Column("kind", sa.String(20), nullable=False, server_default="start"),
            sa.Column("status", sa.String(20), nullable=False, server_default="new"),
            sa.Column("fields", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("excerpt", sa.String(400), nullable=False, server_default=""),
            sa.Column("digest", sa.String(40), nullable=False, server_default=""),
            sa.Column("author_id", sa.String(64), nullable=False, server_default=""),
            sa.Column("happened_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("campaign_id", sa.Uuid(), sa.ForeignKey("pm_campaign.id", ondelete="SET NULL"), nullable=True),
            sa.Column("decided_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("organization_id", "source_key", name="uq_pm_mizito_request_source"),
        )
    # 0014 جدول‌های pm_ را از روی مدل‌ها می‌سازد، پس ممکن است جدول از قبل باشد ولی ایندکس نه.
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("pm_mizito_request")}
    if "ix_pm_mizito_request_org_status" not in indexes:
        op.create_index("ix_pm_mizito_request_org_status", "pm_mizito_request", ["organization_id", "status"])


def downgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "pm_mizito_request"):
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes("pm_mizito_request")}
        if "ix_pm_mizito_request_org_status" in indexes:
            op.drop_index("ix_pm_mizito_request_org_status", table_name="pm_mizito_request")
        op.drop_table("pm_mizito_request")
    if table_exists(bind, "pm_mizito_cursor"):
        op.drop_table("pm_mizito_cursor")
