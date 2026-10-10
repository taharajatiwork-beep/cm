"""خانهٔ تیم: بخش مشترک برای درختی که زیرتیم دارد، و بخش خود تیم."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user
from app.core.permissions import PermissionCode
from app.db.session import get_db
from app.models import Team
from app.requests.models import WorkProject, WorkRequest
from app.requests.routes import _is_requester_only, _is_triage, _tree_ids
from app.requests.spine import child_team_ids, progress, tasks_for

router = APIRouter(prefix="/teams", tags=["teams"])


def _summary(row: WorkProject, request_code: str, team_name: str, done: dict) -> dict:
    return {
        "id": str(row.id),
        "code": row.code,
        "title": row.title,
        "request_code": request_code,
        "team_id": str(row.team_id) if row.team_id else None,
        "team_name": team_name,
        "status": row.status,
        "due_date": row.due_date.isoformat() if row.due_date else None,
        "progress": done,
    }


@router.get("/{team_id}")
async def team_home(
    team_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if _is_requester_only(ctx):
        raise HTTPException(status_code=403, detail="مدیر پنل تیم را نمی‌بیند")
    team = await db.get(Team, team_id)
    if not team or team.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="تیم پیدا نشد")
    visible = await _tree_ids(db, ctx)
    if visible is not None and team.id not in visible:
        raise HTTPException(status_code=404, detail="تیم پیدا نشد")
    children = list(
        (await db.scalars(select(Team).where(Team.parent_team_id == team.id).order_by(Team.name))).all()
    )
    child_ids = [row.id for row in children]
    shared_ids = set(await child_team_ids(db, [team.id])) if children else {team.id}
    if visible is not None:
        shared_ids &= visible
    requests = list(
        (
            await db.scalars(
                select(WorkRequest)
                .where(WorkRequest.organization_id == ctx.organization_id, WorkRequest.team_id.in_(shared_ids or {team.id}))
                .order_by(WorkRequest.created_at.desc())
            )
        ).all()
    )
    projects = list(
        (
            await db.scalars(
                select(WorkProject)
                .where(WorkProject.organization_id == ctx.organization_id, WorkProject.team_id.in_(shared_ids or {team.id}))
                .order_by(WorkProject.created_at.desc())
            )
        ).all()
    )
    names = {row.id: row.name for row in [team, *children]}
    extra = [row.team_id for row in projects if row.team_id and row.team_id not in names]
    if extra:
        for row in (await db.scalars(select(Team).where(Team.id.in_(extra)))).all():
            names[row.id] = row.name
    req_codes = {}
    req_ids = {row.request_id for row in projects if row.request_id}
    if req_ids:
        for row in (await db.scalars(select(WorkRequest).where(WorkRequest.id.in_(req_ids)))).all():
            req_codes[row.id] = row.code
    cards = []
    for row in projects:
        tasks = await tasks_for(db, ctx.organization_id, project_id=row.id)
        cards.append(_summary(row, req_codes.get(row.request_id, ""), names.get(row.team_id, ""), progress(tasks)))
    own_section = team.id == ctx.user.team_id or _is_triage(ctx) or PermissionCode.ORG_ADMIN in ctx.permissions
    sections = []
    for child in children:
        if visible is not None and child.id not in visible:
            continue
        if not _is_triage(ctx) and PermissionCode.ORG_ADMIN not in ctx.permissions and child.id != ctx.user.team_id:
            continue
        sections.append({"id": str(child.id), "name": child.name, "code": child.code})
    return {
        "team": {"id": str(team.id), "name": team.name, "code": team.code},
        "shared": bool(children),
        "can_edit": _is_triage(ctx) and (ctx.user.team_id == team.id or PermissionCode.ORG_ADMIN in ctx.permissions),
        "requests": [
            {"id": str(row.id), "code": row.code, "title": row.title, "status": row.status}
            for row in requests
        ],
        "projects": cards,
        "sections": sections,
        "own_section": own_section,
    }
