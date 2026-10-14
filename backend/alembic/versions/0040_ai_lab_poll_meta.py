"""ai lab last_polled_at for GitHub polling"""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import column_exists

revision = "0040_ai_lab_poll_meta"
down_revision = "0039_ai_lab_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not column_exists(bind, "ai_tasks", "last_polled_at"):
        op.add_column("ai_tasks", sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if column_exists(bind, "ai_tasks", "last_polled_at"):
        op.drop_column("ai_tasks", "last_polled_at")
