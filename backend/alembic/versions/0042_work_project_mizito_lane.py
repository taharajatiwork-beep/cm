"""دستهٔ میزیتو روی پروژهٔ کار (مارکتینگ)."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import column_exists

revision = "0042_work_project_mizito_lane"
down_revision = "0041_ai_lab_followups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not column_exists(bind, "work_project", "mizito_lane"):
        op.add_column("work_project", sa.Column("mizito_lane", sa.String(length=40), nullable=True))
    if not column_exists(bind, "work_project", "mizito_card_id"):
        op.add_column("work_project", sa.Column("mizito_card_id", sa.String(length=64), nullable=True))
    if not column_exists(bind, "work_project", "mizito_project_id"):
        op.add_column("work_project", sa.Column("mizito_project_id", sa.String(length=64), nullable=True))
    if not column_exists(bind, "work_project", "mizito_board"):
        op.add_column("work_project", sa.Column("mizito_board", sa.String(length=200), nullable=True))
    if not column_exists(bind, "work_project", "mizito_status"):
        op.add_column("work_project", sa.Column("mizito_status", sa.String(length=40), nullable=True))
    op.create_index(
        "ix_work_project_mizito_lane",
        "work_project",
        ["organization_id", "mizito_lane"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "uq_work_project_mizito_card",
        "work_project",
        ["organization_id", "mizito_card_id"],
        unique=True,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("uq_work_project_mizito_card", table_name="work_project", if_exists=True)
    op.drop_index("ix_work_project_mizito_lane", table_name="work_project", if_exists=True)
    bind = op.get_bind()
    for col in ("mizito_status", "mizito_board", "mizito_project_id", "mizito_card_id", "mizito_lane"):
        if column_exists(bind, "work_project", col):
            op.drop_column("work_project", col)
