"""قیمت خودرو و ساعت پست — تأیید مالی قبل از انتشار."""

from alembic import op
import sqlalchemy as sa

from app.db.migration_guard import column_exists, table_exists

revision = "0013_pricing_slots"
down_revision = "0012_department_on_work"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "vehicles"):
        alters = [
            ("price_updated_at", sa.DateTime(timezone=True)),
            ("price_updated_by", sa.Uuid()),
            ("stock_updated_at", sa.DateTime(timezone=True)),
            ("stock_updated_by", sa.Uuid()),
            ("delivery_note", sa.String(255)),
        ]
        for name, col in alters:
            if not column_exists(bind, "vehicles", name):
                op.add_column("vehicles", sa.Column(name, col, nullable=True))
    if not table_exists(bind, "vehicle_prices"):
        op.create_table(
            "vehicle_prices",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("vehicle_id", sa.Uuid(), sa.ForeignKey("vehicles.id"), nullable=False),
            sa.Column("amount", sa.BigInteger(), nullable=False),
            sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column("note", sa.String(255)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if not table_exists(bind, "post_slots"):
        op.create_table(
            "post_slots",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("vehicle_id", sa.Uuid(), sa.ForeignKey("vehicles.id"), nullable=False),
            sa.Column("post_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("slot_type", sa.String(40), nullable=False, server_default="video"),
            sa.Column("channel", sa.String(40)),
            sa.Column("requester_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("status", sa.String(30), nullable=False, server_default="requested"),
            sa.Column("confirmed_price", sa.BigInteger()),
            sa.Column("confirmed_by", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column("confirmed_at", sa.DateTime(timezone=True)),
            sa.Column("reminded_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("post_slots")
    op.drop_table("vehicle_prices")
    for name in (
        "delivery_note",
        "stock_updated_by",
        "stock_updated_at",
        "price_updated_by",
        "price_updated_at",
    ):
        op.drop_column("vehicles", name)
