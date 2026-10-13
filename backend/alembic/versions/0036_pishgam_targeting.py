"""ممیزی کال پیشگام و جدول‌های مرجع استان، شهر و دستگاه."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import table_exists

revision = "0036_pishgam_targeting"
down_revision = "0035_campaign_seq_export"
branch_labels = None
depends_on = None


def _ref(name: str, *extra: sa.Column) -> None:
    bind = op.get_bind()
    if table_exists(bind, name):
        return
    op.create_table(
        name,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("remote_id", sa.Integer(), nullable=False),
        *extra,
        sa.Column("name", sa.String(120), nullable=False, server_default=""),
        sa.UniqueConstraint("organization_id", "remote_id", name=f"uq_{name}"),
    )


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "pm_pishgam_audit"):
        op.create_table(
            "pm_pishgam_audit",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("method", sa.String(8), nullable=False),
            sa.Column("endpoint", sa.String(160), nullable=False),
            sa.Column("is_mutating", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("request_hash", sa.String(64), nullable=False, server_default=""),
            sa.Column("status_code", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    _ref("pm_ref_province")
    _ref("pm_ref_city", sa.Column("province_remote_id", sa.Integer(), nullable=False))
    _ref("pm_ref_device_brand")
    _ref("pm_ref_device_type")


def downgrade() -> None:
    bind = op.get_bind()
    for name in (
        "pm_ref_device_type",
        "pm_ref_device_brand",
        "pm_ref_city",
        "pm_ref_province",
        "pm_pishgam_audit",
    ):
        if table_exists(bind, name):
            op.drop_table(name)
