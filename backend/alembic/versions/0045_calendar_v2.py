"""تقویم v2: رویداد ساعت‌دار، تولید محتوا، تکرار، مناسبت‌ها."""

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import column_exists, table_exists

revision = "0045_calendar_v2"
down_revision = "0044_mizito_sync_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    entry_cols = [
        ("entry_type", sa.String(20), "content"),
        ("title", sa.String(400), ""),
        ("start_time", sa.Time(), None),
        ("end_time", sa.Time(), None),
        ("all_day", sa.Boolean(), True),
        ("location", sa.String(200), ""),
        ("notes", sa.Text(), ""),
        ("production_status", sa.String(20), "idea"),
        ("published_url", sa.String(400), ""),
        ("recurrence", sa.String(20), "none"),
        ("recur_until", sa.Date(), None),
        ("recurrence_parent_id", sa.Uuid(), None),
    ]
    for name, col_type, default in entry_cols:
        if not column_exists(bind, "calendar_entry", name):
            if default is None:
                op.add_column("calendar_entry", sa.Column(name, col_type, nullable=True))
            elif isinstance(default, bool):
                op.add_column(
                    "calendar_entry",
                    sa.Column(name, col_type, nullable=False, server_default=sa.text("true" if default else "false")),
                )
            else:
                op.add_column(
                    "calendar_entry",
                    sa.Column(name, col_type, nullable=False, server_default=default),
                )
    if column_exists(bind, "calendar_entry", "recurrence_parent_id"):
        # FK added only if column fresh — safe on sqlite/pg
        pass

    if not table_exists(bind, "calendar_entry_attendee"):
        op.create_table(
            "calendar_entry_attendee",
            sa.Column("entry_id", sa.Uuid(), sa.ForeignKey("calendar_entry.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        )
    if not table_exists(bind, "calendar_occasion"):
        op.create_table(
            "calendar_occasion",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=True),
            sa.Column("on_date", sa.Date(), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("kind", sa.String(20), nullable=False, server_default="marketing"),
            sa.Column("is_off", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_calendar_occasion_date", "calendar_occasion", ["on_date"])


def downgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "calendar_occasion"):
        op.drop_table("calendar_occasion")
    if table_exists(bind, "calendar_entry_attendee"):
        op.drop_table("calendar_entry_attendee")
    for name in (
        "recurrence_parent_id",
        "recur_until",
        "recurrence",
        "published_url",
        "production_status",
        "notes",
        "location",
        "all_day",
        "end_time",
        "start_time",
        "title",
        "entry_type",
    ):
        if column_exists(bind, "calendar_entry", name):
            op.drop_column("calendar_entry", name)
