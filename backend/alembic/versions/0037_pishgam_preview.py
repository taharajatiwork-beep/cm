"""ذخیرهٔ آخرین پیش‌نمایش هدف‌گیری هوشمند."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import table_exists

revision = "0037_pishgam_preview"
down_revision = "0036_pishgam_targeting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "pm_pishgam_preview"):
        return
    op.create_table(
        "pm_pishgam_preview",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", name="uq_pm_pishgam_preview_org"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "pm_pishgam_preview"):
        return
    op.drop_table("pm_pishgam_preview")
