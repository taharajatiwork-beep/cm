"""Add customers table + FK from work/cases/conversations."""

from alembic import op
import sqlalchemy as sa


revision = "0002_customers"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(40)),
        sa.Column("email", sa.String(255)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "phone"),
    )
    # Soft-link columns already exist as Uuid; add FKs where supported
    for table in ("conversations", "work_items", "cases"):
        try:
            op.create_foreign_key(
                f"fk_{table}_customer_id",
                table,
                "customers",
                ["customer_id"],
                ["id"],
            )
        except Exception:
            pass


def downgrade() -> None:
    for table in ("conversations", "work_items", "cases"):
        try:
            op.drop_constraint(f"fk_{table}_customer_id", table, type_="foreignkey")
        except Exception:
            pass
    op.drop_table("customers")
