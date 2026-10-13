"""ADR 005: seed و نقش‌های دمو بدون price.write."""

from sqlalchemy import select

from app.core.permissions import PermissionCode, ROLE_TEMPLATES, admin_role_permission_codes
from app.models import Role, User
from app.services import get_user_permissions


def test_admin_bootstrap_codes_exclude_price_write():
    assert PermissionCode.PRICE_WRITE not in admin_role_permission_codes()


def test_role_templates_never_grant_price_write():
    for _code, (_name, _scope, perms) in ROLE_TEMPLATES.items():
        assert PermissionCode.PRICE_WRITE not in perms


async def test_seeded_users_lack_price_write(db, seeded):
    users = (await db.scalars(select(User).where(User.organization_id == seeded["org"].id))).all()
    for user in users:
        perms = await get_user_permissions(db, user)
        assert PermissionCode.PRICE_WRITE not in perms


async def test_seeded_roles_lack_price_write(db, seeded):
    from app.models import Permission, RolePermission

    rows = await db.execute(
        select(Role.code, Permission.code)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(Role.organization_id == seeded["org"].id)
    )
    for _role_code, perm_code in rows.all():
        assert perm_code != PermissionCode.PRICE_WRITE
