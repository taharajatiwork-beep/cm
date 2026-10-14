from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, handle_authz
from app.api.pagination import page
from app.core.permissions import AuthorizationError, PermissionCode, require_permission
from app.core.vehicle_labels import fa_vehicle_name
from app.db.session import get_db
from app.models import Notification
from app.models.enums import CaseStatus, CaseType
from app.schemas import (
    CaseCreate,
    CaseOut,
    CaseUpdate,
    ConversationCreate,
    ConversationOut,
    DelegateIn,
    EventOut,
    MessageCreate,
    MessageOut,
    NotificationOut,
    ProgressOut,
    SlaPolicyCreate,
    SlaPolicyOut,
    TaskCreate,
    TaskDependencyCreate,
    TaskOut,
    WorkItemCreate,
    WorkItemOut,
)
from app.services import UNSET, CommunicationService, SlaService, TimelineService, WorkService

router = APIRouter(tags=["work"])


async def _is_site_admin(db: AsyncSession, ctx: AuthContext) -> bool:
    """نقش ادمین سایت همه‌چیز را می‌بیند؛ مدیر فروش با org.admin این‌طور نیست."""
    from app.models import Role

    if not ctx.user.role_id:
        return False
    code = await db.scalar(select(Role.code).where(Role.id == ctx.user.role_id))
    return code == "admin"


async def _member_conversation(db: AsyncSession, ctx: AuthContext, conversation_id: UUID):
    """چت فقط برای کسی که داخل آن است باز می‌شود. ادمین سایت استثناست."""
    from app.models import Conversation, ConversationParticipant

    row = await db.get(Conversation, conversation_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(404, "Conversation not found")
    if await _is_site_admin(db, ctx):
        return row
    member = await db.scalar(
        select(ConversationParticipant.id).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == ctx.user.id,
        )
    )
    if member is None:
        raise HTTPException(404, "Conversation not found")
    return row


