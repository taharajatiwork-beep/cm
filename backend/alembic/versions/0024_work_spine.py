"""وظیفه و گفتگو به پروژه/درخواست، پیوست، مهلت و بودجهٔ پروژه."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import column_exists, table_exists

revision = "0024_work_spine"
down_revision = "0023_work_project"
branch_labels = None
depends_on = None


def _add(table: str, name: str, column: sa.Column) -> None:
    bind = op.get_bind()
    if not table_exists(bind, table):
        return
    if not column_exists(bind, table, name):
        op.add_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()
    _add("tasks", "project_id", sa.Column("project_id", sa.Uuid(), nullable=True))
    _add("tasks", "request_id", sa.Column("request_id", sa.Uuid(), nullable=True))
    _add("conversations", "project_id", sa.Column("project_id", sa.Uuid(), nullable=True))
    _add("conversations", "request_id", sa.Column("request_id", sa.Uuid(), nullable=True))
    _add("messages", "task_id", sa.Column("task_id", sa.Uuid(), nullable=True))
    _add("messages", "perf_campaign_id", sa.Column("perf_campaign_id", sa.Uuid(), nullable=True))
    _add("work_project", "due_date", sa.Column("due_date", sa.Date(), nullable=True))
    _add("work_project", "planned_budget", sa.Column("planned_budget", sa.BigInteger(), nullable=True))
    _add("work_project", "lead_user_id", sa.Column("lead_user_id", sa.Uuid(), nullable=True))
    if not table_exists(bind, "work_attachment"):
        op.create_table(
            "work_attachment",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Uuid(), nullable=True),
            sa.Column("request_id", sa.Uuid(), nullable=True),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("url", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("kind", sa.String(length=40), nullable=False, server_default="link"),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "work_attachment"):
        op.drop_table("work_attachment")
    for table, names in {
        "tasks": ("project_id", "request_id"),
        "conversations": ("project_id", "request_id"),
        "messages": ("task_id", "perf_campaign_id"),
        "work_project": ("due_date", "planned_budget", "lead_user_id"),
    }.items():
        if not table_exists(bind, table):
            continue
        for name in names:
            if column_exists(bind, table, name):
                op.drop_column(table, name)
