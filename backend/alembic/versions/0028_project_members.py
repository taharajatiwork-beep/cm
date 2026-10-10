"""چند عضو روی یک پروژه."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import table_exists

revision = "0028_project_members"
down_revision = "0027_role_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "work_project_member"):
        return
    op.create_table(
        "work_project_member",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("work_project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "user_id", name="uq_work_project_member"),
    )


def downgrade() -> None:
    op.drop_table("work_project_member")
