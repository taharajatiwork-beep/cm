"""خانهٔ تیم: بخش مشترک برای درختی که زیرتیم دارد، و بخش خود تیم."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
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
    page_tree = set(await child_team_ids(db, [team.id]))
    reading_parent_hub = bool(
        ctx.user.team_id and team.id != ctx.user.team_id and ctx.user.team_id in page_tree
    )
    if visible is not None and team.id not in visible:
        if not reading_parent_hub:
            raise HTTPException(status_code=404, detail="تیم پیدا نشد")
    children = list(
        (await db.scalars(select(Team).where(Team.parent_team_id == team.id).order_by(Team.name))).all()
    )
    child_ids = [row.id for row in children]
    shared_ids = set(await child_team_ids(db, [team.id])) if children else {team.id}
    if visible is not None and not reading_parent_hub:
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
    project_ids = {str(row.id) for row in projects}
    active_campaigns = 0
    month_cost = 0
    campaigns: list[dict] = []
    try:
        campaign_rows = (
            await db.execute(text("SELECT id, code, title, project_id, status FROM pm_campaign"))
        ).all()
        for camp_id, code, title, project_id, status in campaign_rows:
            if str(project_id) not in project_ids:
                continue
            if status == "active":
                active_campaigns += 1
            campaigns.append(
                {
                    "id": str(camp_id),
                    "code": code,
                    "title": title,
                    "project_id": str(project_id) if project_id else None,
                    "status": status,
                }
            )
        start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_cost = int(
            await db.scalar(
                text(
                    "SELECT COALESCE(SUM(amount_toman), 0) FROM pm_cost "
                    "WHERE organization_id = :org AND created_at >= :start"
                ),
                {"org": str(ctx.organization_id), "start": start},
            )
            or 0
        )
    except Exception:
        active_campaigns = 0
        month_cost = 0
    shown = [row for row in children if visible is None or row.id in visible]
    request_rows = (
        [{"id": str(row.id), "code": row.code, "title": row.title, "status": row.status} for row in requests]
        if _is_triage(ctx)
        else []
    )
    return {
        "team": {"id": str(team.id), "name": team.name, "code": team.code},
        "shared": bool(shown),
        "can_edit": _is_triage(ctx),
        "own_section": visible is None or team.id == ctx.user.team_id,
        "sections": [{"id": str(row.id), "name": row.name, "code": row.code} for row in shown],
        "requests": request_rows,
        "projects": cards,
        "campaigns": campaigns,
        "counts": {
            "open_requests": sum(1 for row in request_rows if row["status"] in ("new", "in_review")),
            "active_projects": sum(1 for row in projects if row.status != "done"),
            "active_campaigns": active_campaigns,
            "month_cost": month_cost,
        },
    }