"""Telegram staff channel tables and account fields."""

from alembic import op
import sqlalchemy as sa


revision = "0005_telegram_staff"
down_revision = "0004_vehicle_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Expand telegram_accounts
    with op.batch_alter_table("telegram_accounts") as batch:
        batch.add_column(sa.Column("provider", sa.String(20), nullable=False, server_default="telegram"))
        batch.add_column(sa.Column("link_code_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("notify_prefs", sa.Text(), nullable=True))
        batch.add_column(sa.Column("quiet_start_hour", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("quiet_end_hour", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("digest_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))

    op.create_table(
        "telegram_processed_updates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("provider", sa.String(20), nullable=False, server_default="telegram"),
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "update_id", name="uq_tg_processed_update"),
    )
    op.create_table(
        "telegram_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False, server_default="telegram"),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("buttons_json", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "telegram_pending_confirms",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False, server_default="telegram"),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("telegram_pending_confirms")
    op.drop_table("telegram_outbox")
    op.drop_table("telegram_processed_updates")
    with op.batch_alter_table("telegram_accounts") as batch:
        batch.drop_column("digest_enabled")
        batch.drop_column("quiet_end_hour")
        batch.drop_column("quiet_start_hour")
        batch.drop_column("notify_prefs")
        batch.drop_column("disabled_at")
        batch.drop_column("link_code_expires_at")
        batch.drop_column("provider")
