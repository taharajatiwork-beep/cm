"""Who may use AI Lab (pilot) — aligned with frontend canSeeAiLab."""

from __future__ import annotations

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
    perms = auth.permissions
    if PermissionCode.ORG_ADMIN in perms:
        return True
    if _role_code(auth) == "finance":
        return False
    if _is_performance_user(auth):
        return True
    if PermissionCode.PERF_WRITE in perms or PermissionCode.PERF_APPROVE in perms:
        return True
    return False
