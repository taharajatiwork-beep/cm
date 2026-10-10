"""درخواست مدیر به تیم: مستقل از پرفورمنس، برای همهٔ مدیرها و تیم‌ها."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, handle_authz
from app.core.permissions import AuthorizationError, PermissionCode, require_any_permission, require_permission
from app.db.session import get_db
from app.models import Team, User
from datetime import date, datetime
from app.requests.models import WorkProject, WorkRequest
from app.requests.schemas import ProjectIn, ProjectPatch, RequestIn, RequestPatch

router = APIRouter(prefix="/requests", tags=["requests"])

REQUEST_STATUSES = ("new", "in_review", "converted", "rejected", "done")
REQUEST_PRIORITIES = ("low", "normal", "high")
PROJECT_STATUSES = ("new", "in_progress", "done")


def _need(ctx: AuthContext, *codes: str) -> None:
    try:
        if len(codes) == 1:
            require_permission(ctx.permissions, codes[0])
        else:
            require_any_permission(ctx.permissions, *codes)
    except AuthorizationError as exc:
        raise handle_authz(exc) from exc


def _request_out(row: WorkRequest, requester_name: str = "", team_name: str = "") -> dict:
    return {
        "id": str(row.id),
        "code": row.code,
        "title": row.title,
        "description": row.description,
        "kind": row.kind,
        "priority": row.priority,
        "due_date": iso(row.due_date),
        "status": row.status,
        "requested_by": str(row.requested_by) if row.requested_by else None,
        "requester_name": requester_name,
        "team_id": str(row.team_id) if row.team_id else None,
        "team_name": team_name,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def _project_out(row: WorkProject, request_code: str = "", team_name: str = "") -> dict:
    return {
        "id": str(row.id),
        "code": row.code,
        "title": row.title,
        "description": row.description,
        "kind": row.kind,
        "request_id": str(row.request_id) if row.request_id else None,
        "request_code": request_code,
        "team_id": str(row.team_id) if row.team_id else None,
        "team_name": team_name,
        "status": row.status,
        "due_date": iso(row.due_date),
        "planned_budget": row.planned_budget,
        "lead_user_id": str(row.lead_user_id) if row.lead_user_id else None,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def iso(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)


def _is_triage(ctx: AuthContext) -> bool:
    return (
        PermissionCode.REQUEST_TRIAGE in ctx.permissions
        or PermissionCode.REQUEST_MANAGE in ctx.permissions
        or PermissionCode.ORG_ADMIN in ctx.permissions
    )


def _is_requester_only(ctx: AuthContext) -> bool:
    """قالب مدیر: درخواست و گفتگوی همان درخواست، نه صفحهٔ پروژه."""
    return PermissionCode.REQUEST_CREATE in ctx.permissions and not _is_triage(ctx) and PermissionCode.TASK_READ not in ctx.permissions


async def _tree_ids(db: AsyncSession, ctx: AuthContext) -> set[UUID] | None:
    """None یعنی کل سازمان. مجموعه یعنی فقط همین تیم‌ها."""
    if PermissionCode.ORG_ADMIN in ctx.permissions:
        return None
    if not ctx.user.team_id:
        return None if _is_triage(ctx) else set()
    if _is_triage(ctx):
        from app.requests.spine import child_team_ids

        return set(await child_team_ids(db, [ctx.user.team_id]))
    return {ctx.user.team_id}


async def _next_request_code(db: AsyncSession, organization_id: UUID) -> str:
    rows = (await db.scalars(select(WorkRequest.code).where(WorkRequest.organization_id == organization_id))).all()
    highest = 0
    for code in rows:
        digits = "".join(char for char in code if char.isdigit())
        if digits:
            highest = max(highest, int(digits))
    return f"REQ-{highest + 1:03d}"


async def _next_project_code(db: AsyncSession, organization_id: UUID) -> str:
    rows = (await db.scalars(select(WorkProject.code).where(WorkProject.organization_id == organization_id))).all()
    highest = 0
    for code in rows:
        digits = "".join(char for char in code if char.isdigit())
        if digits:
            highest = max(highest, int(digits))
    return f"PRJ-{highest + 1:03d}"


@router.get("")
async def list_requests(
    status: str = "",
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ترییج/ادمین همه را می‌بینند؛ مدیر عادی فقط درخواست‌های خودش."""
    _need(
        ctx,
        PermissionCode.REQUEST_CREATE,
        PermissionCode.REQUEST_TRIAGE,
        PermissionCode.REQUEST_MANAGE,
        PermissionCode.ORG_ADMIN,
    )
    query = select(WorkRequest).where(WorkRequest.organization_id == ctx.organization_id)
    if status:
        query = query.where(WorkRequest.status == status)
    if not _is_triage(ctx):
        query = query.where(WorkRequest.requested_by == ctx.user.id)
    elif ctx.user.team_id and PermissionCode.ORG_ADMIN not in ctx.permissions:
        tree = await _tree_ids(db, ctx)
        if tree is not None:
            query = query.where(WorkRequest.team_id.in_(tree))
    rows = (await db.scalars(query.order_by(WorkRequest.created_at.desc()))).all()
    users: dict[UUID, str] = {}
    if rows:
        ids = {row.requested_by for row in rows if row.requested_by}
        if ids:
            for user in (await db.scalars(select(User).where(User.id.in_(ids)))).all():
                users[user.id] = user.full_name
    teams: dict[UUID, str] = {}
    team_ids = {row.team_id for row in rows if row.team_id}
    if team_ids:
        for team in (await db.scalars(select(Team).where(Team.id.in_(team_ids)))).all():
            teams[team.id] = team.name
    return [_request_out(row, users.get(row.requested_by, ""), teams.get(row.team_id, "")) for row in rows]


