"""ai lab trigger column and recommendation followups"""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import column_exists, table_exists

revision = "0041_ai_lab_followups"
down_revision = "0040_ai_lab_poll_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not column_exists(bind, "ai_tasks", "trigger"):
        op.add_column(
            "ai_tasks",
            sa.Column("trigger", sa.String(length=20), nullable=False, server_default="manual"),
        )
    if not table_exists(bind, "ai_rec_followups"):
        op.create_table(
            "ai_rec_followups",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("ai_task_id", sa.Uuid(), nullable=False),
            sa.Column("rec_id", sa.String(length=80), nullable=False),
            sa.Column("cm_task_id", sa.Uuid(), nullable=True),
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("baseline_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("followup_due_on", sa.Date(), nullable=False),
            sa.Column("followup_json", sa.Text(), nullable=True),
            sa.Column("measured_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["ai_task_id"], ["ai_tasks.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("ai_task_id", "rec_id", name="uq_ai_rec_followup_task_rec"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "ai_rec_followups"):
        op.drop_table("ai_rec_followups")
    if column_exists(bind, "ai_tasks", "trigger"):
        op.drop_column("ai_tasks", "trigger")
