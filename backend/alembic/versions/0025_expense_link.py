"""اتصال هزینه به پروژه یا درخواست، و دادن مجوز هزینه به نقش‌های price.write."""

import uuid

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import column_exists, table_exists

revision = "0025_expense_link"
down_revision = "0024_work_spine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "pm_payment_request"):
        for name in ("project_id", "request_id", "team_id"):
            if not column_exists(bind, "pm_payment_request", name):
                op.add_column("pm_payment_request", sa.Column(name, sa.Uuid(), nullable=True))
    if not table_exists(bind, "permissions"):
        return
    for code, description in (
        ("expense.request", "درخواست هزینه"),
        ("expense.approve", "تأیید هزینه"),
    ):
        existing = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}).fetchone()
        if existing:
            perm_id = existing[0]
        else:
            perm_id = uuid.uuid4().hex
            bind.execute(
                sa.text("INSERT INTO permissions (id, code, description) VALUES (:id, :code, :description)"),
                {"id": perm_id, "code": code, "description": description},
            )
        price = bind.execute(sa.text("SELECT id FROM permissions WHERE code = 'price.write'")).fetchone()
        if not price:
            continue
        roles = bind.execute(
            sa.text("SELECT role_id FROM role_permissions WHERE permission_id = :pid"),
            {"pid": price[0]},
        ).fetchall()
        for (role_id,) in roles:
            have = bind.execute(
                sa.text(
                    "SELECT 1 FROM role_permissions WHERE role_id = :role AND permission_id = :perm"
                ),
                {"role": role_id, "perm": perm_id},
            ).fetchone()
            if not have:
                bind.execute(
                    sa.text(
                        "INSERT INTO role_permissions (id, role_id, permission_id) VALUES (:id, :role, :perm)"
                    ),
                    {"id": uuid.uuid4().hex, "role": role_id, "perm": perm_id},
                )


def downgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "pm_payment_request"):
        for name in ("project_id", "request_id", "team_id"):
            if column_exists(bind, "pm_payment_request", name):
                op.drop_column("pm_payment_request", name)
