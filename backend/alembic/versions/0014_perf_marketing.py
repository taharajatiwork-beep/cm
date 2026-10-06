"""جدول‌های پرفورمنس مارکتینگ (پیشوند pm_)."""

from alembic import op

from app.db.migration_guard import table_exists

revision = "0014_perf_marketing"
down_revision = "0013_pricing_slots"
branch_labels = None
depends_on = None


def _pm_tables():
    import app.perf.models  # noqa: F401
    from app.db.base import Base

    return [table for table in Base.metadata.sorted_tables if table.name.startswith("pm_")]


def upgrade() -> None:
    bind = op.get_bind()
    for table in _pm_tables():
        if not table_exists(bind, table.name):
            table.create(bind)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(_pm_tables()):
        if table_exists(bind, table.name):
            table.drop(bind)
