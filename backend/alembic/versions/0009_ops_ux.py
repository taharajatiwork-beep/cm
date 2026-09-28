"""Customer stage, vehicle photos, and KPI history.

SQLite-safe. Skips objects that the 0001 baseline already created.
"""

from alembic import op
import sqlalchemy as sa

from app.db.migration_guard import column_exists, table_exists


revision = "0009_ops_ux"
down_revision = "0008_divar_last_error"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not column_exists(bind, "customers", "stage"):
        op.add_column(
            "customers",
            sa.Column("stage", sa.String(40), nullable=False, server_default="lead"),
        )
    if not table_exists(bind, "vehicle_photos"):
        op.create_table(
            "vehicle_photos",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("vehicle_id", sa.Uuid(), sa.ForeignKey("vehicles.id"), nullable=False),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("content_type", sa.String(120), nullable=False),
            sa.Column("storage_path", sa.String(500), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if not table_exists(bind, "kpi_snapshots"):
        op.create_table(
            "kpi_snapshots",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "kpi_snapshots"):
        op.drop_table("kpi_snapshots")
    if table_exists(bind, "vehicle_photos"):
        op.drop_table("vehicle_photos")
    if column_exists(bind, "customers", "stage"):
        op.drop_column("customers", "stage")
