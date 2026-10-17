"""جزئیات میزیتو روی پروژه، لاگ تغییر، و اجرای همگام‌سازی."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import column_exists, table_exists

revision = "0044_mizito_sync_state"
down_revision = "0043_mizito_lane_boards"
branch_labels = None
depends_on = None

_PROJECT_COLS = (
    ("mizito_hash", sa.String(length=64)),
    ("mizito_code", sa.String(length=40)),
    ("mizito_assignee_ids", sa.Text()),
)
_PROJECT_INTS = (
    "mizito_progress",
    "mizito_checklist_done",
    "mizito_checklist_total",
    "mizito_attachments",
    "mizito_missing_runs",
)
_PROJECT_TIMES = (
    "mizito_created_at",
    "mizito_modified_at",
    "mizito_completed_at",
    "mizito_deadline",
    "mizito_removed_at",
)


def upgrade() -> None:
    bind = op.get_bind()
    if not column_exists(bind, "work_project", "mizito_weight"):
        op.add_column("work_project", sa.Column("mizito_weight", sa.Float(), nullable=True))
    for name, typ in _PROJECT_COLS:
        if not column_exists(bind, "work_project", name):
            op.add_column("work_project", sa.Column(name, typ, nullable=True))
    for name in _PROJECT_INTS:
        if not column_exists(bind, "work_project", name):
            op.add_column("work_project", sa.Column(name, sa.Integer(), nullable=True))
    for name in _PROJECT_TIMES:
        if not column_exists(bind, "work_project", name):
            op.add_column("work_project", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    if not column_exists(bind, "work_project", "mizito_has_comments"):
        op.add_column("work_project", sa.Column("mizito_has_comments", sa.Boolean(), nullable=True))
    if not column_exists(bind, "work_project", "hidden_in_cm"):
        op.add_column(
            "work_project",
            sa.Column("hidden_in_cm", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if not column_exists(bind, "work_mizito_lane_board", "removed"):
        op.add_column(
            "work_mizito_lane_board",
            sa.Column("removed", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if not column_exists(bind, "tasks", "external_ref"):
        op.add_column("tasks", sa.Column("external_ref", sa.String(length=80), nullable=True))
        op.create_index("ix_tasks_external_ref", "tasks", ["external_ref"], unique=False)
    if not table_exists(bind, "work_mizito_change"):
        op.create_table(
            "work_mizito_change",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Uuid(), nullable=True),
            sa.Column("kind", sa.String(length=20), nullable=False),
            sa.Column("field", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("old_value", sa.Text(), nullable=False, server_default=""),
            sa.Column("new_value", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="applied"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("decided_by", sa.Uuid(), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not table_exists(bind, "work_mizito_sync_run"):
        op.create_table(
            "work_mizito_sync_run",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("error", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("unchanged_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("pending_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("truncated_projects", sa.Text(), nullable=False, server_default=""),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "work_mizito_sync_run"):
        op.drop_table("work_mizito_sync_run")
    if table_exists(bind, "work_mizito_change"):
        op.drop_table("work_mizito_change")
    if column_exists(bind, "tasks", "external_ref"):
        op.drop_index("ix_tasks_external_ref", table_name="tasks")
        op.drop_column("tasks", "external_ref")
    if column_exists(bind, "work_mizito_lane_board", "removed"):
        op.drop_column("work_mizito_lane_board", "removed")
    for name in (
        "hidden_in_cm",
        "mizito_has_comments",
        "mizito_removed_at",
        "mizito_deadline",
        "mizito_completed_at",
        "mizito_modified_at",
        "mizito_created_at",
        "mizito_missing_runs",
        "mizito_attachments",
        "mizito_checklist_total",
        "mizito_checklist_done",
        "mizito_progress",
        "mizito_assignee_ids",
        "mizito_code",
        "mizito_hash",
        "mizito_weight",
    ):
        if column_exists(bind, "work_project", name):
            op.drop_column("work_project", name)