@router.post("/conversations", response_model=ConversationOut)
async def create_conversation(
    body: ConversationCreate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.CONVERSATION_WRITE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return await CommunicationService(db).create_conversation(
        organization_id=ctx.organization_id,
        channel=body.channel,
        participant_ids=body.participant_ids,
        topic=body.topic,
        branch_id=body.branch_id,
        team_id=body.team_id,
        work_item_id=body.work_item_id,
        case_id=body.case_id,
        vehicle_id=body.vehicle_id,
        customer_id=body.customer_id,
        campaign_id=body.campaign_id,
        actor_id=ctx.user.id,
    )


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut)
async def post_message(
    conversation_id: UUID,
    body: MessageCreate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.CONVERSATION_WRITE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    await _member_conversation(db, ctx, conversation_id)
    return await CommunicationService(db).post_message(
        organization_id=ctx.organization_id,
        conversation_id=conversation_id,
        sender_id=ctx.user.id,
        text=body.text,
        channel=body.channel,
        message_type=body.message_type,
        reply_to_message_id=body.reply_to_message_id,
    )


@router.post("/conversations/{conversation_id}/messages/{message_id}/task")
async def task_from_message(
    conversation_id: UUID,
    message_id: UUID,
    body: dict,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ساخت وظیفه از پیام فقط با پیش‌نمایش و تأیید. از چت چیزی تأیید مالی نمی‌شود."""
    from app.models import Conversation, Message

    try:
        require_permission(ctx.permissions, PermissionCode.TASK_WRITE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    message = await db.get(Message, message_id)
    conv = await db.get(Conversation, conversation_id)
    if not message or not conv or message.conversation_id != conv.id or conv.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پیام پیدا نشد")
    title = (message.text or "").strip()[:120] or "پیگیری"
    preview = {"title": title, "conversation_id": str(conv.id), "message_id": str(message.id)}
    if not body.get("confirm"):
        return {"preview": preview, "created": False}
    task = await WorkService(db).create_task(
        organization_id=ctx.organization_id,
        title=title,
        owner_id=ctx.user.id,
        project_id=conv.project_id,
        request_id=conv.request_id,
        description=message.text or "",
        actor_permissions=ctx.permissions,
    )
    message.task_id = task.id
    return {"preview": preview, "created": True, "task_id": str(task.id)}


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.CONVERSATION_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    await _member_conversation(db, ctx, conversation_id)
    return await CommunicationService(db).list_messages(conversation_id)


@router.post("/work-items", response_model=WorkItemOut)
async def create_work_item(
    body: WorkItemCreate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.WORK_ITEM_WRITE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return await WorkService(db).create_work_item(
        organization_id=ctx.organization_id,
        title=body.title,
        owner_id=ctx.user.id,
        description=body.description,
        priority=body.priority,
        branch_id=body.branch_id,
        vehicle_id=body.vehicle_id,
        customer_id=body.customer_id,
        deadline=body.deadline,
        participant_ids=body.participant_ids,
    )


@router.get("/work-items/{work_item_id}", response_model=WorkItemOut)
async def get_work_item(
    work_item_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models import WorkItem

    try:
        require_permission(ctx.permissions, PermissionCode.WORK_ITEM_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    wi = await db.get(WorkItem, work_item_id)
    if not wi or wi.organization_id != ctx.organization_id:
        raise HTTPException(404, "Work item not found")
    from app.core.scope import row_is_visible

    if not await row_is_visible(db, WorkItem, work_item_id, ctx.organization_id, ctx.scope):
        raise HTTPException(404, "Work item not found")
    return wi


@router.get("/work-items/{work_item_id}/progress", response_model=ProgressOut)
async def work_item_progress(
    work_item_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.WORK_ITEM_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    from app.models import WorkItem

    wi = await db.get(WorkItem, work_item_id)
    if not wi or wi.organization_id != ctx.organization_id:
        raise HTTPException(404, "Work item not found")
    from app.core.scope import row_is_visible

    if not await row_is_visible(db, WorkItem, work_item_id, ctx.organization_id, ctx.scope):
        raise HTTPException(404, "Work item not found")
    try:
        data = await WorkService(db).work_item_progress(work_item_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return data


@router.get("/work-items/{work_item_id}/timeline", response_model=list[EventOut])
async def work_item_timeline(
    work_item_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.EVENT_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return await TimelineService(db).for_work_item(work_item_id, organization_id=ctx.organization_id)


@router.get("/work-items")
async def list_work_items(
    status: str | None = None,
    owner_id: UUID | None = None,
    vehicle_id: UUID | None = None,
    envelope: bool = False,
    cursor: str | None = None,
    limit: int = 20,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.enums import WorkItemStatus

    try:
        require_permission(ctx.permissions, PermissionCode.WORK_ITEM_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    items = await WorkService(db).list_work_items(
        ctx.organization_id,
        status=WorkItemStatus(status) if status else None,
        owner_id=owner_id,
        vehicle_id=vehicle_id,
        scope=ctx.scope,
    )
    if envelope:
        dumped = [
            {
                "id": str(item.id),
                "title": item.title,
                "status": getattr(item.status, "value", item.status),
                "owner_id": str(item.owner_id),
            }
            for item in items
        ]
        return JSONResponse(page(dumped, cursor=cursor, limit=limit))
    return items


@router.post("/work-items/{work_item_id}/participants")
async def add_work_item_participant(
    work_item_id: UUID,
    body: dict,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models import WorkItem
    from app.models.enums import ParticipantRole

    try:
        require_permission(ctx.permissions, PermissionCode.WORK_ITEM_WRITE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    wi = await db.get(WorkItem, work_item_id)
    if not wi or wi.organization_id != ctx.organization_id:
        raise HTTPException(404, "Work item not found")
    try:
        row = await WorkService(db).add_work_item_participant(
            work_item_id=work_item_id,
            user_id=UUID(body["user_id"]),
            role=ParticipantRole(body.get("role", ParticipantRole.MEMBER.value)),
            actor_id=ctx.user.id,
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return {"id": row.id, "user_id": row.user_id, "role": row.role.value}


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    work_item_id: UUID | None = None,
    case_id: UUID | None = None,
    campaign_id: UUID | None = None,
    project_id: UUID | None = None,
    request_id: UUID | None = None,
    archived: bool = False,
    envelope: bool = False,
    cursor: str | None = None,
    limit: int = 20,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.CONVERSATION_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    service = CommunicationService(db)
    see_all = await _is_site_admin(db, ctx)
    rows = await service.list_conversations(
        ctx.organization_id,
        work_item_id=work_item_id,
        case_id=case_id,
        campaign_id=campaign_id,
        scope=ctx.scope,
        archived=archived,
        viewer_id=None if see_all else ctx.user.id,
    )
    if project_id:
        rows = [row for row in rows if row.project_id == project_id]
    if request_id:
        rows = [row for row in rows if row.request_id == request_id]
    latest = await service.last_messages([row.id for row in rows])
    listed = []
    for row in rows:
        text, sender_id, sent_at = latest.get(row.id, (None, None, None))
        participant_ids = [p.user_id for p in row.participants]
        in_chat = ctx.user.id in participant_ids
        listed.append(
            ConversationOut.model_validate(row).model_copy(
                update={
                    "participant_ids": participant_ids,
                    "last_message_text": text,
                    "last_sender_id": sender_id,
                    "last_message_at": sent_at,
                    "needs_reply": in_chat and sender_id is not None and sender_id != ctx.user.id,
                }
            )
        )
    if envelope:
        dumped = [row.model_dump(mode="json") for row in listed]
        return JSONResponse(page(dumped, cursor=cursor, limit=limit))
    return listed


@router.get("/tasks")
async def list_tasks(
    work_item_id: UUID | None = None,
    assignee_id: UUID | None = None,
    status: str | None = None,
    overdue_only: bool = False,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.enums import TaskStatus

    try:
        require_permission(ctx.permissions, PermissionCode.TASK_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    tasks = await WorkService(db).list_tasks(
        ctx.organization_id,
        work_item_id=work_item_id,
        assignee_id=assignee_id,
        status=TaskStatus(status) if status else None,
        overdue_only=overdue_only,
        scope=ctx.scope,
    )
    from app.models.enums import TaskRole
    from app.schemas import TaskOut

    listed = []
    for task in tasks:
        row = TaskOut.model_validate(task).model_dump(mode="json")
        row["assignee_ids"] = [
            str(link.user_id) for link in task.assignees if link.role == TaskRole.ASSIGNEE
        ]
        listed.append(row)
    return listed


def _task_note_out(note, author_name: str = "") -> dict:
    return {
        "id": str(note.id),
        "kind": note.kind,
        "body": note.body or "",
        "url": note.url or "",
        "file_name": note.file_name or "",
        "author_name": author_name,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "has_file": bool(note.file_path),
    }


async def _ensure_task_visible(db: AsyncSession, ctx: AuthContext, task_id: UUID):
    from app.models import Task
    from app.models.enums import TaskRole
    from sqlalchemy.orm import selectinload

    try:
        require_permission(ctx.permissions, PermissionCode.TASK_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    task = await db.get(
        Task,
        task_id,
        options=(selectinload(Task.assignees),),
    )
    if not task or task.organization_id != ctx.organization_id:
        raise HTTPException(404, "Task not found")
    assignee_ids = {link.user_id for link in task.assignees if link.role == TaskRole.ASSIGNEE}
    is_participant = ctx.user.id == task.owner_id or ctx.user.id in assignee_ids
    if not is_participant and PermissionCode.ORG_ADMIN.value not in ctx.permissions:
        from app.core.scope import apply_scope

        scoped = apply_scope(
            select(Task.id).where(Task.id == task_id, Task.organization_id == ctx.organization_id),
            Task,
            ctx.scope,
        )
        if not await db.scalar(scoped):
            raise HTTPException(403, "Not authorized")
    return task


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models import User
    from app.models.enums import TaskRole
    from app.schemas import TaskOut

    task = await _ensure_task_visible(db, ctx, task_id)
    row = TaskOut.model_validate(task).model_dump(mode="json")
    assignee_ids_ordered = [link.user_id for link in task.assignees if link.role == TaskRole.ASSIGNEE]
    row["assignee_ids"] = [str(uid) for uid in assignee_ids_ordered]
    names: dict[UUID, str] = {}
    if assignee_ids_ordered:
        for user in (
            await db.scalars(select(User).where(User.id.in_(assignee_ids_ordered)))
        ).all():
            names[user.id] = user.full_name
    row["assignees"] = [{"id": str(uid), "full_name": names.get(uid, "")} for uid in assignee_ids_ordered]
    if task.project_id:
        from app.requests.models import WorkAttachment, WorkProject

        project = await db.get(WorkProject, task.project_id)
        if project and project.organization_id == ctx.organization_id:
            row["project"] = {
                "id": str(project.id),
                "code": project.code,
                "title": project.title,
                "description": (project.description or "").strip(),
                "request_id": str(project.request_id) if project.request_id else None,
            }
            attachments = list(
                (
                    await db.scalars(
                        select(WorkAttachment).where(WorkAttachment.project_id == project.id)
                    )
                ).all()
            )
            row["project_attachments"] = [
                {
                    "id": str(item.id),
                    "title": item.title,
                    "url": item.url,
                    "kind": item.kind,
                }
                for item in attachments
            ]
    return row


@router.get("/tasks/{task_id}/notes")
async def list_task_notes(
    task_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models import TaskNote, User

    await _ensure_task_visible(db, ctx, task_id)
    notes = list(
        (
            await db.scalars(
                select(TaskNote)
                .where(TaskNote.task_id == task_id, TaskNote.organization_id == ctx.organization_id)
                .order_by(TaskNote.created_at.asc())
            )
        ).all()
    )
    author_ids = {note.author_id for note in notes if note.author_id}
    authors: dict[UUID, str] = {}
    if author_ids:
        for user in (await db.scalars(select(User).where(User.id.in_(author_ids)))).all():
            authors[user.id] = user.full_name
    return [_task_note_out(note, authors.get(note.author_id, "") if note.author_id else "") for note in notes]


@router.post("/tasks/{task_id}/notes", status_code=201)
async def add_task_note(
    task_id: UUID,
    body: dict,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models import TaskNote

    await _ensure_task_visible(db, ctx, task_id)
    kind = str(body.get("kind") or "comment").strip() or "comment"
    if kind not in ("comment", "link"):
        raise HTTPException(422, "Invalid note kind")
    note = TaskNote(
        organization_id=ctx.organization_id,
        task_id=task_id,
        author_id=ctx.user.id,
        kind=kind,
        body=(body.get("body") or "").strip() or None,
        url=(body.get("url") or "").strip() or None,
    )
    if kind == "link" and not note.url:
        raise HTTPException(422, "URL required")
    db.add(note)
    await db.flush()
    return _task_note_out(note, ctx.user.full_name)


@router.post("/tasks/{task_id}/files", status_code=201)
async def upload_task_file(
    task_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
    kind: str = Form("deliverable"),
):
    from app.core.files import UploadRejected, save_upload
    from app.models import TaskNote

    await _ensure_task_visible(db, ctx, task_id)
    if kind not in ("file", "deliverable"):
        raise HTTPException(422, "Invalid file kind")
    raw = await file.read()
    try:
        path = save_upload(file.filename or "upload", file.content_type, raw)
    except UploadRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    note = TaskNote(
        organization_id=ctx.organization_id,
        task_id=task_id,
        author_id=ctx.user.id,
        kind=kind,
        file_path=str(path),
        file_name=file.filename or "file",
    )
    db.add(note)
    await db.flush()
    return _task_note_out(note, ctx.user.full_name)


@router.get("/tasks/{task_id}/files/{note_id}")
async def download_task_file(
    task_id: UUID,
    note_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response

    from app.core.files import read_upload
    from app.models import TaskNote

    await _ensure_task_visible(db, ctx, task_id)
    note = await db.get(TaskNote, note_id)
    if not note or note.task_id != task_id or note.organization_id != ctx.organization_id:
        raise HTTPException(404, "File not found")
    if not note.file_path:
        raise HTTPException(404, "File not found")
    data = read_upload(note.file_path)
    name = note.file_name or "file"
    return Response(content=data, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/tasks/{task_id}/participants")
async def add_task_participant(
    task_id: UUID,
    body: dict,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models import Task
    from app.models.enums import TaskRole

    try:
        require_permission(ctx.permissions, PermissionCode.TASK_WRITE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    task = await db.get(Task, task_id)
    if not task or task.organization_id != ctx.organization_id:
        raise HTTPException(404, "Task not found")
    try:
        row = await WorkService(db).add_task_participant(
            task_id=task_id,
            user_id=UUID(body["user_id"]),
            role=TaskRole(body.get("role", TaskRole.FOLLOWER.value)),
            actor_id=ctx.user.id,
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return {"id": row.id, "user_id": row.user_id, "role": row.role.value}


@router.post("/tasks/{task_id}/assign", response_model=TaskOut)
async def assign_task(
    task_id: UUID,
    body: DelegateIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Alias of delegate — assign to user and/or team/department/branch target."""
    try:
        return await WorkService(db).delegate_task(
            organization_id=ctx.organization_id,
            task_id=task_id,
            actor_id=ctx.user.id,
            actor_permissions=ctx.permissions,
            to_user_id=body.to_user_id,
            to_target_type=body.to_target_type,
            to_target_id=body.to_target_id,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/tasks/{task_id}/timeline", response_model=list[EventOut])
async def task_timeline(
    task_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.EVENT_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return await TimelineService(db).for_entity("task", task_id, organization_id=ctx.organization_id)


@router.get("/cases/{case_id}/timeline", response_model=list[EventOut])
async def case_timeline(
    case_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.EVENT_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return await TimelineService(db).for_entity("case", case_id, organization_id=ctx.organization_id)


@router.get("/users/{user_id}/workload")
async def user_workload(
    user_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.TASK_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    from app.models import User

    target = await db.get(User, user_id)
    if not target or target.organization_id != ctx.organization_id:
        raise HTTPException(404, "User not found")
    return await WorkService(db).user_workload(user_id, organization_id=ctx.organization_id)


@router.get("/cases", response_model=list[CaseOut])
async def list_cases(
    type: CaseType | None = None,
    status: CaseStatus | None = None,
    owner_id: UUID | None = None,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.CASE_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return await WorkService(db).list_cases(
        ctx.organization_id,
        case_type=type,
        status=status,
        owner_id=owner_id,
        scope=ctx.scope,
    )


class InquiryIn(BaseModel):
    vehicle_id: UUID
    full_name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=3, max_length=40)
    note: str = ""


@router.post("/cases/inquiry", response_model=CaseOut, status_code=201)
async def create_inquiry(
    body: InquiryIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.INQUIRY_CREATE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    from app.models import Role, User
    from app.models.customer import Customer
    from app.models.inventory import Vehicle
    from app.services.notifications import notify

    vehicle = await db.get(Vehicle, body.vehicle_id)
    if not vehicle or vehicle.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="خودرو پیدا نشد")
    phone = body.phone.strip()
    customer = await db.scalar(
        select(Customer).where(
            Customer.organization_id == ctx.organization_id,
            Customer.phone == phone,
        )
    )
    if customer is None:
        customer = Customer(
            organization_id=ctx.organization_id,
            full_name=body.full_name.strip(),
            phone=phone,
            created_by=ctx.user.id,
        )
        db.add(customer)
        await db.flush()
    elif body.full_name.strip():
        customer.full_name = body.full_name.strip()
    owner_id = ctx.user.manager_id
    if owner_id is None:
        owner_id = await db.scalar(
            select(User.id)
            .join(Role, User.role_id == Role.id)
            .where(User.organization_id == ctx.organization_id, Role.code == "admin")
            .limit(1)
        )
    if owner_id is None:
        owner_id = ctx.user.id
    label = fa_vehicle_name(vehicle.brand, vehicle.model) or f"{vehicle.brand} {vehicle.model}".strip()
    subject = f"استعلام خرید — {label}"
    if body.note.strip():
        subject = f"{subject} — {body.note.strip()[:120]}"
    case = await WorkService(db).create_case(
        organization_id=ctx.organization_id,
        subject=subject,
        case_type=CaseType.BUYER_REQUEST,
        created_by=ctx.user.id,
        owner_id=owner_id,
        vehicle_id=body.vehicle_id,
        customer_id=customer.id,
    )
    await notify(
        db,
        organization_id=ctx.organization_id,
        user_id=owner_id,
        title="استعلام جدید",
        body=subject,
        entity_type="case",
        entity_id=case.id,
    )
    return case


@router.post("/cases", response_model=CaseOut)
async def create_case(
    body: CaseCreate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.CASE_WRITE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return await WorkService(db).create_case(
        organization_id=ctx.organization_id,
        subject=body.subject,
        case_type=body.type,
        created_by=ctx.user.id,
        work_item_id=body.work_item_id,
        owner_id=body.owner_id,
        priority=body.priority,
        branch_id=body.branch_id,
        vehicle_id=body.vehicle_id,
        customer_id=body.customer_id,
        deadline=body.deadline,
        sla_policy_id=body.sla_policy_id,
    )


@router.patch("/cases/{case_id}", response_model=CaseOut)
async def update_case(
    case_id: UUID,
    body: CaseUpdate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.CASE_WRITE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    try:
        return await WorkService(db).update_case(
            organization_id=ctx.organization_id,
            case_id=case_id,
            actor_id=ctx.user.id,
            status=body.status,
            owner_id=body.owner_id if "owner_id" in body.model_fields_set else UNSET,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/tasks", response_model=TaskOut)
async def create_task(
    body: TaskCreate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await WorkService(db).create_task(
            organization_id=ctx.organization_id,
            title=body.title,
            owner_id=ctx.user.id,
            work_item_id=body.work_item_id,
            case_id=body.case_id,
            project_id=body.project_id,
            request_id=body.request_id,
            description=body.description,
            priority=body.priority,
            assignee_ids=body.assignee_ids,
            assignment_target_type=body.assignment_target_type,
            assignment_target_id=body.assignment_target_id,
            deadline=body.deadline,
            sla_policy_id=body.sla_policy_id,
            actor_permissions=ctx.permissions,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e


@router.post("/tasks/dependencies")
async def add_dependency(
    body: TaskDependencyCreate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.TASK_WRITE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    from app.models import Task

    dependent = await db.get(Task, body.dependent_task_id)
    if not dependent or dependent.organization_id != ctx.organization_id:
        raise HTTPException(404, "Task not found")
    prerequisite = await db.get(Task, body.prerequisite_task_id)
    if not prerequisite or prerequisite.organization_id != ctx.organization_id:
        raise HTTPException(404, "Task not found")
    dep = await WorkService(db).add_dependency(
        body.dependent_task_id, body.prerequisite_task_id, actor_id=ctx.user.id
    )
    return {"id": dep.id}


@router.post("/tasks/{task_id}/delegate", response_model=TaskOut)
async def delegate_task(
    task_id: UUID,
    body: DelegateIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await WorkService(db).delegate_task(
            organization_id=ctx.organization_id,
            task_id=task_id,
            actor_id=ctx.user.id,
            actor_permissions=ctx.permissions,
            to_user_id=body.to_user_id,
            to_target_type=body.to_target_type,
            to_target_id=body.to_target_id,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/tasks/{task_id}/complete", response_model=TaskOut)
async def complete_task(
    task_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models import Task

    task = await db.get(Task, task_id)
    if not task or task.organization_id != ctx.organization_id:
        raise HTTPException(404, "Task not found")
    try:
        return await WorkService(db).complete_task(task_id, ctx.user.id)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/tasks/{task_id}/reopen", response_model=TaskOut)
async def reopen_task(
    task_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import UTC, datetime, timedelta

    from app.models import Task
    from app.models.enums import TaskRole, TaskStatus
    from app.schemas import TaskOut

    task = await _ensure_task_visible(db, ctx, task_id)
    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(400, "Task is not completed")
    assignee_ids = {link.user_id for link in task.assignees if link.role == TaskRole.ASSIGNEE}
    if ctx.user.id != task.owner_id and ctx.user.id not in assignee_ids:
        raise HTTPException(403, "Not authorized")
    if not task.completed_at or task.completed_at < datetime.now(UTC) - timedelta(minutes=10):
        raise HTTPException(400, "Reopen window expired")
    task.status = TaskStatus.IN_PROGRESS
    task.completed_at = None
    task.updated_at = datetime.now(UTC)
    await db.flush()
    return TaskOut.model_validate(task)


@router.post("/sla/policies", response_model=SlaPolicyOut)
async def create_sla_policy(
    body: SlaPolicyCreate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.SLA_MANAGE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return await SlaService(db).create_policy(
        organization_id=ctx.organization_id,
        name=body.name,
        priority=body.priority,
        response_minutes=body.response_minutes,
        warning_minutes=body.warning_minutes,
        escalate_on_breach=body.escalate_on_breach,
    )


@router.post("/sla/tasks/{task_id}/evaluate", response_model=TaskOut)
async def evaluate_task_sla(
    task_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.SLA_MANAGE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    from app.models import Task

    task = await db.get(Task, task_id)
    if not task or task.organization_id != ctx.organization_id:
        raise HTTPException(404, "Task not found")
    return await SlaService(db).evaluate_task(task_id)


@router.post("/sla/cases/{case_id}/evaluate", response_model=CaseOut)
async def evaluate_case_sla(
    case_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.SLA_MANAGE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    from app.models import CommunicationCase

    case = await db.get(CommunicationCase, case_id)
    if not case or case.organization_id != ctx.organization_id:
        raise HTTPException(404, "Case not found")
    return await SlaService(db).evaluate_case(case_id)


@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.NOTIFICATION_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == ctx.user.id)
        .order_by(Notification.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(Notification, notification_id)
    if not row or row.user_id != ctx.user.id:
        raise HTTPException(404, "Notification not found")
    row.is_read = True
    return {"id": str(row.id), "is_read": True}


@router.post("/conversations/{conversation_id}/archive")
async def archive_conversation(
    conversation_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.CONVERSATION_WRITE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    row = await _member_conversation(db, ctx, conversation_id)
    row.archived_at = datetime.now(UTC)
    return {"id": str(row.id), "archived": True}


@router.post("/conversations/{conversation_id}/unarchive")
async def unarchive_conversation(
    conversation_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.CONVERSATION_WRITE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    row = await _member_conversation(db, ctx, conversation_id)
    row.archived_at = None
    return {"id": str(row.id), "archived": False}


@router.post("/conversations/{conversation_id}/participants")
async def add_conversation_participant(
    conversation_id: UUID,
    body: dict,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.CONVERSATION_WRITE)
        await _member_conversation(db, ctx, conversation_id)
        row = await CommunicationService(db).add_participant(
            organization_id=ctx.organization_id,
            conversation_id=conversation_id,
            user_id=UUID(body["user_id"]),
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    except (ValueError, KeyError) as e:
        raise HTTPException(404, str(e)) from e
    return {"id": str(row.id), "user_id": str(row.user_id)}


@router.get("/timeline/{entity_type}/{entity_id}", response_model=list[EventOut])
async def entity_timeline(
    entity_type: str,
    entity_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.EVENT_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return await TimelineService(db).for_entity(
        entity_type, entity_id, organization_id=ctx.organization_id
    )


@router.get("/timeline/users/{user_id}", response_model=list[EventOut])
async def user_timeline(
    user_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.EVENT_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return await TimelineService(db).for_user_activity(user_id, organization_id=ctx.organization_id)
