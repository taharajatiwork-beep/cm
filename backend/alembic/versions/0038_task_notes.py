"""task notes and deliverables"""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import table_exists

revision = "0038_task_notes"
down_revision = "0037_pishgam_preview"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "task_notes"):
        return
    op.create_table(
        "task_notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("kind", sa.String(32), nullable=False, server_default="comment"),
        sa.Column("body", sa.Text()),
        sa.Column("url", sa.Text()),
        sa.Column("file_path", sa.Text()),
        sa.Column("file_name", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_task_notes_task_id", "task_notes", ["task_id"])
    op.create_index("ix_task_notes_organization_id", "task_notes", ["organization_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "task_notes"):
        return
    op.drop_index("ix_task_notes_organization_id", table_name="task_notes")
    op.drop_index("ix_task_notes_task_id", table_name="task_notes")
    op.drop_table("task_notes")
