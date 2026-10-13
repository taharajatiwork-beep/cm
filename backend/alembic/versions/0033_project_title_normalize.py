"""عنوان پروژه را از الگوی «موضوع — نام تیم» جدا می‌کند."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import table_exists
from app.requests.project_title import project_title_without_team_suffix

revision = "0033_project_title_normalize"
down_revision = "0032_finance_split"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not table_exists(bind, "work_project") or not table_exists(bind, "teams"):
        return
    rows = bind.execute(
        sa.text(
            """
            SELECT wp.id, wp.title, t.name AS team_name
            FROM work_project wp
            LEFT JOIN teams t ON t.id = wp.team_id
            WHERE wp.team_id IS NOT NULL AND wp.title LIKE '% — %'
            """
        )
    ).fetchall()
    for row_id, title, team_name in rows:
        new_title = project_title_without_team_suffix(title or "", team_name)
        if new_title != title:
            bind.execute(
                sa.text("UPDATE work_project SET title = :title WHERE id = :id"),
                {"title": new_title, "id": row_id},
            )


def downgrade() -> None:
    # دادهٔ تفکیک‌شده را بدون snapshot برنمی‌گردانیم.
    pass
