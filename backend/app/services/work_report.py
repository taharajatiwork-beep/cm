"""گزارش کار با محدودسازی scope. از پرفورمنس import نمی‌کند."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import PermissionCode
from app.models import Task, TaskAssignee, User
from app.models.enums import TaskRole, TaskStatus
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
    project_id: UUID | None = None,
    request_id: UUID | None = None,
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
        project_ids = {row.id for row in projects}
        request_ids = {row.id for row in requests}
        tasks = [
            row
            for row in tasks
            if row.project_id in project_ids or row.request_id in request_ids or row.owner_id == user.id
        ]
    elif scope in ("team", "team_tree") and team_ids is not None:
        requests = [row for row in requests if row.team_id in team_ids]
        projects = [row for row in projects if row.team_id in team_ids]
    if request_id is not None:
        requests = [row for row in requests if row.id == request_id]
        projects = [row for row in projects if row.request_id == request_id]
    if project_id is not None:
        projects = [row for row in projects if row.id == project_id]
        linked = {row.request_id for row in projects if row.request_id}
        requests = [row for row in requests if row.id in linked]
        tasks = [row for row in tasks if row.project_id == project_id]
    elif scope != "org":
        scoped_projects = {row.id for row in projects}
        scoped_requests = {row.id for row in requests}
        tasks = [
            row
            for row in tasks
            if row.project_id in scoped_projects or row.request_id in scoped_requests
        ]
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
    names, assignees = await _names(db, tasks)
    focused = project_id is not None or request_id is not None
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
        "trend": _weekly(requests, projects, tasks),
        "request_rows": _request_rows(requests, projects, tasks, names, assignees, with_tasks=focused),
        "rows": [
            {
                "id": str(row.id),
                "kind": "request",
                "title": row.title,
                "status": row.status,
                "href": f"/reports?request={row.id}",
            }
            for row in requests[:40]
        ]
        + [
            {
                "id": str(row.id),
                "kind": "project",
                "title": row.title,
                "status": row.status,
                "href": f"/reports?project={row.id}",
            }
            for row in projects[:40]
        ],
    }


def _open(task: Task) -> bool:
    return task.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)


def _overdue(task: Task, now: datetime) -> bool:
    deadline = _aware(task.deadline)
    return _open(task) and deadline is not None and deadline < now


def _task_out(task: Task, names: dict[UUID, str], assignees: dict[UUID, str], now: datetime) -> dict:
    status = task.status.value if hasattr(task.status, "value") else str(task.status)
    return {
        "id": str(task.id),
        "title": task.title,
        "status": status,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "person": assignees.get(task.id) or names.get(task.owner_id) or "",
        "overdue": _overdue(task, now),
    }


def _request_rows(
    requests: list[WorkRequest],
    projects: list[WorkProject],
    tasks: list[Task],
    names: dict[UUID, str],
    assignees: dict[UUID, str],
    *,
    with_tasks: bool,
) -> list[dict]:
    now = datetime.now(UTC)
    by_request: dict[UUID, list[WorkProject]] = {}
    loose: list[WorkProject] = []
    for project in projects:
        if project.request_id:
            by_request.setdefault(project.request_id, []).append(project)
        else:
            loose.append(project)
    by_project: dict[UUID, list[Task]] = {}
    for task in tasks:
        if task.project_id:
            by_project.setdefault(task.project_id, []).append(task)

    def project_out(project: WorkProject) -> dict:
        rows = by_project.get(project.id, [])
        done = sum(1 for row in rows if row.status == TaskStatus.COMPLETED)
        body = {
            "id": str(project.id),
            "code": project.code,
            "title": project.title,
            "status": project.status,
            "kind": project.kind,
            "done": done,
            "total": len(rows),
            "overdue": sum(1 for row in rows if _overdue(row, now)),
        }
        if with_tasks:
            body["tasks"] = [_task_out(row, names, assignees, now) for row in rows]
        return body

    out = []
    for request in requests:
        packed = [project_out(child) for child in by_request.get(request.id, [])]
        out.append(
            {
                "id": str(request.id),
                "code": request.code,
                "title": request.title,
                "status": request.status,
                "kind": request.kind,
                "done": sum(item["done"] for item in packed),
                "total": sum(item["total"] for item in packed),
                "projects": packed,
            }
        )
    if loose:
        packed = [project_out(child) for child in loose]
        out.append(
            {
                "id": "",
                "code": "",
                "title": "پروژه‌های بدون درخواست",
                "status": "in_progress",
                "kind": "",
                "done": sum(item["done"] for item in packed),
                "total": sum(item["total"] for item in packed),
                "projects": packed,
            }
        )
    return out


async def _names(db: AsyncSession, tasks: list[Task]) -> tuple[dict[UUID, str], dict[UUID, str]]:
    owner_ids = {row.owner_id for row in tasks}
    links = []
    if tasks:
        links = list(
            (
                await db.scalars(
                    select(TaskAssignee).where(
                        TaskAssignee.task_id.in_([row.id for row in tasks]),
                        TaskAssignee.role == TaskRole.ASSIGNEE,
                    )
                )
            ).all()
        )
    user_ids = owner_ids | {row.user_id for row in links}
    users = {}
    if user_ids:
        users = {
            row.id: row.full_name
            for row in (await db.scalars(select(User).where(User.id.in_(user_ids)))).all()
        }
    assignees = {row.task_id: users.get(row.user_id, "") for row in links}
    return users, assignees


def _allowed_scopes(user: User, permissions: set[str]) -> set[str]:
    if PermissionCode.ORG_ADMIN in permissions:
        return {"me", "team", "team_tree", "org"}
    allowed = {"me"}
    if PermissionCode.REPORT_READ in permissions and user.team_id:
        allowed.add("team")
    if PermissionCode.REQUEST_TRIAGE in permissions or PermissionCode.REQUEST_MANAGE in permissions:
        allowed.add("team_tree")
    return allowed


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _weekly(requests: list, projects: list, tasks: list) -> list[dict]:
    now = datetime.now(UTC)
    points = []
    for week in range(5, -1, -1):
        start = now - timedelta(days=7 * (week + 1))
        end = now - timedelta(days=7 * week)

        def inside(value: datetime | None) -> bool:
            stamp = _aware(value)
            return stamp is not None and start <= stamp < end

        points.append(
            {
                "label": start.date().isoformat(),
                "requests": sum(1 for row in requests if inside(row.created_at)),
                "projects": sum(1 for row in projects if inside(row.created_at)),
                "done_tasks": sum(
                    1 for row in tasks if row.status == TaskStatus.COMPLETED and inside(row.completed_at)
                ),
            }
        )
    return points


async def _scope_teams(db: AsyncSession, user: User, scope: str) -> list[UUID] | None:
    if scope == "org" or scope == "me" or not user.team_id:
        return None
    if scope == "team":
        return [user.team_id]
    return await child_team_ids(db, [user.team_id])