@router.post("", status_code=201)
async def create_request(
    body: RequestIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _need(ctx, PermissionCode.REQUEST_CREATE, PermissionCode.REQUEST_TRIAGE, PermissionCode.REQUEST_MANAGE, PermissionCode.ORG_ADMIN)
    if body.priority not in REQUEST_PRIORITIES:
        raise HTTPException(status_code=422, detail="اولویت باید کم، معمولی یا بالا باشد")
    if body.team_id:
        team = await db.get(Team, body.team_id)
        if not team or team.organization_id != ctx.organization_id:
            raise HTTPException(status_code=404, detail="تیم پیدا نشد")
    row = WorkRequest(
        organization_id=ctx.organization_id,
        code=await _next_request_code(db, ctx.organization_id),
        title=body.title.strip(),
        description=(body.description or "").strip(),
        kind=body.kind.strip() or "عمومی",
        priority=body.priority,
        due_date=body.due_date,
        requested_by=ctx.user.id,
        team_id=body.team_id,
        created_by=ctx.user.id,
    )
    db.add(row)
    await db.flush()
    team_name = ""
    if row.team_id:
        team = await db.get(Team, row.team_id)
        team_name = team.name if team else ""
    return _request_out(row, team_name=team_name)


@router.patch("/{request_id}")
async def patch_request(
    request_id: UUID,
    body: RequestPatch,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """تیم ترییج وضعیت و تیم واگذارشده را عوض می‌کند؛ مدیرِ درخواست‌دهنده تا «جدید» می‌تواند ویرایش کند."""
    row = await db.get(WorkRequest, request_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="درخواست پیدا نشد")
    is_triage = _is_triage(ctx)
    is_owner = row.requested_by == ctx.user.id
    if not is_triage and not is_owner:
        raise HTTPException(status_code=403, detail="فقط تیم ترییج یا خودِ درخواست‌دهنده می‌تواند تغییر دهد")
    data = body.model_dump(exclude_unset=True)
    if not is_triage:
        forbidden = set(data) - {"title", "description", "kind", "priority", "due_date"}
        if forbidden or row.status != "new":
            raise HTTPException(status_code=403, detail="تغییر وضعیت و تیم واگذاری با تیم ترییج است")
    if "status" in data and data["status"] not in REQUEST_STATUSES:
        raise HTTPException(status_code=422, detail="وضعیت نامعتبر است")
    if "priority" in data and data["priority"] not in REQUEST_PRIORITIES:
        raise HTTPException(status_code=422, detail="اولویت نامعتبر است")
    if data.get("team_id"):
        team = await db.get(Team, data["team_id"])
        if not team or team.organization_id != ctx.organization_id:
            raise HTTPException(status_code=404, detail="تیم پیدا نشد")
    for key, value in data.items():
        if key == "title" and value is not None:
            value = value.strip()
            if not value:
                raise HTTPException(status_code=422, detail="عنوان خالی است")
        setattr(row, key, value)
    row.updated_at = now()
    await db.flush()
    return _request_out(row)


@router.delete("/{request_id}", status_code=204)
async def delete_request(
    request_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(WorkRequest, request_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="درخواست پیدا نشد")
    is_triage = _is_triage(ctx)
    if not is_triage and row.requested_by != ctx.user.id:
        raise HTTPException(status_code=403, detail="فقط تیم ترییج یا خودِ درخواست‌دهنده می‌تواند حذف کند")
    await db.delete(row)
    await db.flush()
    return Response(status_code=204)


# ---------------------------------------------------------------- پروژه‌ها (تیم از درخواست می‌سازد)


@router.get("/projects")
async def list_projects(
    request_id: UUID | None = None,
    status: str = "",
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ترییج/ادمین همه را می‌بینند؛ بقیه فقط پروژه‌های درخواست‌های خودشان."""
    _need(ctx, PermissionCode.REQUEST_CREATE, PermissionCode.REQUEST_TRIAGE, PermissionCode.REQUEST_MANAGE, PermissionCode.ORG_ADMIN)
    query = select(WorkProject).where(WorkProject.organization_id == ctx.organization_id)
    if request_id:
        query = query.where(WorkProject.request_id == request_id)
    if status:
        query = query.where(WorkProject.status == status)
    if not _is_triage(ctx):
        mine = select(WorkRequest.id).where(
            WorkRequest.organization_id == ctx.organization_id,
            WorkRequest.requested_by == ctx.user.id,
        )
        query = query.where(WorkProject.request_id.in_(mine))
    elif ctx.user.team_id and PermissionCode.ORG_ADMIN not in ctx.permissions:
        tree = await _tree_ids(db, ctx)
        if tree is not None:
            query = query.where(WorkProject.team_id.in_(tree))
    rows = (await db.scalars(query.order_by(WorkProject.created_at.desc()))).all()
    req_codes: dict[UUID, str] = {}
    req_ids = {row.request_id for row in rows if row.request_id}
    if req_ids:
        for req in (await db.scalars(select(WorkRequest).where(WorkRequest.id.in_(req_ids)))).all():
            req_codes[req.id] = req.code
    teams: dict[UUID, str] = {}
    team_ids = {row.team_id for row in rows if row.team_id}
    if team_ids:
        for team in (await db.scalars(select(Team).where(Team.id.in_(team_ids)))).all():
            teams[team.id] = team.name
    return [_project_out(row, req_codes.get(row.request_id, ""), teams.get(row.team_id, "")) for row in rows]


@router.post("/{request_id}/projects", status_code=201)
async def create_project(
    request_id: UUID,
    body: ProjectIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ترییج درخواست را به یک یا چند پروژه تبدیل می‌کند؛ وضعیت درخواست «تبدیل به پروژه» می‌شود."""
    _need(ctx, PermissionCode.REQUEST_TRIAGE, PermissionCode.REQUEST_MANAGE, PermissionCode.ORG_ADMIN)
    req = await db.get(WorkRequest, request_id)
    if not req or req.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="درخواست پیدا نشد")
    if body.status not in PROJECT_STATUSES:
        raise HTTPException(status_code=422, detail="وضعیت نامعتبر است")
    if body.team_id:
        team = await db.get(Team, body.team_id)
        if not team or team.organization_id != ctx.organization_id:
            raise HTTPException(status_code=404, detail="تیم پیدا نشد")
    row = WorkProject(
        organization_id=ctx.organization_id,
        code=await _next_project_code(db, ctx.organization_id),
        title=body.title.strip(),
        description=(body.description or "").strip(),
        kind=body.kind.strip() or "عمومی",
        request_id=req.id,
        team_id=body.team_id or req.team_id,
        status=body.status,
        due_date=req.due_date,
        created_by=ctx.user.id,
    )
    db.add(row)
    if req.status in ("new", "in_review"):
        req.status = "converted"
        req.updated_at = now()
    await db.flush()
    team_name = ""
    if row.team_id:
        team = await db.get(Team, row.team_id)
        team_name = team.name if team else ""
    return _project_out(row, req.code, team_name)


@router.patch("/projects/{project_id}")
async def patch_project(
    project_id: UUID,
    body: ProjectPatch,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _need(ctx, PermissionCode.REQUEST_TRIAGE, PermissionCode.REQUEST_MANAGE, PermissionCode.ORG_ADMIN)
    row = await db.get(WorkProject, project_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in PROJECT_STATUSES:
        raise HTTPException(status_code=422, detail="وضعیت نامعتبر است")
    if data.get("team_id"):
        team = await db.get(Team, data["team_id"])
        if not team or team.organization_id != ctx.organization_id:
            raise HTTPException(status_code=404, detail="تیم پیدا نشد")
    for key, value in data.items():
        if key == "title" and value is not None:
            value = value.strip()
            if not value:
                raise HTTPException(status_code=422, detail="عنوان خالی است")
        setattr(row, key, value)
    row.updated_at = now()
    await db.flush()
    req_code = ""
    if row.request_id:
        req = await db.get(WorkRequest, row.request_id)
        req_code = req.code if req else ""
    team_name = ""
    if row.team_id:
        team = await db.get(Team, row.team_id)
        team_name = team.name if team else ""
    return _project_out(row, req_code, team_name)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _need(ctx, PermissionCode.REQUEST_TRIAGE, PermissionCode.REQUEST_MANAGE, PermissionCode.ORG_ADMIN)
    row = await db.get(WorkProject, project_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    await db.delete(row)
    await db.flush()
    return Response(status_code=204)


@router.get("/my-work")
async def my_work_view(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _need(ctx, PermissionCode.TASK_READ, PermissionCode.REQUEST_CREATE, PermissionCode.ORG_ADMIN)
    from app.requests.spine import my_work

    return await my_work(db, ctx.organization_id, ctx.user.id)


@router.get("/team-load")
async def team_load_view(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _need(ctx, PermissionCode.TASK_READ, PermissionCode.REQUEST_TRIAGE, PermissionCode.ORG_ADMIN)
    from app.requests.spine import child_team_ids, team_load

    root = [ctx.user.team_id] if ctx.user.team_id else []
    if _is_triage(ctx) and ctx.user.team_id:
        root = await child_team_ids(db, root)
    return await team_load(db, ctx.organization_id, root)


@router.get("/projects/{project_id}")
async def project_detail(
    project_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _need(
        ctx,
        PermissionCode.REQUEST_CREATE,
        PermissionCode.REQUEST_TRIAGE,
        PermissionCode.REQUEST_MANAGE,
        PermissionCode.TASK_READ,
        PermissionCode.ORG_ADMIN,
    )
    if _is_requester_only(ctx):
        raise HTTPException(status_code=403, detail="مدیر صفحهٔ پروژه را نمی‌بیند")
    row = await db.get(WorkProject, project_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    visible = await _tree_ids(db, ctx)
    if visible is not None and row.team_id not in visible:
        raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    from app.requests.models import DesignDeliverable, Shoot, WorkAttachment
    from app.requests.spine import (
        attachment_out,
        deliverable_out,
        ensure_thread,
        progress,
        shoot_out,
        tasks_for,
        template_for,
    )

    tasks = await tasks_for(db, ctx.organization_id, project_id=row.id)
    thread = await ensure_thread(
        db, organization_id=ctx.organization_id, actor_id=ctx.user.id, project_id=row.id, topic=row.title
    )
    attachments = list(
        (
            await db.scalars(
                select(WorkAttachment).where(
                    WorkAttachment.organization_id == ctx.organization_id, WorkAttachment.project_id == row.id
                )
            )
        ).all()
    )
    designs = list((await db.scalars(select(DesignDeliverable).where(DesignDeliverable.project_id == row.id))).all())
    shoots = list((await db.scalars(select(Shoot).where(Shoot.project_id == row.id))).all())
    req_code = ""
    if row.request_id:
        req = await db.get(WorkRequest, row.request_id)
        req_code = req.code if req else ""
    team_name = ""
    if row.team_id:
        team = await db.get(Team, row.team_id)
        team_name = team.name if team else ""
    body = _project_out(row, req_code, team_name)
    body["progress"] = progress(tasks)
    body["template"] = template_for(row.kind)
    body["thread_id"] = str(thread.id)
    body["tasks"] = [
        {
            "id": str(task.id),
            "title": task.title,
            "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "owner_id": str(task.owner_id),
        }
        for task in tasks
    ]
    body["attachments"] = [attachment_out(item) for item in attachments]
    body["designs"] = [deliverable_out(item) for item in designs]
    body["shoots"] = [shoot_out(item) for item in shoots]
    from app.expenses.spend import budget_for_project

    body["budget"] = await budget_for_project(db, ctx.organization_id, row.id, int(row.planned_budget or 0))
    body["members"] = await _project_members(db, row.id)
    body["member_choices"] = await _member_choices(db, ctx.organization_id, row.team_id)
    body["campaigns"], body["campaign_choices"] = await _project_campaigns(db, ctx.organization_id, row.id)
    return body


async def _project_members(db: AsyncSession, project_id: UUID) -> list[dict]:
    from app.models import User
    from app.requests.models import WorkProjectMember

    rows = list(
        (
            await db.scalars(select(WorkProjectMember).where(WorkProjectMember.project_id == project_id))
        ).all()
    )
    if not rows:
        return []
    users = {
        user.id: user.full_name
        for user in (await db.scalars(select(User).where(User.id.in_([row.user_id for row in rows])))).all()
    }
    return [{"id": str(row.user_id), "full_name": users.get(row.user_id, "")} for row in rows]


async def _member_choices(db: AsyncSession, organization_id: UUID, team_id: UUID | None) -> list[dict]:
    from app.models import User
    from app.requests.spine import child_team_ids

    if not team_id:
        return []
    team = await db.get(Team, team_id)
    root = team.parent_team_id if team and team.parent_team_id else team_id
    people = list(
        (
            await db.scalars(
                select(User)
                .where(
                    User.organization_id == organization_id,
                    User.is_active.is_(True),
                    User.team_id.in_(await child_team_ids(db, [root])),
                )
                .order_by(User.full_name)
            )
        ).all()
    )
    return [{"id": str(user.id), "full_name": user.full_name} for user in people]


async def _project_campaigns(db: AsyncSession, organization_id: UUID, project_id: UUID) -> tuple[list[dict], list[dict]]:
    from app.core.campaigns import project_campaigns

    return await project_campaigns(db, organization_id, project_id)


@router.put("/projects/{project_id}/members")
async def set_project_members(
    project_id: UUID,
    body: dict,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """اعضای پروژه را یکجا عوض می‌کند. چند نفر می‌توانند با هم روی همان پروژه باشند."""
    _need(ctx, PermissionCode.REQUEST_TRIAGE, PermissionCode.REQUEST_MANAGE, PermissionCode.TASK_WRITE, PermissionCode.ORG_ADMIN)
    from app.models import User
    from app.requests.models import WorkProjectMember

    row = await db.get(WorkProject, project_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    user_ids: list[UUID] = []
    for item in body.get("user_ids") or []:
        try:
            user_ids.append(UUID(str(item)))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="عضو نامعتبر است") from exc
    if user_ids:
        found = list(
            (await db.scalars(select(User).where(User.organization_id == ctx.organization_id, User.id.in_(user_ids)))).all()
        )
        if len(found) != len(set(user_ids)):
            raise HTTPException(status_code=404, detail="یکی از اعضا پیدا نشد")
    existing = list((await db.scalars(select(WorkProjectMember).where(WorkProjectMember.project_id == row.id))).all())
    for member in existing:
        if member.user_id not in user_ids:
            await db.delete(member)
    have = {member.user_id for member in existing}
    for user_id in set(user_ids):
        if user_id not in have:
            db.add(WorkProjectMember(organization_id=ctx.organization_id, project_id=row.id, user_id=user_id))
    await db.flush()
    return await _project_members(db, row.id)


@router.put("/projects/{project_id}/campaigns")
async def set_project_campaigns(
    project_id: UUID,
    body: dict,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """کمپین‌های این پروژه را یکجا تعیین می‌کند. یک پروژه چند کمپین می‌گیرد."""
    _need(ctx, PermissionCode.REQUEST_TRIAGE, PermissionCode.REQUEST_MANAGE, PermissionCode.ORG_ADMIN)
    from app.core.campaigns import set_project_campaigns

    row = await db.get(WorkProject, project_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    campaign_ids: list[UUID] = []
    for item in body.get("campaign_ids") or []:
        try:
            campaign_ids.append(UUID(str(item)))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="کمپین نامعتبر است") from exc
    try:
        return await set_project_campaigns(db, ctx.organization_id, row.id, campaign_ids)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/close-hint")
async def close_hint(
    project_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _need(ctx, PermissionCode.REQUEST_TRIAGE, PermissionCode.REQUEST_MANAGE, PermissionCode.ORG_ADMIN)
    from app.requests.spine import ready_to_close, tasks_for

    row = await db.get(WorkProject, project_id)
    if not row or not row.request_id:
        return {"ready": False}
    req = await db.get(WorkRequest, row.request_id)
    if not req:
        return {"ready": False}
    tasks = await tasks_for(db, ctx.organization_id, request_id=req.id)
    return {"ready": ready_to_close(req, tasks), "request_id": str(req.id)}


@router.post("/{request_id}/tasks", status_code=201)
async def convert_to_task(
    request_id: UUID,
    body: dict,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _need(ctx, PermissionCode.REQUEST_TRIAGE, PermissionCode.REQUEST_MANAGE, PermissionCode.ORG_ADMIN)
    from app.requests.spine import ensure_thread, system_message
    from app.services import WorkService

    req = await db.get(WorkRequest, request_id)
    if not req or req.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="درخواست پیدا نشد")
    title = str(body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="عنوان خالی است")
    assignee = body.get("assignee_id")
    task = await WorkService(db).create_task(
        organization_id=ctx.organization_id,
        title=title,
        owner_id=ctx.user.id,
        request_id=req.id,
        description=str(body.get("description") or ""),
        assignee_ids=[UUID(assignee)] if assignee else None,
        actor_permissions=ctx.permissions | {PermissionCode.TASK_WRITE},
    )
    if req.status in ("new", "in_review"):
        req.status = "converted"
        req.updated_at = now()
    thread = await ensure_thread(
        db, organization_id=ctx.organization_id, actor_id=ctx.user.id, request_id=req.id, topic=req.title
    )
    await system_message(db, thread, f"وظیفه ساخته شد: {title}", task_id=task.id)
    await db.flush()
    return {"id": str(task.id), "title": task.title, "request_id": str(req.id), "status": req.status}


@router.post("/projects/{project_id}/tasks", status_code=201)
async def project_task(
    project_id: UUID,
    body: dict,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _need(ctx, PermissionCode.TASK_WRITE, PermissionCode.REQUEST_TRIAGE, PermissionCode.ORG_ADMIN)
    from app.services import WorkService

    row = await db.get(WorkProject, project_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    title = str(body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="عنوان خالی است")
    raw_ids = body.get("assignee_ids") or []
    if body.get("assignee_id"):
        raw_ids = [body.get("assignee_id")]
    assignee_ids = []
    for item in raw_ids:
        try:
            assignee_ids.append(UUID(str(item)))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="عضو نامعتبر است") from exc
    task = await WorkService(db).create_task(
        organization_id=ctx.organization_id,
        title=title,
        owner_id=ctx.user.id,
        project_id=row.id,
        request_id=row.request_id,
        assignee_ids=assignee_ids or None,
        actor_permissions=ctx.permissions | {PermissionCode.TASK_WRITE},
    )
    return {"id": str(task.id), "title": task.title, "project_id": str(row.id)}


@router.get("/projects/{project_id}/template")
async def preview_template(
    project_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _need(ctx, PermissionCode.REQUEST_CREATE, PermissionCode.REQUEST_TRIAGE, PermissionCode.ORG_ADMIN)
    from app.requests.spine import template_for

    row = await db.get(WorkProject, project_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    return {"kind": row.kind, "titles": template_for(row.kind)}


@router.post("/projects/{project_id}/apply-template", status_code=201)
async def apply_template(
    project_id: UUID,
    body: dict,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not body.get("confirm"):
        raise HTTPException(status_code=422, detail="اعمال قالب فقط با تأیید صریح است")
    _need(ctx, PermissionCode.TASK_WRITE, PermissionCode.REQUEST_TRIAGE, PermissionCode.ORG_ADMIN)
    from app.requests.spine import template_for
    from app.services import WorkService

    row = await db.get(WorkProject, project_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    made = []
    for title in template_for(row.kind):
        task = await WorkService(db).create_task(
            organization_id=ctx.organization_id,
            title=title,
            owner_id=ctx.user.id,
            project_id=row.id,
            request_id=row.request_id,
            actor_permissions=ctx.permissions | {PermissionCode.TASK_WRITE},
        )
        made.append({"id": str(task.id), "title": task.title})
    return {"tasks": made}


@router.post("/projects/{project_id}/attachments", status_code=201)
async def add_attachment(
    project_id: UUID,
    body: dict,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _need(ctx, PermissionCode.REQUEST_TRIAGE, PermissionCode.TASK_WRITE, PermissionCode.ORG_ADMIN)
    from app.requests.models import WorkAttachment
    from app.requests.spine import attachment_out

    row = await db.get(WorkProject, project_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    title = str(body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="عنوان خالی است")
    item = WorkAttachment(
        organization_id=ctx.organization_id,
        project_id=row.id,
        request_id=row.request_id,
        title=title,
        url=str(body.get("url") or ""),
        kind=str(body.get("kind") or "link"),
        created_by=ctx.user.id,
    )
    db.add(item)
    await db.flush()
    return attachment_out(item)


@router.post("/projects/{project_id}/designs", status_code=201)
async def add_design(
    project_id: UUID,
    body: dict,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _need(ctx, PermissionCode.REQUEST_TRIAGE, PermissionCode.TASK_WRITE, PermissionCode.ORG_ADMIN)
    from app.requests.models import DesignDeliverable
    from app.requests.spine import deliverable_out

    row = await db.get(WorkProject, project_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    item = DesignDeliverable(
        organization_id=ctx.organization_id,
        project_id=row.id,
        title=str(body.get("title") or "طرح").strip(),
        url=str(body.get("url") or ""),
        created_by=ctx.user.id,
    )
    db.add(item)
    await db.flush()
    return deliverable_out(item)


@router.patch("/projects/{project_id}/designs/{item_id}")
async def patch_design(
    project_id: UUID,
    item_id: UUID,
    body: dict,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _need(ctx, PermissionCode.REQUEST_TRIAGE, PermissionCode.TASK_WRITE, PermissionCode.ORG_ADMIN)
    from app.requests.models import DesignDeliverable
    from app.requests.spine import deliverable_out

    item = await db.get(DesignDeliverable, item_id)
    if not item or item.project_id != project_id or item.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="طرح پیدا نشد")
    status = str(body.get("status") or "")
    if status not in ("draft", "in_review", "approved", "changes_requested"):
        raise HTTPException(status_code=422, detail="وضعیت طرح نامعتبر است")
    item.status = status
    return deliverable_out(item)


@router.post("/projects/{project_id}/shoots", status_code=201)
async def add_shoot(
    project_id: UUID,
    body: dict,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _need(ctx, PermissionCode.REQUEST_TRIAGE, PermissionCode.TASK_WRITE, PermissionCode.ORG_ADMIN)
    from app.requests.models import Shoot
    from app.requests.spine import shoot_out

    row = await db.get(WorkProject, project_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    item = Shoot(
        organization_id=ctx.organization_id,
        project_id=row.id,
        title=str(body.get("title") or "فیلم").strip(),
        location=str(body.get("location") or ""),
        created_by=ctx.user.id,
    )
    db.add(item)
    await db.flush()
    return shoot_out(item)


@router.patch("/projects/{project_id}/shoots/{item_id}")
async def patch_shoot(
    project_id: UUID,
    item_id: UUID,
    body: dict,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _need(ctx, PermissionCode.REQUEST_TRIAGE, PermissionCode.TASK_WRITE, PermissionCode.ORG_ADMIN)
    from app.requests.models import Shoot
    from app.requests.spine import shoot_out

    item = await db.get(Shoot, item_id)
    if not item or item.project_id != project_id or item.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="فیلم پیدا نشد")
    status = str(body.get("status") or "")
    if status not in ("planned", "shot", "delivered"):
        raise HTTPException(status_code=422, detail="وضعیت فیلم نامعتبر است")
    item.status = status
    return shoot_out(item)


@router.get("/context/{kind}/{entity_id}")
async def check_context(
    kind: str,
    entity_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """اعتبار زمینهٔ دستیار. شناسهٔ سازمان دیگر ۴۰۴ است."""
    from app.requests.spine import assert_visible

    try:
        await assert_visible(db, ctx.organization_id, kind, entity_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="پیدا نشد") from None
    return {"ok": True, "kind": kind, "id": str(entity_id)}