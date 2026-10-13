"""وضعیت legacy finance_ok را به manager_ok (منتظر مالی) تبدیل می‌کند."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import table_exists

revision = "0034_finance_ok_status"
down_revision = "0033_project_title_normalize"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "pm_payment_request"):
        return
    bind.execute(
        sa.text(
            """
            UPDATE pm_payment_request
            SET status = 'manager_ok', updated_at = CURRENT_TIMESTAMP
            WHERE status = 'finance_ok'
            """
        )
    )


def downgrade() -> None:
    pass
