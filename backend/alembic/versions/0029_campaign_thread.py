"""ستون گفتگوی کمپین پرفورمنس."""

import sqlalchemy as sa

from alembic import op

revision = "0029_campaign_thread"
down_revision = "0028_project_members"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "conversations" not in inspector.get_table_names():
        return
    names = {column["name"] for column in inspector.get_columns("conversations")}
    if "pm_campaign_id" not in names:
        op.add_column("conversations", sa.Column("pm_campaign_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "pm_campaign_id")
