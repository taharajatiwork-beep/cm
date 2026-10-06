"""توکن میزیتو که از صفحهٔ اتصالات ذخیره می‌شود."""

from alembic import op

from app.db.migration_guard import table_exists

revision = "0016_perf_integration"
down_revision = "0015_page_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "pm_integration"):
        return
    import app.perf.models  # noqa: F401
    from app.db.base import Base

    Base.metadata.tables["pm_integration"].create(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "pm_integration"):
        op.drop_table("pm_integration")
