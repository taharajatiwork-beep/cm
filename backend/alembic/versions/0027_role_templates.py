"""قابلیت افزودنی کاربر و اطلاعیهٔ تیم."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import table_exists

revision = "0027_role_templates"
down_revision = "0026_work_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "user_permission_grants"):
        op.create_table(
            "user_permission_grants",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("permission_id", sa.Uuid(), sa.ForeignKey("permissions.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "permission_id"),
        )
    if not table_exists(bind, "team_notices"):
        op.create_table(
            "team_notices",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "team_notices"):
        op.drop_table("team_notices")
    if table_exists(bind, "user_permission_grants"):
        op.drop_table("user_permission_grants")
