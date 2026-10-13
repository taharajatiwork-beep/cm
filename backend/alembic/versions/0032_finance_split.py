"""price.approve و expense.pay؛ ستون‌های تأیید تحویل و manager_ok_by."""

import uuid

import sqlalchemy as sa

from alembic import op
from app.db.migration_guard import column_exists, table_exists

revision = "0032_finance_split"
down_revision = "0031_content_calendar"
branch_labels = None
depends_on = None


def _ensure_perm(bind, code: str, description: str) -> str:
    row = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}).fetchone()
    if row:
        return row[0]
    perm_id = uuid.uuid4().hex
    bind.execute(
        sa.text("INSERT INTO permissions (id, code, description) VALUES (:id, :code, :description)"),
        {"id": perm_id, "code": code, "description": description},
    )
    return perm_id


def _grant_like(bind, source_code: str, target_id: str) -> None:
    source = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": source_code}).fetchone()
    if not source:
        return
    roles = bind.execute(
        sa.text("SELECT role_id FROM role_permissions WHERE permission_id = :pid"),
        {"pid": source[0]},
    ).fetchall()
    for (role_id,) in roles:
        have = bind.execute(
            sa.text("SELECT 1 FROM role_permissions WHERE role_id = :role AND permission_id = :perm"),
            {"role": role_id, "perm": target_id},
        ).fetchone()
        if not have:
            bind.execute(
                sa.text("INSERT INTO role_permissions (id, role_id, permission_id) VALUES (:id, :role, :perm)"),
                {"id": uuid.uuid4().hex, "role": role_id, "perm": target_id},
            )
    grants = bind.execute(
        sa.text("SELECT user_id FROM user_permission_grants WHERE permission_id = :pid"),
        {"pid": source[0]},
    ).fetchall()
    for (user_id,) in grants:
        have = bind.execute(
            sa.text("SELECT 1 FROM user_permission_grants WHERE user_id = :uid AND permission_id = :perm"),
            {"uid": user_id, "perm": target_id},
        ).fetchone()
        if not have:
            bind.execute(
                sa.text("INSERT INTO user_permission_grants (id, user_id, permission_id) VALUES (:id, :uid, :perm)"),
                {"id": uuid.uuid4().hex, "uid": user_id, "perm": target_id},
            )


def upgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "permissions"):
        approve_id = _ensure_perm(bind, "price.approve", "تأیید قیمت و پست")
        pay_id = _ensure_perm(bind, "expense.pay", "پرداخت هزینه")
        report_id = _ensure_perm(bind, "report.read", "گزارش تیم یا شعبه")
        _grant_like(bind, "price.write", approve_id)
        _grant_like(bind, "price.write", pay_id)
        _grant_like(bind, "event.read", report_id)
    if table_exists(bind, "pm_payment_request") and not column_exists(bind, "pm_payment_request", "manager_ok_by"):
        op.add_column("pm_payment_request", sa.Column("manager_ok_by", sa.Uuid(), nullable=True))
    if table_exists(bind, "work_project"):
        if not column_exists(bind, "work_project", "requester_acceptance"):
            op.add_column("work_project", sa.Column("requester_acceptance", sa.String(20), nullable=True))
        if not column_exists(bind, "work_project", "requester_acceptance_note"):
            op.add_column("work_project", sa.Column("requester_acceptance_note", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if table_exists(bind, "work_project"):
        if column_exists(bind, "work_project", "requester_acceptance_note"):
            op.drop_column("work_project", "requester_acceptance_note")
        if column_exists(bind, "work_project", "requester_acceptance"):
            op.drop_column("work_project", "requester_acceptance")
    if table_exists(bind, "pm_payment_request") and column_exists(bind, "pm_payment_request", "manager_ok_by"):
        op.drop_column("pm_payment_request", "manager_ok_by")
