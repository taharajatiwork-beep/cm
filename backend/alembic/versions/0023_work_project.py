"""پروژه (تیم از درخواست می‌سازد) + سلسله‌مراتب تیم + کمپین متعلق به پروژه."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import column_exists, table_exists

revision = "0023_work_project"
down_revision = "0022_work_request"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "work_project"):
        op.create_table(
            "work_project",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("code", sa.String(length=40), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("kind", sa.String(length=40), nullable=False, server_default="عمومی"),
            sa.Column("request_id", sa.Uuid(), sa.ForeignKey("work_request.id", ondelete="SET NULL"), nullable=True),
            sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id"), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="new"),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("organization_id", "code", name="uq_work_project_code"),
        )
    if table_exists(bind, "teams") and not column_exists(bind, "teams", "parent_team_id"):
        op.add_column("teams", sa.Column("parent_team_id", sa.Uuid(), nullable=True))
    if table_exists(bind, "pm_campaign") and not column_exists(bind, "pm_campaign", "project_id"):
        op.add_column("pm_campaign", sa.Column("project_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if column_exists(bind, "pm_campaign", "project_id"):
        op.drop_column("pm_campaign", "project_id")
    if column_exists(bind, "teams", "parent_team_id"):
        op.drop_column("teams", "parent_team_id")
    if table_exists(bind, "work_project"):
        op.drop_table("work_project")