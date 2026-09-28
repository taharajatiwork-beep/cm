"""Data retention: conversations.archived_at (stage 6).

آرشیو فقط این فلد را پر می‌کند؛ topic دست‌نخورده می‌ماند.
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_data_retention"
down_revision = "0006_enterprise"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db.migration_guard import column_exists

    if column_exists(op.get_bind(), "conversations", "archived_at"):
        return
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("archived_at")
