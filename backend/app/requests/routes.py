"""درخواست مدیر به تیم: مستقل از پرفورمنس، برای همهٔ مدیرها و تیم‌ها."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from app.models import Task
from app.models.enums import TaskStatus
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, handle_authz
from app.core.permissions import AuthorizationError, PermissionCode, require_any_permission, require_permission
from app.db.session import get_db
from app.models import Conversation, Team, User
from datetime import date, datetime
from app.requests.models import WorkProject, WorkRequest
from app.requests.project_access import apply_project_visibility, base_visible_projects
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


def _project_out(
    row: WorkProject,
    *,
    request_code: str = "",
    request_title: str = "",
    team_name: str = "",
    task_total: int | None = None,
    task_done: int | None = None,
) -> dict:
    out = {
        "id": str(row.id),
        "code": row.code,
        "title": row.title,
        "description": row.description,
        "kind": row.kind,
        "request_id": str(row.request_id) if row.request_id else None,
        "request_code": request_code,
        "request_title": request_title,
        "team_id": str(row.team_id) if row.team_id else None,
        "team_name": team_name,
        "status": row.status,
        "due_date": iso(row.due_date),
        "planned_budget": row.planned_budget,
        "lead_user_id": str(row.lead_user_id) if row.lead_user_id else None,
        "requester_acceptance": row.requester_acceptance,
        "mizito_lane": row.mizito_lane,
        "mizito_card_id": row.mizito_card_id,
        "mizito_board": row.mizito_board,
        "mizito_board_id": row.mizito_board_id,
        "mizito_board_position": row.mizito_board_position,
        "mizito_status": row.mizito_status,
        "mizito_code": row.mizito_code,
        "mizito_weight": row.mizito_weight,
        "mizito_created_at": iso(row.mizito_created_at),
        "mizito_modified_at": iso(row.mizito_modified_at),
        "mizito_completed_at": iso(row.mizito_completed_at),
        "mizito_deadline": iso(row.mizito_deadline),
        "mizito_progress": row.mizito_progress,
        "mizito_checklist_done": row.mizito_checklist_done,
        "mizito_checklist_total": row.mizito_checklist_total,
        "mizito_attachments": row.mizito_attachments,
        "mizito_has_comments": row.mizito_has_comments,
        "mizito_removed_at": iso(row.mizito_removed_at),
        "hidden_in_cm": bool(row.hidden_in_cm),
        "source": "mizito" if row.mizito_card_id else "cm",
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }
    if task_total is not None:
        out["task_total"] = task_total
        out["task_done"] = task_done or 0
    return out


async def _task_counts_for_projects(db: AsyncSession, organization_id: UUID, project_ids: set[UUID]) -> dict[UUID, tuple[int, int]]:
    if not project_ids:
        return {}
    rows = (
        await db.scalars(
            select(Task).where(
                Task.organization_id == organization_id,
                Task.project_id.in_(project_ids),
            )
        )
    ).all()
    counts: dict[UUID, tuple[int, int]] = {}
    for task in rows:
        if not task.project_id or task.status == TaskStatus.CANCELLED:
            continue
        total, done = counts.get(task.project_id, (0, 0))
        total += 1
        if task.status == TaskStatus.COMPLETED:
            done += 1
        counts[task.project_id] = (total, done)
    return counts


async def _ensure_request_visible(db: AsyncSession, ctx: AuthContext, request_id: UUID) -> WorkRequest:
    row = await db.get(WorkRequest, request_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="درخواست پیدا نشد")
    if _is_requester_only(ctx):
        if row.requested_by != ctx.user.id:
            raise HTTPException(status_code=404, detail="درخواست پیدا نشد")
        return row
    if _is_triage(ctx):
        if ctx.user.team_id and PermissionCode.ORG_ADMIN not in ctx.permissions:
            tree = await _tree_ids(db, ctx)
            if tree is not None and row.team_id and row.team_id not in tree:
                raise HTTPException(status_code=404, detail="درخواست پیدا نشد")
        return row
    if PermissionCode.TASK_READ in ctx.permissions:
        visible = await _member_project_ids(db, ctx)
        if visible:
            linked = await db.scalar(
                select(WorkProject.id).where(
                    WorkProject.request_id == request_id,
                    WorkProject.id.in_(visible),
                )
            )
            if linked:
                return row
        raise HTTPException(status_code=404, detail="درخواست پیدا نشد")
    if PermissionCode.REPORT_READ in ctx.permissions:
        if ctx.scope.is_org_wide or ctx.scope.level == "organization":
            return row
        if ctx.user.team_id:
            if row.team_id == ctx.user.team_id:
                return row
            from app.requests.spine import child_team_ids

            tree = set(await child_team_ids(db, [ctx.user.team_id]))
            if row.team_id and row.team_id in tree:
                return row
        raise HTTPException(status_code=404, detail="درخواست پیدا نشد")
    raise HTTPException(status_code=403, detail="دسترسی نیست")


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
    """قالب مدیر: درخواست‌های خودش و نمای فقط‌خواندنی پروژه‌های همان درخواست‌ها."""
    return PermissionCode.REQUEST_CREATE in ctx.permissions and not _is_triage(ctx) and PermissionCode.TASK_READ not in ctx.permissions


async def _member_project_ids(db: AsyncSession, ctx: AuthContext) -> set[UUID]:
    """پروژه‌هایی که کاربر عضوشان است یا وظیفه‌ای در آن‌ها به او سپرده شده."""
    from app.models import Task, TaskAssignee
    from app.requests.models import WorkProjectMember

    member_ids = set(
        (
            await db.scalars(
                select(WorkProjectMember.project_id).where(WorkProjectMember.user_id == ctx.user.id)
            )
        ).all()
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


async def _ensure_triage_target(db: AsyncSession, ctx: AuthContext, row: WorkRequest) -> None:
    """تریاژ فقط برای درخواست‌هایی که تیم مقصد در زیرتیم کاربر است."""
    if PermissionCode.ORG_ADMIN in ctx.permissions or not _is_triage(ctx):
        return
    tree = await _tree_ids(db, ctx)
    if tree is None:
        return
    if not row.team_id or row.team_id not in tree:
        raise HTTPException(status_code=403, detail="این درخواست برای تیم شما نیست")


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
    _need(ctx, PermissionCode.REQUEST_CREATE, PermissionCode.ORG_ADMIN)
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
    if is_triage and not is_owner:
        await _ensure_triage_target(db, ctx, row)
    data = body.model_dump(exclude_unset=True)
    if is_owner and row.status == "new" and PermissionCode.ORG_ADMIN not in ctx.permissions:
        forbidden = set(data) - {"title", "description", "kind", "priority", "due_date"}
        if forbidden:
            raise HTTPException(status_code=403, detail="تغییر وضعیت و تیم واگذاری با سرپرست است")
    elif is_triage and PermissionCode.ORG_ADMIN not in ctx.permissions:
        forbidden = set(data) - {"status", "team_id"}
        if forbidden:
            raise HTTPException(status_code=403, detail="سرپرست فقط وضعیت و مسیردهی را عوض می‌کند")
    elif not is_triage:
        raise HTTPException(status_code=403, detail="فقط تا وقتی درخواست جدید است می‌توانید متن را عوض کنید")
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


@router.get("/{request_id}/spine")
async def request_spine(
    request_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """خط زمین مفهومی درخواست کار (پروژه‌ها، وظایف، پرداخت‌ها)."""
    _need(
        ctx,
        PermissionCode.REQUEST_CREATE,
        PermissionCode.REQUEST_TRIAGE,
        PermissionCode.REQUEST_MANAGE,
        PermissionCode.TASK_READ,
        PermissionCode.REPORT_READ,
        PermissionCode.ORG_ADMIN,
    )
    await _ensure_request_visible(db, ctx, request_id)
    from app.requests.spine import build_spine_timeline

    return {
        "request_id": str(request_id),
        "items": await build_spine_timeline(db, ctx.organization_id, request_id=request_id),
    }


@router.delete("/{request_id}", status_code=204)
async def delete_request(
    request_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(WorkRequest, request_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="درخواست پیدا نشد")
    is_admin = PermissionCode.ORG_ADMIN in ctx.permissions
    is_owner_new = row.requested_by == ctx.user.id and row.status == "new"
    if not is_admin and not is_owner_new:
        raise HTTPException(status_code=403, detail="فقط صاحب درخواست، تا وقتی جدید است، می‌تواند آن را حذف کند")
    await db.delete(row)
    await db.flush()
    return Response(status_code=204)


# ---------------------------------------------------------------- پروژه‌ها (تیم از درخواست می‌سازد)


@router.post("/projects", status_code=201)
async def create_standalone_project(
    body: ProjectIn,
    request_id: UUID | None = None,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """سرپرست یا ادمین پروژه می‌سازد. درخواست مادر اختیاری است."""
    _need(ctx, PermissionCode.REQUEST_TRIAGE, PermissionCode.REQUEST_MANAGE, PermissionCode.ORG_ADMIN)
    req = None
    if request_id:
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
        request_id=req.id if req else None,
        team_id=body.team_id or (req.team_id if req else ctx.user.team_id),
        status=body.status,
        due_date=req.due_date if req else None,
        mizito_lane=(body.mizito_lane or "").strip() or None,
        created_by=ctx.user.id,
    )
    db.add(row)
    if req and req.status in ("new", "in_review"):
        req.status = "converted"
        req.updated_at = now()
    await db.flush()
    team_name = ""
    if row.team_id:
        team = await db.get(Team, row.team_id)
        team_name = team.name if team else ""
    return _project_out(
        row,
        request_code=req.code if req else "",
        request_title=req.title if req else "",
        team_name=team_name,
    )


@router.post("/mizito/sync-work")
async def sync_mizito_work(
    purge_manual: bool = Query(default=False),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """پروژه‌های CM را از کارت‌های میزیتو به‌روز می‌کند. توکن فقط از اتصالات (DB) — همان ذخیرهٔ پنل."""
    _need(ctx, PermissionCode.REQUEST_TRIAGE, PermissionCode.REQUEST_MANAGE, PermissionCode.ORG_ADMIN)
    from app.perf.services.connections import mizito_token_for
    from app.requests.mizito_sync import run_org_mizito_sync, sync_mizito_cards_to_projects
    from app.worker import acquire_job, release_job

    token = (await mizito_token_for(db, ctx.organization_id)).strip()
    if not token:
        raise HTTPException(
            status_code=400,
            detail="توکن میزیتو ذخیره نشده. در اتصالات → میزیتو، x-token را یک بار ذخیره کنید.",
        )
    if not await acquire_job("mizito_sync", ttl_seconds=900):
        raise HTTPException(status_code=409, detail="همگام‌سازی میزیتو در حال اجراست")
    try:
        if purge_manual:
            result = await sync_mizito_cards_to_projects(
                db, ctx.organization_id, token=token, purge_manual=True
            )
        else:
            result = await run_org_mizito_sync(db, ctx.organization_id, token)
    finally:
        await release_job("mizito_sync")
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=str(result.get("reason") or "میزیتو وصل نشد"))
    return result


@router.get("/mizito/sync-status")
async def mizito_sync_status(
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
    from app.requests.mizito_sync import sync_status

    return await sync_status(db, ctx.organization_id)


@router.get("/mizito/changes")
async def mizito_changes(
    status: str = "",
    project_id: UUID | None = None,
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
    from app.requests.models import WorkMizitoChange

    query = select(WorkMizitoChange).where(WorkMizitoChange.organization_id == ctx.organization_id)
    if status:
        query = query.where(WorkMizitoChange.status == status)
    if project_id:
        query = query.where(WorkMizitoChange.project_id == project_id)
    rows = (await db.scalars(query.order_by(WorkMizitoChange.created_at.desc()).limit(100))).all()
    return [
        {
            "id": str(row.id),
            "project_id": str(row.project_id) if row.project_id else None,
            "kind": row.kind,
            "field": row.field,
            "old_value": row.old_value,
            "new_value": row.new_value,
            "status": row.status,
            "created_at": iso(row.created_at),
        }
        for row in rows
    ]


@router.post("/mizito/changes/{change_id}/approve")
async def approve_mizito_change(
    change_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _decide_mizito_change(db, ctx, change_id, approve=True)


@router.post("/mizito/changes/{change_id}/ignore")
async def ignore_mizito_change(
    change_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _decide_mizito_change(db, ctx, change_id, approve=False)


async def _decide_mizito_change(db: AsyncSession, ctx: AuthContext, change_id: UUID, *, approve: bool) -> dict:
    _need(ctx, PermissionCode.REQUEST_TRIAGE, PermissionCode.REQUEST_MANAGE, PermissionCode.ORG_ADMIN)
    from app.requests.mizito_sync import decide_change

    try:
        return await decide_change(db, ctx.organization_id, change_id, ctx.user.id, approve)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/mizito-kanban/column")
async def mizito_kanban_column_route(
    lane: str,
    board_id: str,
    source: str = "",
    q: str = "",
    hide_done: bool = False,
    offset: int = 0,
    limit: int = Query(20, ge=1, le=100),
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
    from app.requests.mizito_kanban import mizito_kanban_column

    return await mizito_kanban_column(
        db,
        ctx,
        lane.strip(),
        board_id.strip(),
        source=source.strip(),
        q=q.strip(),
        hide_done=hide_done,
        offset=offset,
        limit=limit,
    )


@router.get("/mizito-kanban")
async def mizito_kanban(
    lane: str,
    source: str = "",
    q: str = "",
    hide_done: bool = False,
    include_archive: bool = False,
    per_column: int = Query(20, ge=1, le=50),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """کانبان یک دسته: ستون‌ها = بردهای میزیتو، کارت‌ها = پروژه‌های CM (هر کارت میزیتو)."""
    _need(
        ctx,
        PermissionCode.REQUEST_CREATE,
        PermissionCode.REQUEST_TRIAGE,
        PermissionCode.REQUEST_MANAGE,
        PermissionCode.TASK_READ,
        PermissionCode.ORG_ADMIN,
    )
    from app.requests.mizito_kanban import mizito_lane_kanban

    return await mizito_lane_kanban(
        db,
        ctx,
        lane.strip(),
        source=source.strip(),
        q=q.strip(),
        hide_done=hide_done,
        include_archive=include_archive,
        per_column=per_column,
    )


@router.get("/mizito-lanes")
async def list_mizito_lanes(
    counts: bool = False,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """دسته‌بندی مارکتینگ (پروژه‌های میزیتو) برای فیلتر پروژه‌ها."""
    _need(
        ctx,
        PermissionCode.REQUEST_CREATE,
        PermissionCode.REQUEST_TRIAGE,
        PermissionCode.REQUEST_MANAGE,
        PermissionCode.TASK_READ,
        PermissionCode.ORG_ADMIN,
    )
    from app.requests.mizito_lanes import mizito_lane_labels

    labels = mizito_lane_labels()
    if not counts:
        return labels
    out = []
    for lane in labels:
        query = base_visible_projects(ctx.organization_id).where(WorkProject.mizito_lane == lane["slug"])
        query = await apply_project_visibility(query, db, ctx)
        total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
        out.append({**lane, "project_count": int(total)})
    return out


@router.get("/projects")
async def list_projects(
    request_id: UUID | None = None,
    status: str = "",
    mizito_lane: str = "",
    source: str = "",
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ترییج/ادمین همه را می‌بینند؛ بقیه فقط پروژه‌های درخواست‌های خودشان."""
    """سرپرست و ادمین درخت تیم را می‌بینند؛ مدیر پروژه‌های درخواست خودش را؛ عضو فقط پروژه‌ای که در آن است."""
    _need(
        ctx,
        PermissionCode.REQUEST_CREATE,
        PermissionCode.REQUEST_TRIAGE,
        PermissionCode.REQUEST_MANAGE,
        PermissionCode.TASK_READ,
        PermissionCode.ORG_ADMIN,
    )
    query = base_visible_projects(ctx.organization_id)
    if request_id:
        query = query.where(WorkProject.request_id == request_id)
    if status:
        query = query.where(WorkProject.status == status)
    if mizito_lane.strip():
        query = query.where(WorkProject.mizito_lane == mizito_lane.strip())
    if source == "mizito":
        query = query.where(WorkProject.mizito_card_id.is_not(None))
    elif source == "cm":
        query = query.where(WorkProject.mizito_card_id.is_(None))
    query = await apply_project_visibility(query, db, ctx)
    rows = (await db.scalars(query.order_by(WorkProject.created_at.desc()))).all()
    task_counts = await _task_counts_for_projects(db, ctx.organization_id, {row.id for row in rows})
    req_meta: dict[UUID, tuple[str, str]] = {}
    req_ids = {row.request_id for row in rows if row.request_id}
    if req_ids:
        for req in (await db.scalars(select(WorkRequest).where(WorkRequest.id.in_(req_ids)))).all():
            req_meta[req.id] = (req.code, req.title)
    teams: dict[UUID, str] = {}
    team_ids = {row.team_id for row in rows if row.team_id}
    if team_ids:
        for team in (await db.scalars(select(Team).where(Team.id.in_(team_ids)))).all():
            teams[team.id] = team.name
    return [
        _project_out(
            row,
            request_code=req_meta.get(row.request_id, ("", ""))[0] if row.request_id else "",
            request_title=req_meta.get(row.request_id, ("", ""))[1] if row.request_id else "",
            team_name=teams.get(row.team_id, "") if row.team_id else "",
            task_total=task_counts.get(row.id, (0, 0))[0],
            task_done=task_counts.get(row.id, (0, 0))[1],
        )
        for row in rows
    ]


