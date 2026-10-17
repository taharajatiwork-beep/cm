"""بردهای کانبان دستهٔ میزیتو + جای ستون روی پروژه."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import column_exists, table_exists

revision = "0043_mizito_lane_boards"
down_revision = "0042_work_project_mizito_lane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "work_mizito_lane_board"):
        op.create_table(
            "work_mizito_lane_board",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("lane_slug", sa.String(length=40), nullable=False),
            sa.Column("board_id", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("organization_id", "lane_slug", "board_id", name="uq_work_mizito_lane_board"),
        )
    if not column_exists(bind, "work_project", "mizito_board_id"):
        op.add_column("work_project", sa.Column("mizito_board_id", sa.String(length=64), nullable=True))
    if not column_exists(bind, "work_project", "mizito_board_position"):
        op.add_column("work_project", sa.Column("mizito_board_position", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if column_exists(bind, "work_project", "mizito_board_position"):
        op.drop_column("work_project", "mizito_board_position")
    if column_exists(bind, "work_project", "mizito_board_id"):
        op.drop_column("work_project", "mizito_board_id")
    if table_exists(bind, "work_mizito_lane_board"):
        op.drop_table("work_mizito_lane_board")
