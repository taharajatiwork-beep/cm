"""قفل وضعیت همگام‌سازی شیت."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import table_exists

revision = "0030_perf_sync_state"
down_revision = "0029_campaign_thread"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "perf_sync_state"):
        return
    op.create_table(
        "perf_sync_state",
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("running", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("started_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.String(40), nullable=False, server_default=""),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("perf_sync_state")