_PROJECT_SORT = {
    "created_at": WorkProject.created_at,
    "title": WorkProject.title,
    "status": WorkProject.status,
    "updated_at": WorkProject.updated_at,
    "due": WorkProject.mizito_deadline,
}


@router.get("/projects/page")
async def list_projects_page(
    q: str = "",
    mizito_lane: str = "",
    source: str = "",
    status: str = "",
    sort: str = "created_at",
    order: str = "desc",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
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
    query = base_visible_projects(ctx.organization_id)
    if mizito_lane.strip():
        query = query.where(WorkProject.mizito_lane == mizito_lane.strip())
    if status:
        query = query.where(WorkProject.status == status)
    if source == "mizito":
        query = query.where(WorkProject.mizito_card_id.is_not(None))
    elif source == "cm":
        query = query.where(WorkProject.mizito_card_id.is_(None))
    if q.strip():
        needle = f"%{q.strip()}%"
        query = query.where(or_(WorkProject.title.ilike(needle), WorkProject.code.ilike(needle)))
    query = await apply_project_visibility(query, db, ctx)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    col = _PROJECT_SORT.get(sort, WorkProject.created_at)
    ordering = col.desc() if order.lower() == "desc" else col.asc()
    rows = list(await db.scalars(query.order_by(ordering).offset(offset).limit(limit)))
    task_counts = await _task_counts_for_projects(db, ctx.organization_id, {row.id for row in rows})
    req_meta: dict[UUID, tuple[str, str]] = {}
    req_ids = {row.request_id for row in rows if row.request_id}
    if req_ids:
        for req in (await db.scalars(select(WorkRequest).where(WorkRequest.id.in_(req_ids)))).all():
            req_meta[req.id] = (req.code, req.title)
    teams: dict[UUID, str] = {}
    team_ids = {row.team_id for row in rows if row.team_id}
    if team_ids:
        for team in (await db.scalars(select(Team).where(Team.id.in_(team_ids)))).all():
            teams[team.id] = team.name
    items = [
        _project_out(
            row,
            request_code=req_meta.get(row.request_id, ("", ""))[0] if row.request_id else "",
            request_title=req_meta.get(row.request_id, ("", ""))[1] if row.request_id else "",
            team_name=teams.get(row.team_id, "") if row.team_id else "",
            task_total=task_counts.get(row.id, (0, 0))[0],
            task_done=task_counts.get(row.id, (0, 0))[1],
        )
        for row in rows
    ]
    return {"items": items, "total": int(total), "limit": limit, "offset": offset}


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
    await _ensure_triage_target(db, ctx, req)
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
    return _project_out(row, request_code=req.code, request_title=req.title, team_name=team_name)


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
    locked = {"title", "kind", "status", "due_date", "mizito_lane"}
    if row.mizito_card_id and locked.intersection(data):
        raise HTTPException(status_code=409, detail="این فیلد از میزیتو می‌آید")
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
    if row.status == "done" and row.request_id:
        from app.requests.spine import close_request_if_projects_done

        await close_request_if_projects_done(db, row.request_id)
    await db.flush()
    req_code = ""
    req_title = ""
    if row.request_id:
        req = await db.get(WorkRequest, row.request_id)
        req_code = req.code if req else ""
        req_title = req.title if req else ""
    team_name = ""
    if row.team_id:
        team = await db.get(Team, row.team_id)
        team_name = team.name if team else ""
    return _project_out(row, request_code=req_code, request_title=req_title, team_name=team_name)


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
    if row.mizito_card_id:
        raise HTTPException(status_code=409, detail="پروژهٔ میزیتو حذف نمی‌شود. می‌توانید آن را در CM پنهان کنید.")
    await db.delete(row)
    await db.flush()
    return Response(status_code=204)


@router.get("/my-work")
async def my_work_view(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
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


@router.get("/{request_id}")
async def get_request(
    request_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """جزئیات یک درخواست با پروژه‌ها و کارهای مستقیم."""
    _need(
        ctx,
        PermissionCode.REQUEST_CREATE,
        PermissionCode.REQUEST_TRIAGE,
        PermissionCode.REQUEST_MANAGE,
        PermissionCode.TASK_READ,
        PermissionCode.ORG_ADMIN,
    )
    row = await _ensure_request_visible(db, ctx, request_id)
    requester_name = ""
    if row.requested_by:
        user = await db.get(User, row.requested_by)
        requester_name = user.full_name if user else ""
    team_name = ""
    if row.team_id:
        team = await db.get(Team, row.team_id)
        team_name = team.name if team else ""
    projects = list(
        (await db.scalars(select(WorkProject).where(WorkProject.request_id == request_id))).all()
    )
    task_counts = await _task_counts_for_projects(db, ctx.organization_id, {p.id for p in projects})
    teams: dict[UUID, str] = {}
    team_ids = {p.team_id for p in projects if p.team_id}
    if team_ids:
        for team in (await db.scalars(select(Team).where(Team.id.in_(team_ids)))).all():
            teams[team.id] = team.name
    from app.requests.spine import build_spine_timeline, tasks_for

    direct_tasks = await tasks_for(db, ctx.organization_id, request_id=request_id)
    spine = await build_spine_timeline(db, ctx.organization_id, request_id=request_id)
    return {
        "request": _request_out(row, requester_name, team_name),
        "projects": [
            _project_out(
                project,
                request_code=row.code,
                request_title=row.title,
                team_name=teams.get(project.team_id, "") if project.team_id else "",
                task_total=task_counts.get(project.id, (0, 0))[0],
                task_done=task_counts.get(project.id, (0, 0))[1],
            )
            for project in projects
        ],
        "tasks": [
            {
                "id": str(task.id),
                "title": task.title,
                "status": task.status.value if hasattr(task.status, "value") else str(task.status),
                "project_id": str(task.project_id) if task.project_id else None,
            }
            for task in direct_tasks
            if not task.project_id
        ],
        "spine": spine,
    }


async def _visible_project(db: AsyncSession, ctx: AuthContext, project_id: UUID) -> WorkProject:
    _need(
        ctx,
        PermissionCode.REQUEST_CREATE,
        PermissionCode.REQUEST_TRIAGE,
        PermissionCode.REQUEST_MANAGE,
        PermissionCode.TASK_READ,
        PermissionCode.ORG_ADMIN,
    )
    row = await db.get(WorkProject, project_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    if _is_requester_only(ctx):
        req = await db.get(WorkRequest, row.request_id) if row.request_id else None
        if not req or req.requested_by != ctx.user.id:
            raise HTTPException(status_code=403, detail="Not authorized")
    elif not _is_triage(ctx):
        if row.id not in await _member_project_ids(db, ctx):
            raise HTTPException(status_code=403, detail="Not authorized")
    else:
        visible = await _tree_ids(db, ctx)
        if visible is not None and row.team_id not in visible:
            raise HTTPException(status_code=403, detail="Not authorized")
    return row


@router.post("/projects/{project_id}/thread")
async def open_project_thread(
    project_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """گفتگوی پروژه را (در صورت نبود) می‌سازد و کاربر را عضوش می‌کند."""
    from app.requests.spine import ensure_thread

    row = await _visible_project(db, ctx, project_id)
    if _is_requester_only(ctx):
        raise HTTPException(status_code=403, detail="Not authorized")
    thread = await ensure_thread(
        db, organization_id=ctx.organization_id, actor_id=ctx.user.id, project_id=row.id, topic=row.title
    )
    return {"id": str(thread.id), "topic": thread.topic}


@router.get("/projects/{project_id}")
async def project_detail(
    project_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _visible_project(db, ctx, project_id)
    from app.requests.models import DesignDeliverable, Shoot, WorkAttachment
    from app.requests.spine import (
        attachment_out,
        deliverable_out,
        progress,
        shoot_out,
        tasks_for,
        template_for,
    )

    tasks = await tasks_for(db, ctx.organization_id, project_id=row.id)
    thread = None
    if not _is_requester_only(ctx):
        thread = await db.scalar(
            select(Conversation).where(
                Conversation.organization_id == ctx.organization_id,
                Conversation.project_id == row.id,
                Conversation.pm_campaign_id.is_(None),
            )
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
    req_title = ""
    if row.request_id:
        req = await db.get(WorkRequest, row.request_id)
        req_code = req.code if req else ""
        req_title = req.title if req else ""
    team_name = ""
    if row.team_id:
        team = await db.get(Team, row.team_id)
        team_name = team.name if team else ""
    body = _project_out(row, request_code=req_code, request_title=req_title, team_name=team_name)
    if row.mizito_card_id:
        from app.perf.services.mizito import card_url_prefix

        prefix = card_url_prefix()
        body["mizito_url"] = f"{prefix}{row.mizito_card_id}" if prefix else ""
    body["progress"] = progress(tasks)
    body["template"] = template_for(row.kind)
    body["thread_id"] = str(thread.id) if thread else None
    body["tasks"] = [
        {
            "id": str(task.id),
            "title": task.title,
            "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "owner_id": str(task.owner_id),
            "assignee_ids": [
                str(link.user_id)
                for link in task.assignees
                if (link.role.value if hasattr(link.role, "value") else str(link.role)) == "ASSIGNEE"
            ],
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
    from app.core.campaigns import campaign_tag_choices

    body["campaign_tags"] = campaign_tag_choices()
    from app.requests.spine import build_spine_timeline

    body["spine"] = await build_spine_timeline(db, ctx.organization_id, project_id=row.id, request_id=row.request_id)
    if _is_requester_only(ctx):
        prog = progress(tasks)
        lead_name = ""
        if row.lead_user_id:
            lead = await db.get(User, row.lead_user_id)
            lead_name = lead.full_name if lead else ""
        stages = [
            {"key": "new", "label": "تازه", "done": row.status != "new"},
            {"key": "in_progress", "label": "در جریان", "done": row.status in ("in_progress", "done")},
            {"key": "done", "label": "تحویل", "done": row.status == "done"},
        ]
        return {
            "id": body["id"],
            "code": body["code"],
            "title": body["title"],
            "description": body.get("description", ""),
            "kind": body["kind"],
            "status": body["status"],
            "due_date": body.get("due_date"),
            "updated_at": body.get("updated_at"),
            "request_id": body["request_id"],
            "request_code": body["request_code"],
            "team_name": body["team_name"],
            "lead_name": lead_name,
            "blocked": int(prog.get("overdue") or 0) > 0,
            "progress": prog,
            "planning_pending": len(tasks) == 0,
            "requester_acceptance": row.requester_acceptance,
            "requester_acceptance_note": row.requester_acceptance_note or "",
            "timeline": stages,
            "spine": body["spine"],
            "tasks": body["tasks"],
            "campaigns": [
                {"id": item["id"], "code": item.get("code"), "title": item.get("title"), "status": item.get("status")}
                for item in body["campaigns"]
            ],
            "readonly": True,
            "report_href": f"/reports?project={body['id']}",
        }
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
    _need(ctx, PermissionCode.REQUEST_TRIAGE, PermissionCode.REQUEST_MANAGE, PermissionCode.ORG_ADMIN)
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


@router.post("/projects/{project_id}/campaigns", status_code=201)
async def create_project_campaign(
    project_id: UUID,
    body: dict,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """کمپین را همین‌جا می‌سازد و به پروژه وصل می‌کند. شماره از دفتر برند می‌آید."""
    _need(ctx, PermissionCode.REQUEST_TRIAGE, PermissionCode.REQUEST_MANAGE, PermissionCode.ORG_ADMIN)
    from sqlalchemy.exc import IntegrityError

    from app.core.campaigns import create_project_campaign as make_campaign

    row = await db.get(WorkProject, project_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    try:
        return await make_campaign(
            db,
            ctx.organization_id,
            row.id,
            ctx.user.id,
            str(body.get("title") or ""),
            str(body.get("tag") or "S"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="کد کمپین تکراری است") from exc


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


@router.post("/projects/{project_id}/acceptance")
async def project_acceptance(
    project_id: UUID,
    body: dict,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """مدیر (درخواست‌دهنده) پس از done پروژه تحویل را تأیید یا برمی‌گرداند."""
    _need(ctx, PermissionCode.REQUEST_CREATE, PermissionCode.ORG_ADMIN)
    if PermissionCode.ORG_ADMIN not in ctx.permissions and not _is_requester_only(ctx):
        raise HTTPException(status_code=403, detail="فقط درخواست‌دهنده می‌تواند تحویل را تأیید کند")
    row = await db.get(WorkProject, project_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    req = await db.get(WorkRequest, row.request_id) if row.request_id else None
    if not req or req.requested_by != ctx.user.id:
        raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    if row.status != "done":
        raise HTTPException(status_code=422, detail="پروژه هنوز تمام نشده")
    decision = str(body.get("decision") or "").strip()
    if decision not in ("accepted", "returned"):
        raise HTTPException(status_code=422, detail="تصمیم باید accepted یا returned باشد")
    note = str(body.get("note") or "").strip()
    if decision == "returned" and not note:
        raise HTTPException(status_code=422, detail="برای برگشت، یادداشت لازم است")
    if decision == "returned":
        row.status = "in_progress"
        row.requester_acceptance = None
        row.requester_acceptance_note = note
        row.updated_at = now()
        await db.flush()
        from app.requests.spine import ensure_thread, system_message
        from app.services import notify

        thread = await ensure_thread(
            db,
            organization_id=ctx.organization_id,
            actor_id=ctx.user.id,
            project_id=row.id,
            request_id=row.request_id,
            topic=row.title,
        )
        await system_message(db, thread, f"درخواست‌دهنده تحویل را برگرداند: {note}")
        if row.lead_user_id:
            await notify(
                db,
                organization_id=ctx.organization_id,
                user_id=row.lead_user_id,
                title="تحویل پروژه برگشت خورد",
                body=note,
                entity_type="project",
                entity_id=row.id,
            )
    else:
        row.requester_acceptance = decision
        row.requester_acceptance_note = note
        row.updated_at = now()
        await db.flush()
    return {"ok": True, "requester_acceptance": row.requester_acceptance, "note": row.requester_acceptance_note}


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