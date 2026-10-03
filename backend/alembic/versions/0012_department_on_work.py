"""بخش روی پروژه، پرونده و کمپین — تا کار فروش با بازاریابی قاطی نشود."""

from alembic import op
import sqlalchemy as sa

from app.db.migration_guard import column_exists

revision = "0012_department_on_work"
down_revision = "0011_audit_hash_chain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in ("work_items", "cases", "campaigns"):
        if column_exists(bind, table, "department_id"):
            continue
        op.add_column(table, sa.Column("department_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    for table in ("campaigns", "cases", "work_items"):
        op.drop_column(table, "department_id")
