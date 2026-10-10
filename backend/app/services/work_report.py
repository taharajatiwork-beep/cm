"""گزارش کار با محدودسازی scope. از پرفورمنس import نمی‌کند."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import PermissionCode
from app.models import Task, User
from app.models.enums import TaskStatus
from app.requests.models import WorkProject, WorkRequest
from app.requests.spine import child_team_ids


async def work_report(
    db: AsyncSession,
    *,
    organization_id: UUID,
    user: User,
    permissions: set[str],
    scope: str,
    group_by: str,
) -> dict:
    allowed = _allowed_scopes(user, permissions)
    if scope not in allowed:
        raise PermissionError(scope)
    if group_by == "person" and scope == "me":
        raise PermissionError("person")
    requests = list(
        (await db.scalars(select(WorkRequest).where(WorkRequest.organization_id == organization_id))).all()
    )
    projects = list(
        (await db.scalars(select(WorkProject).where(WorkProject.organization_id == organization_id))).all()
    )
    tasks = list((await db.scalars(select(Task).where(Task.organization_id == organization_id))).all())
    team_ids = await _scope_teams(db, user, scope)
    if scope == "me":
        requests = [row for row in requests if row.requested_by == user.id]
        projects = [row for row in projects if row.request_id in {item.id for item in requests} or row.lead_user_id == user.id]
        tasks = [row for row in tasks if row.owner_id == user.id]
    elif scope in ("team", "team_tree") and team_ids is not None:
        requests = [row for row in requests if row.team_id in team_ids]
        projects = [row for row in projects if row.team_id in team_ids]
    by_status: dict[str, int] = {}
    for row in requests:
        by_status[row.status] = by_status.get(row.status, 0) + 1
    by_kind: dict[str, int] = {}
    for row in projects:
        by_kind[row.kind] = by_kind.get(row.kind, 0) + 1
    open_tasks = [row for row in tasks if row.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)]
    from app.expenses.spend import recorded_for_projects

    spent = await recorded_for_projects(db, organization_id, {row.id for row in projects})
    planned = sum(row.planned_budget or 0 for row in projects)
    return {
        "scope": scope,
        "allowed": sorted(allowed),
        "group_by": group_by,
        "requests": len(requests),
        "requests_by_status": by_status,
        "projects": len(projects),
        "projects_by_kind": by_kind,
        "open_tasks": len(open_tasks),
        "done_tasks": len(tasks) - len(open_tasks),
        "planned_budget": planned,
        "recorded_cost": spent,
    }


def _allowed_scopes(user: User, permissions: set[str]) -> set[str]:
    if PermissionCode.ORG_ADMIN in permissions:
        return {"me", "team", "team_tree", "org"}
    scopes = {"me"}
    if user.team_id:
        scopes.add("team")
    if PermissionCode.REQUEST_TRIAGE in permissions or PermissionCode.REQUEST_MANAGE in permissions:
        scopes.add("team_tree")
    return scopes


async def _scope_teams(db: AsyncSession, user: User, scope: str) -> list[UUID] | None:
    if scope == "org" or scope == "me" or not user.team_id:
        return None
    if scope == "team":
        return [user.team_id]
    return await child_team_ids(db, [user.team_id])

