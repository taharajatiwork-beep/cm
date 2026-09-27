"""Add campaigns table + conversation.campaign_id."""

from alembic import op
import sqlalchemy as sa


revision = "0003_campaigns"
down_revision = "0002_customers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "ACTIVE",
                "PAUSED",
                "COMPLETED",
                "CANCELLED",
                name="campaign_status",
            ),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("channel", sa.Enum(name="channel", create_type=False)),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("vehicle_id", sa.Uuid(), sa.ForeignKey("vehicles.id")),
        sa.Column("work_item_id", sa.Uuid(), sa.ForeignKey("work_items.id")),
        sa.Column("branch_id", sa.Uuid(), sa.ForeignKey("branches.id")),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id")),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.add_column("conversations", sa.Column("campaign_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_conversations_campaign_id",
        "conversations",
        "campaigns",
        ["campaign_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_conversations_campaign_id", "conversations", type_="foreignkey")
    op.drop_column("conversations", "campaign_id")
    op.drop_table("campaigns")
    sa.Enum(name="campaign_status").drop(op.get_bind(), checkfirst=True)
