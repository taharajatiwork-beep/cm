"""اسلات قیمت روی پروژه، تحویل طراحی و فیلم‌برداری."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import column_exists, table_exists

revision = "0026_work_types"
down_revision = "0025_expense_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "post_slots"):
        for name in ("project_id", "request_id"):
            if not column_exists(bind, "post_slots", name):
                op.add_column("post_slots", sa.Column(name, sa.Uuid(), nullable=True))
    if not table_exists(bind, "design_deliverable"):
        op.create_table(
            "design_deliverable",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Uuid(), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("url", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
            sa.Column("reviewer_id", sa.Uuid(), nullable=True),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    if not table_exists(bind, "shoot"):
        op.create_table(
            "shoot",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Uuid(), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("shoot_date", sa.Date(), nullable=True),
            sa.Column("location", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("people", sa.String(length=400), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="planned"),
            sa.Column("delivery_url", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "shoot"):
        op.drop_table("shoot")
    if table_exists(bind, "design_deliverable"):
        op.drop_table("design_deliverable")
    if table_exists(bind, "post_slots"):
        for name in ("project_id", "request_id"):
            if column_exists(bind, "post_slots", name):
                op.drop_column("post_slots", name)
