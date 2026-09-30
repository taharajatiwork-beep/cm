"""زنجیرهٔ هش لاگ ممیزی — prev_hash و row_hash.

لاگ ممیزی پیش از این فقط در سطح API فقط-افزودنی بود؛ دسترسی مستقیم به دیتابیس
می‌توانست سطرها را UPDATE یا DELETE کند و هیچ اثری باقی نمی‌ماند. با افزودن
زنجیرهٔ SHA-256 به‌ازای هر سازمان، هر تغییر یا حذف قابل‌شناسایی می‌شود.

سطرهای قدیمی NULL می‌مانند (هش ندارند) و زنجیره از اولین سطر هش‌دار شروع
می‌شود؛ تابع راستی‌آزمایی هم سطرهای بدون هش را مبنا نمی‌گیرد.
"""

from alembic import op
import sqlalchemy as sa

from app.db.migration_guard import column_exists

revision = "0011_audit_hash_chain"
down_revision = "0010_query_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("audit_logs") as batch:
        if not column_exists(bind, "audit_logs", "prev_hash"):
            batch.add_column(sa.Column("prev_hash", sa.String(64), nullable=True))
        if not column_exists(bind, "audit_logs", "row_hash"):
            batch.add_column(sa.Column("row_hash", sa.String(64), nullable=True))
        if not column_exists(bind, "audit_logs", "chain_seq"):
            batch.add_column(
                sa.Column("chain_seq", sa.Integer(), nullable=False, server_default="0")
            )
    # راستی‌آزمایی زنجیره به ترتیب صریح نیاز دارد (created_at در SQLite
    # میلی‌ثانیه‌ای نیست و ترتیب پایدار نمی‌ماند)
    with op.batch_alter_table("audit_logs") as batch:
        if not column_exists(bind, "audit_logs", "ix_audit_chain"):
            batch.create_index(
                "ix_audit_chain",
                ["organization_id", "chain_seq"],
                unique=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("audit_logs") as batch:
        if column_exists(bind, "audit_logs", "ix_audit_chain"):
            batch.drop_index("ix_audit_chain")
        if column_exists(bind, "audit_logs", "chain_seq"):
            batch.drop_column("chain_seq")
        if column_exists(bind, "audit_logs", "row_hash"):
            batch.drop_column("row_hash")
        if column_exists(bind, "audit_logs", "prev_hash"):
            batch.drop_column("prev_hash")
