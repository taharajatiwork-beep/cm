"""Who can see which work projects (shared by list + kanban)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext
from app.core.permissions import PermissionCode
from app.models import Task, TaskAssignee
from app.requests.models import WorkProject, WorkProjectMember, WorkRequest


def is_triage(ctx: AuthContext) -> bool:
    return (
        PermissionCode.REQUEST_TRIAGE in ctx.permissions
        or PermissionCode.REQUEST_MANAGE in ctx.permissions
        or PermissionCode.ORG_ADMIN in ctx.permissions
    )


def is_requester_only(ctx: AuthContext) -> bool:
    return (
        PermissionCode.REQUEST_CREATE in ctx.permissions
        and not is_triage(ctx)
        and PermissionCode.TASK_READ not in ctx.permissions
    )


async def member_project_ids(db: AsyncSession, ctx: AuthContext) -> set[UUID]:
    member_ids = set(
        (await db.scalars(select(WorkProjectMember.project_id).where(WorkProjectMember.user_id == ctx.user.id))).all()
    )
    assigned = set(
        (
            await db.scalars(
                select(Task.project_id).where(
                    Task.organization_id == ctx.organization_id,
                    Task.project_id.is_not(None),
                    Task.id.in_(select(TaskAssignee.task_id).where(TaskAssignee.user_id == ctx.user.id)),
                )
            )
        ).all()
    )
    return {item for item in member_ids | assigned if item}


async def tree_ids(db: AsyncSession, ctx: AuthContext) -> set[UUID] | None:
    if PermissionCode.ORG_ADMIN in ctx.permissions:
        return None
    if not ctx.user.team_id:
        return None if is_triage(ctx) else set()
    if is_triage(ctx):
        from app.requests.spine import child_team_ids

        return set(await child_team_ids(db, [ctx.user.team_id]))
    return {ctx.user.team_id}


async def apply_project_visibility(query: Select, db: AsyncSession, ctx: AuthContext) -> Select:
    """Restrict a WorkProject select to rows the user may see."""
    if is_triage(ctx):
        pass
    else:
        clauses = []
        if PermissionCode.REQUEST_CREATE in ctx.permissions:
            mine = select(WorkRequest.id).where(
                WorkRequest.organization_id == ctx.organization_id,
                WorkRequest.requested_by == ctx.user.id,
            )
            clauses.append(WorkProject.request_id.in_(mine))
        if PermissionCode.TASK_READ in ctx.permissions:
            visible = await member_project_ids(db, ctx)
            if visible:
                clauses.append(WorkProject.id.in_(visible))
        if clauses:
            query = query.where(or_(*clauses))
        else:
            query = query.where(WorkProject.id.is_(None))
    if is_triage(ctx) and ctx.user.team_id and PermissionCode.ORG_ADMIN not in ctx.permissions:
        tree = await tree_ids(db, ctx)
        if tree is not None:
            query = query.where(WorkProject.team_id.in_(tree))
    return query


def base_visible_projects(organization_id: UUID) -> Select:
    return select(WorkProject).where(
        WorkProject.organization_id == organization_id,
        WorkProject.hidden_in_cm.is_(False),
        WorkProject.mizito_removed_at.is_(None),
    )
