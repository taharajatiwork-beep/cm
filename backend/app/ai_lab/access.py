"""Who may use AI Lab (pilot) — aligned with frontend canSeeAiLab."""

from __future__ import annotations

from app.ai_lab.workspaces import allowed_kinds as _allowed_kinds, visible_workspaces
from app.api.deps import AuthContext
from app.core.permissions import PermissionCode


def _role_code(auth: AuthContext) -> str | None:
    return auth.user.role.code if auth.user.role else None


def _is_performance_user(auth: AuthContext) -> bool:
    if _role_code(auth) == "performance_marketing":
        return True
    perms = auth.permissions
    return (
        PermissionCode.PERF_WRITE in perms
        and PermissionCode.PERF_APPROVE not in perms
        and PermissionCode.ORG_ADMIN not in perms
    )


def can_use_ai_lab(auth: AuthContext) -> bool:
    return bool(visible_workspaces(auth))


def allowed_kinds(auth: AuthContext) -> set[str]:
    return _allowed_kinds(auth)


def is_org_admin(auth: AuthContext) -> bool:
    return PermissionCode.ORG_ADMIN in auth.permissions


def require_kind_allowed(auth: AuthContext, kind: str) -> None:
    if kind not in allowed_kinds(auth):
        raise AuthorizationError("This analysis type is not available for your role")


def task_visible(auth: AuthContext, row) -> bool:
    if row.kind not in allowed_kinds(auth):
        return False
    from app.ai_lab.workspaces import is_private_kind

    if is_private_kind(row.kind) and not is_org_admin(auth):
        return row.created_by == auth.user.id
    return True
