"""AI Lab workspaces (role tabs) and task-kind registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

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

PERF_KINDS = ("period_review", "campaign_review", "channel_budget", "sms_copy_review")
MANAGER_KINDS = ("projects_health", "team_load")
FINANCE_KINDS = ("finance_reconcile",)
TEAM_KINDS = ("my_work_review",)

ALL_KINDS = (*PERF_KINDS, *MANAGER_KINDS, *FINANCE_KINDS, *TEAM_KINDS)


@dataclass(frozen=True)
class WorkspaceDef:
    key: str
    label_en: str
    label_fa: str
    kinds: tuple[str, ...]
    private: bool
    allowed: Callable[[AuthContext], bool]


def _is_admin(auth: AuthContext) -> bool:
    return PermissionCode.ORG_ADMIN in auth.permissions


def _can_performance(auth: AuthContext) -> bool:
    if _is_admin(auth):
        return True
    if _role_code(auth) == "performance_marketing":
        return True
    return _is_performance_user(auth)


def _can_manager(auth: AuthContext) -> bool:
    if _is_admin(auth):
        return True
    if _role_code(auth) == "marketing_manager":
        return True
    return PermissionCode.PERF_APPROVE in auth.permissions


def _can_finance(auth: AuthContext) -> bool:
    if _is_admin(auth):
        return True
    return _role_code(auth) == "finance"


def _can_team(auth: AuthContext) -> bool:
    if _is_admin(auth):
        return True
    role = _role_code(auth)
    return role in ("marketing", "designer", "filmmaker")


WORKSPACES: tuple[WorkspaceDef, ...] = (
    WorkspaceDef(
        key="performance",
        label_en="Performance",
        label_fa="پرفورمنس",
        kinds=PERF_KINDS,
        private=False,
        allowed=_can_performance,
    ),
    WorkspaceDef(
        key="manager",
        label_en="Marketing manager",
        label_fa="مدیر مارکتینگ",
        kinds=MANAGER_KINDS,
        private=False,
        allowed=_can_manager,
    ),
    WorkspaceDef(
        key="finance",
        label_en="Finance",
        label_fa="مالی",
        kinds=FINANCE_KINDS,
        private=False,
        allowed=_can_finance,
    ),
    WorkspaceDef(
        key="team",
        label_en="My work",
        label_fa="کار من",
        kinds=TEAM_KINDS,
        private=True,
        allowed=_can_team,
    ),
)


def visible_workspaces(auth: AuthContext) -> list[WorkspaceDef]:
    return [ws for ws in WORKSPACES if ws.allowed(auth)]


def allowed_kinds(auth: AuthContext) -> set[str]:
    kinds: set[str] = set()
    for ws in visible_workspaces(auth):
        kinds.update(ws.kinds)
    return kinds


def workspace_for_kind(kind: str) -> str | None:
    for ws in WORKSPACES:
        if kind in ws.kinds:
            return ws.key
    return None


def is_private_kind(kind: str) -> bool:
    for ws in WORKSPACES:
        if kind in ws.kinds:
            return ws.private
    return False


def workspaces_payload(auth: AuthContext) -> list[dict]:
    out: list[dict] = []
    for ws in visible_workspaces(auth):
        out.append(
            {
                "key": ws.key,
                "label_en": ws.label_en,
                "label_fa": ws.label_fa,
                "kinds": list(ws.kinds),
                "private": ws.private,
            }
        )
    return out
