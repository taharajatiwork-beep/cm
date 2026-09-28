"""Divar listing last_error after HTTP retries (stage 10).

SQLite-safe: a nullable text column only. No PostgreSQL types.
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_divar_last_error"
down_revision = "0007_data_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db.migration_guard import column_exists

    if column_exists(op.get_bind(), "divar_listings", "last_error"):
        return
    with op.batch_alter_table("divar_listings") as batch:
        batch.add_column(sa.Column("last_error", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("divar_listings") as batch:
        batch.drop_column("last_error")
