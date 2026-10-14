"""ai lab tasks table"""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import table_exists

revision = "0039_ai_lab_tasks"
down_revision = "0038_task_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "ai_tasks"):
        return
    op.create_table(
        "ai_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("input_json", sa.Text(), server_default="{}"),
        sa.Column("snapshot_json", sa.Text(), server_default="{}"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("result_json", sa.Text()),
        sa.Column("raw_result", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("rating", sa.Integer()),
        sa.Column("useful", sa.Boolean()),
        sa.Column("eval_note", sa.Text()),
        sa.Column("decisions_json", sa.Text(), server_default="{}"),
    )
    op.create_index("ix_ai_tasks_organization_id", "ai_tasks", ["organization_id"])
    op.create_index("ix_ai_tasks_created_at", "ai_tasks", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "ai_tasks"):
        return
    op.drop_index("ix_ai_tasks_created_at", table_name="ai_tasks")
    op.drop_index("ix_ai_tasks_organization_id", table_name="ai_tasks")
    op.drop_table("ai_tasks")
