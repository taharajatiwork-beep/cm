from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.permissions import AuthorizationError, PermissionCode, require_permission
from app.core.security import hash_password, verify_password
from app.core.timeutil import as_utc, utc_now
from app.models import (
    AuditLog,
    Branch,
    CommunicationCase,
    Conversation,
    ConversationParticipant,
    DataScope,
    Department,
    Event,
    Message,
    Notification,
    Organization,
    OrgRelationship,
    Permission,
    Role,
    RolePermission,
    SlaPolicy,
    Task,
    TaskAssignee,
    TaskDependency,
    TaskParticipant,
    Team,
    User,
    WorkItem,
    WorkItemParticipant,
)
from app.models.enums import (
    AssignmentTargetType,
    CaseStatus,
    CaseType,
    Channel,
    MessageType,
    NotificationChannel,
    ParticipantRole,
    Priority,
    RelationshipType,
    SlaState,
    TaskRole,
    TaskStatus,
    WorkItemStatus,
)


async def emit_event(
    db: AsyncSession,
    *,
    organization_id: UUID,
    event_type: str,
    entity_type: str,
    entity_id: UUID,
    actor_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> Event:
    event = Event(
        organization_id=organization_id,
        event_type=event_type,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=json.dumps(payload) if payload else None,
    )
    db.add(event)
    await db.flush()
    return event


async def write_audit(
    db: AsyncSession,
    *,
    organization_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID,
    actor_id: UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    row = AuditLog(
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=json.dumps(details) if details else None,
    )
    db.add(row)
    await db.flush()
    return row


async def notify(
    db: AsyncSession,
    *,
    organization_id: UUID,
    user_id: UUID,
    title: str,
    body: str,
    channel: NotificationChannel = NotificationChannel.WEB,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
) -> Notification:
    n = Notification(
        organization_id=organization_id,
        user_id=user_id,
        channel=channel,
        title=title,
        body=body,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(n)
    await db.flush()

    # Mirror to Telegram/Bale outbox when the user has linked an account
    try:
        from app.integrations.telegram.callbacks import encode_callback
        from app.integrations.telegram.messages import (
            btn_done,
            btn_open,
            btn_reply,
            notify_branch,
            notify_message,
            notify_sla,
            notify_task_assigned,
            notify_task_done,
        )
        from app.integrations.telegram.outbox import classify_notify_event, enqueue_telegram
        from app.core.config import get_settings

        event = classify_notify_event(title=title, entity_type=entity_type)
        lang = "fa"
        settings = get_settings()
        web = settings.web_app_base_url.rstrip("/")

        if event == "task_assigned":
            text = notify_task_assigned(body or title, lang=lang)
            buttons = None
            if entity_id:
                buttons = [
                    [
                        {"text": btn_done(lang=lang), "callback_data": encode_callback("done", "task", entity_id)},
                        {"text": btn_open(lang=lang), "url": f"{web}/my-work"},
                    ]
                ]
        elif event == "task_done":
            text = notify_task_done(body or title, lang=lang)
            buttons = [[{"text": btn_open(lang=lang), "url": f"{web}/my-work"}]]
        elif event == "sla":
            late = "breach" in title.lower() or "escalat" in title.lower() or "گذشت" in title or "دیر" in title
            text = notify_sla(body or title, late=late, lang=lang)
            buttons = None
            if entity_type == "task" and entity_id:
                buttons = [
                    [
                        {"text": btn_done(lang=lang), "callback_data": encode_callback("done", "task", entity_id)},
                        {"text": btn_open(lang=lang), "url": f"{web}/my-work"},
                    ]
                ]
        elif event == "branch":
            text = notify_branch(body or title, lang=lang)
            buttons = [[{"text": btn_open(lang=lang), "url": f"{web}/cases"}]]
        elif event == "message":
            text = notify_message(title, (body or "")[:200], "", lang=lang)
            buttons = [
                [
                    {"text": btn_reply(lang=lang), "url": f"{web}/communication"},
                    {"text": btn_open(lang=lang), "url": f"{web}/communication"},
                ]
            ]
        else:
            text = f"{title}\n{body}" if body else title
            buttons = [[{"text": btn_open(lang=lang), "url": f"{web}/"}]]

        await enqueue_telegram(
            db,
            organization_id=organization_id,
            user_id=user_id,
            event_type=event,
            text=text,
            buttons=buttons,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    except Exception:
        # Never break the core write path because of Telegram
        pass

    return n


async def get_user_permissions(db: AsyncSession, user: User) -> set[str]:
    if not user.role_id:
        return set()
    result = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == user.role_id)
    )
    return set(result.scalars().all())


class OrgService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_organization(self, name: str, slug: str) -> Organization:
        org = Organization(name=name, slug=slug)
        self.db.add(org)
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=org.id,
            event_type="organization.created",
            entity_type="organization",
            entity_id=org.id,
            payload={"name": name, "slug": slug},
        )
        return org

    async def create_branch(
        self, organization_id: UUID, name: str, code: str, city: str | None = None
    ) -> Branch:
        branch = Branch(organization_id=organization_id, name=name, code=code, city=city)
        self.db.add(branch)
        await self.db.flush()
        return branch

    async def create_department(self, organization_id: UUID, name: str, code: str) -> Department:
        dept = Department(organization_id=organization_id, name=name, code=code)
        self.db.add(dept)
        await self.db.flush()
        return dept

    async def create_team(
        self,
        organization_id: UUID,
        name: str,
        code: str,
        department_id: UUID | None = None,
    ) -> Team:
        team = Team(
            organization_id=organization_id,
            name=name,
            code=code,
            department_id=department_id,
        )
        self.db.add(team)
        await self.db.flush()
        return team

    async def ensure_permissions(self) -> None:
        for code in PermissionCode:
            existing = await self.db.scalar(select(Permission).where(Permission.code == code.value))
            if not existing:
                self.db.add(Permission(code=code.value, description=code.value))
        await self.db.flush()

    async def grant_role_permissions(self, role_id: UUID, permission_codes: list[str]) -> None:
        """Add any missing permissions to an existing role (idempotent)."""
        await self.ensure_permissions()
        for pcode in permission_codes:
            code = pcode.value if hasattr(pcode, "value") else str(pcode)
            perm = await self.db.scalar(select(Permission).where(Permission.code == code))
            if not perm:
                continue
            exists = await self.db.scalar(
                select(RolePermission).where(
                    RolePermission.role_id == role_id,
                    RolePermission.permission_id == perm.id,
                )
            )
            if not exists:
                self.db.add(RolePermission(role_id=role_id, permission_id=perm.id))
        await self.db.flush()

    async def create_role(
        self,
        organization_id: UUID,
        name: str,
        code: str,
        permission_codes: list[str],
        data_scope_level: str = "organization",
    ) -> Role:
        await self.ensure_permissions()
        role = Role(organization_id=organization_id, name=name, code=code)
        self.db.add(role)
        await self.db.flush()
        for pcode in permission_codes:
            perm = await self.db.scalar(select(Permission).where(Permission.code == pcode))
            if perm:
                self.db.add(RolePermission(role_id=role.id, permission_id=perm.id))
        self.db.add(DataScope(role_id=role.id, level=data_scope_level))
        await self.db.flush()
        return role

    async def create_user(
        self,
        *,
        organization_id: UUID,
        email: str,
        full_name: str,
        password: str,
        role_id: UUID | None = None,
        branch_id: UUID | None = None,
        department_id: UUID | None = None,
        team_id: UUID | None = None,
        manager_id: UUID | None = None,
    ) -> User:
        user = User(
            organization_id=organization_id,
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            role_id=role_id,
            branch_id=branch_id,
            department_id=department_id,
            team_id=team_id,
            manager_id=manager_id,
        )
        self.db.add(user)
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=organization_id,
            event_type="user.created",
            entity_type="user",
            entity_id=user.id,
            payload={"email": email, "full_name": full_name},
        )
        return user

    async def authenticate(self, organization_id: UUID, email: str, password: str) -> User | None:
        user = await self.db.scalar(
            select(User).where(User.organization_id == organization_id, User.email == email)
        )
        if not user or not verify_password(password, user.hashed_password):
            return None
        return user

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.db.get(User, user_id)

    async def add_relationship(
        self,
        organization_id: UUID,
        from_user_id: UUID,
        to_user_id: UUID,
        relationship_type: RelationshipType,
        actor_id: UUID | None = None,
    ) -> OrgRelationship:
        rel = OrgRelationship(
            organization_id=organization_id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            relationship_type=relationship_type,
        )
        self.db.add(rel)
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=organization_id,
            event_type="relationship.created",
            actor_id=actor_id,
            entity_type="relationship",
            entity_id=rel.id,
            payload={
                "from_user_id": str(from_user_id),
                "to_user_id": str(to_user_id),
                "type": relationship_type.value,
            },
        )
        return rel

    async def list_relationships(self, user_id: UUID) -> list[OrgRelationship]:
        result = await self.db.execute(
            select(OrgRelationship).where(
                (OrgRelationship.from_user_id == user_id) | (OrgRelationship.to_user_id == user_id)
            )
        )
        return list(result.scalars().all())

    async def who_manages(self, user_id: UUID) -> list[User]:
        result = await self.db.execute(
            select(User)
            .join(OrgRelationship, OrgRelationship.from_user_id == User.id)
            .where(
                OrgRelationship.to_user_id == user_id,
                OrgRelationship.relationship_type == RelationshipType.MANAGES,
            )
        )
        return list(result.scalars().all())

    async def team_members(self, team_id: UUID) -> list[User]:
        result = await self.db.execute(select(User).where(User.team_id == team_id))
        return list(result.scalars().all())

    async def eligible_assignees(
        self,
        organization_id: UUID,
        *,
        team_id: UUID | None = None,
        branch_id: UUID | None = None,
        department_id: UUID | None = None,
    ) -> list[User]:
        q = select(User).where(User.organization_id == organization_id, User.is_active.is_(True))
        if team_id:
            q = q.where(User.team_id == team_id)
        if branch_id:
            q = q.where(User.branch_id == branch_id)
        if department_id:
            q = q.where(User.department_id == department_id)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def list_people(
        self, organization_id: UUID, *, q: str | None = None
    ) -> list[User]:
        stmt = (
            select(User)
            .options(selectinload(User.role))
            .where(User.organization_id == organization_id, User.is_active.is_(True))
            .order_by(User.full_name)
        )
        if q:
            like = f"%{q}%"
            stmt = stmt.where((User.full_name.ilike(like)) | (User.email.ilike(like)))
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_branches(self, organization_id: UUID) -> list[Branch]:
        result = await self.db.execute(
            select(Branch)
            .where(Branch.organization_id == organization_id)
            .order_by(Branch.name)
        )
        return list(result.scalars().all())

    async def list_departments(self, organization_id: UUID) -> list[Department]:
        result = await self.db.execute(
            select(Department)
            .where(Department.organization_id == organization_id)
            .order_by(Department.name)
        )
        return list(result.scalars().all())

    async def list_teams(self, organization_id: UUID) -> list[Team]:
        result = await self.db.execute(
            select(Team).where(Team.organization_id == organization_id).order_by(Team.name)
        )
        return list(result.scalars().all())

    async def who_reports_to(self, manager_id: UUID) -> list[User]:
        result = await self.db.execute(
            select(User)
            .join(OrgRelationship, OrgRelationship.to_user_id == User.id)
            .where(
                OrgRelationship.from_user_id == manager_id,
                OrgRelationship.relationship_type == RelationshipType.MANAGES,
            )
        )
        return list(result.scalars().all())

    async def list_org_relationships(self, organization_id: UUID) -> list[OrgRelationship]:
        result = await self.db.execute(
            select(OrgRelationship)
            .where(OrgRelationship.organization_id == organization_id)
            .order_by(OrgRelationship.created_at.desc())
        )
        return list(result.scalars().all())


class CommunicationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_conversation(
        self,
        *,
        organization_id: UUID,
        channel: Channel,
        participant_ids: list[UUID],
        topic: str | None = None,
        branch_id: UUID | None = None,
        team_id: UUID | None = None,
        work_item_id: UUID | None = None,
        case_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        campaign_id: UUID | None = None,
        actor_id: UUID | None = None,
    ) -> Conversation:
        conv = Conversation(
            organization_id=organization_id,
            channel=channel,
            topic=topic,
            branch_id=branch_id,
            team_id=team_id,
            work_item_id=work_item_id,
            case_id=case_id,
            vehicle_id=vehicle_id,
            campaign_id=campaign_id,
        )
        self.db.add(conv)
        await self.db.flush()
        for uid in participant_ids:
            self.db.add(
                ConversationParticipant(
                    conversation_id=conv.id,
                    user_id=uid,
                    role=ParticipantRole.MEMBER,
                )
            )
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=organization_id,
            event_type="conversation.created",
            actor_id=actor_id,
            entity_type="conversation",
            entity_id=conv.id,
            payload={"topic": topic, "channel": channel.value},
        )
        return conv

    async def post_message(
        self,
        *,
        organization_id: UUID,
        conversation_id: UUID,
        sender_id: UUID,
        text: str,
        channel: Channel = Channel.WEB,
        message_type: MessageType = MessageType.TEXT,
        reply_to_message_id: UUID | None = None,
        channel_message_id: str | None = None,
    ) -> Message:
        msg = Message(
            organization_id=organization_id,
            conversation_id=conversation_id,
            channel=channel,
            channel_message_id=channel_message_id,
            sender_id=sender_id,
            text=text,
            message_type=message_type,
            reply_to_message_id=reply_to_message_id,
        )
        self.db.add(msg)
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=organization_id,
            event_type="message.sent",
            actor_id=sender_id,
            entity_type="message",
            entity_id=msg.id,
            payload={"conversation_id": str(conversation_id)},
        )
        return msg

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        return list(result.scalars().all())

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        return await self.db.scalar(
            select(Conversation)
            .options(selectinload(Conversation.participants), selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id)
        )

    async def list_conversations(
        self,
        organization_id: UUID,
        *,
        work_item_id: UUID | None = None,
        case_id: UUID | None = None,
        campaign_id: UUID | None = None,
    ) -> list[Conversation]:
        q = (
            select(Conversation)
            .where(Conversation.organization_id == organization_id)
            .order_by(Conversation.created_at.desc())
        )
        if work_item_id:
            q = q.where(Conversation.work_item_id == work_item_id)
        if case_id:
            q = q.where(Conversation.case_id == case_id)
        if campaign_id:
            q = q.where(Conversation.campaign_id == campaign_id)
        return list((await self.db.execute(q)).scalars().all())


class WorkService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_work_item(
        self,
        *,
        organization_id: UUID,
        title: str,
        owner_id: UUID,
        description: str | None = None,
        priority: Priority = Priority.MEDIUM,
        branch_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        customer_id: UUID | None = None,
        deadline: datetime | None = None,
        participant_ids: list[UUID] | None = None,
    ) -> WorkItem:
        wi = WorkItem(
            organization_id=organization_id,
            title=title,
            description=description,
            owner_id=owner_id,
            priority=priority,
            branch_id=branch_id,
            vehicle_id=vehicle_id,
            customer_id=customer_id,
            deadline=deadline,
            status=WorkItemStatus.OPEN,
        )
        self.db.add(wi)
        await self.db.flush()
        self.db.add(
            WorkItemParticipant(
                work_item_id=wi.id, user_id=owner_id, role=ParticipantRole.OWNER
            )
        )
        for uid in participant_ids or []:
            if uid != owner_id:
                self.db.add(
                    WorkItemParticipant(
                        work_item_id=wi.id, user_id=uid, role=ParticipantRole.MEMBER
                    )
                )
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=organization_id,
            event_type="work_item.created",
            actor_id=owner_id,
            entity_type="work_item",
            entity_id=wi.id,
            payload={"title": title},
        )
        return wi

    async def create_case(
        self,
        *,
        organization_id: UUID,
        subject: str,
        case_type: CaseType,
        created_by: UUID,
        work_item_id: UUID | None = None,
        owner_id: UUID | None = None,
        priority: Priority = Priority.MEDIUM,
        branch_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        customer_id: UUID | None = None,
        deadline: datetime | None = None,
        sla_policy_id: UUID | None = None,
    ) -> CommunicationCase:
        from sqlalchemy import func as sqlfunc

        existing = await self.db.scalar(
            select(sqlfunc.count())
            .select_from(CommunicationCase)
            .where(CommunicationCase.organization_id == organization_id)
        )
        case_number = f"C-{(existing or 0) + 1:05d}"
        case = CommunicationCase(
            case_number=case_number,
            organization_id=organization_id,
            work_item_id=work_item_id,
            type=case_type,
            subject=subject,
            status=CaseStatus.ASSIGNED if owner_id else CaseStatus.OPEN,
            priority=priority,
            created_by=created_by,
            owner_id=owner_id,
            branch_id=branch_id,
            vehicle_id=vehicle_id,
            customer_id=customer_id,
            deadline=deadline,
            sla_policy_id=sla_policy_id,
            sla_state=SlaState.ACTIVE if sla_policy_id or deadline else SlaState.NONE,
        )
        self.db.add(case)
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=organization_id,
            event_type="case.created",
            actor_id=created_by,
            entity_type="case",
            entity_id=case.id,
            payload={"case_number": case_number, "subject": subject},
        )
        if owner_id:
            await emit_event(
                self.db,
                organization_id=organization_id,
                event_type="case.assigned",
                actor_id=created_by,
                entity_type="case",
                entity_id=case.id,
                payload={"owner_id": str(owner_id)},
            )
            await notify(
                self.db,
                organization_id=organization_id,
                user_id=owner_id,
                title=f"Case {case_number} assigned",
                body=subject,
                entity_type="case",
                entity_id=case.id,
            )
        return case

    async def list_cases(
        self,
        organization_id: UUID,
        *,
        case_type: CaseType | None = None,
        status: CaseStatus | None = None,
        owner_id: UUID | None = None,
        limit: int = 50,
    ) -> list[CommunicationCase]:
        q = (
            select(CommunicationCase)
            .where(CommunicationCase.organization_id == organization_id)
            .order_by(CommunicationCase.created_at.desc())
            .limit(limit)
        )
        if case_type:
            q = q.where(CommunicationCase.type == case_type)
        if status:
            q = q.where(CommunicationCase.status == status)
        if owner_id:
            q = q.where(CommunicationCase.owner_id == owner_id)
        return list((await self.db.execute(q)).scalars().all())

    async def create_task(
        self,
        *,
        organization_id: UUID,
        title: str,
        owner_id: UUID,
        work_item_id: UUID | None = None,
        case_id: UUID | None = None,
        description: str | None = None,
        priority: Priority = Priority.MEDIUM,
        assignee_ids: list[UUID] | None = None,
        assignment_target_type: AssignmentTargetType | None = None,
        assignment_target_id: UUID | None = None,
        deadline: datetime | None = None,
        sla_policy_id: UUID | None = None,
        actor_permissions: set[str] | None = None,
    ) -> Task:
        if actor_permissions is not None:
            require_permission(actor_permissions, PermissionCode.TASK_WRITE)
        status = TaskStatus.ASSIGNED if assignee_ids else TaskStatus.OPEN
        if assignment_target_type and not assignee_ids:
            status = TaskStatus.ASSIGNED  # owned by team/dept/branch
        task = Task(
            organization_id=organization_id,
            work_item_id=work_item_id,
            case_id=case_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            owner_id=owner_id,
            assignment_target_type=assignment_target_type,
            assignment_target_id=assignment_target_id,
            deadline=deadline,
            sla_policy_id=sla_policy_id,
            sla_state=SlaState.ACTIVE if sla_policy_id or deadline else SlaState.NONE,
        )
        self.db.add(task)
        await self.db.flush()
        self.db.add(
            TaskAssignee(task_id=task.id, user_id=owner_id, role=TaskRole.OWNER)
        )
        for uid in assignee_ids or []:
            self.db.add(
                TaskAssignee(task_id=task.id, user_id=uid, role=TaskRole.ASSIGNEE)
            )
            self.db.add(
                TaskParticipant(task_id=task.id, user_id=uid, role=TaskRole.ASSIGNEE)
            )
            await notify(
                self.db,
                organization_id=organization_id,
                user_id=uid,
                title="New task assigned",
                body=title,
                entity_type="task",
                entity_id=task.id,
            )
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=organization_id,
            event_type="task.created",
            actor_id=owner_id,
            entity_type="task",
            entity_id=task.id,
            payload={"title": title, "work_item_id": str(work_item_id) if work_item_id else None},
        )
        if assignee_ids:
            await emit_event(
                self.db,
                organization_id=organization_id,
                event_type="task.assigned",
                actor_id=owner_id,
                entity_type="task",
                entity_id=task.id,
                payload={"assignee_ids": [str(u) for u in assignee_ids]},
            )
        if work_item_id:
            wi = await self.db.get(WorkItem, work_item_id)
            if wi and wi.status == WorkItemStatus.OPEN:
                wi.status = WorkItemStatus.IN_PROGRESS
        return task

    async def add_dependency(
        self, dependent_task_id: UUID, prerequisite_task_id: UUID, actor_id: UUID | None = None
    ) -> TaskDependency:
        dep = TaskDependency(
            dependent_task_id=dependent_task_id,
            prerequisite_task_id=prerequisite_task_id,
        )
        self.db.add(dep)
        dependent = await self.db.get(Task, dependent_task_id)
        if dependent and dependent.status != TaskStatus.COMPLETED:
            prereq = await self.db.get(Task, prerequisite_task_id)
            if prereq and prereq.status != TaskStatus.COMPLETED:
                dependent.status = TaskStatus.BLOCKED
        await self.db.flush()
        if dependent:
            await emit_event(
                self.db,
                organization_id=dependent.organization_id,
                event_type="task.dependency_added",
                actor_id=actor_id,
                entity_type="task",
                entity_id=dependent_task_id,
                payload={"prerequisite_task_id": str(prerequisite_task_id)},
            )
        return dep

    async def delegate_task(
        self,
        *,
        task_id: UUID,
        actor_id: UUID,
        actor_permissions: set[str],
        to_user_id: UUID | None = None,
        to_target_type: AssignmentTargetType | None = None,
        to_target_id: UUID | None = None,
    ) -> Task:
        require_permission(actor_permissions, PermissionCode.TASK_DELEGATE)
        task = await self.db.get(Task, task_id)
        if not task:
            raise ValueError("Task not found")
        if to_user_id:
            self.db.add(
                TaskAssignee(task_id=task.id, user_id=to_user_id, role=TaskRole.ASSIGNEE)
            )
            self.db.add(
                TaskParticipant(task_id=task.id, user_id=to_user_id, role=TaskRole.ASSIGNEE)
            )
            task.status = TaskStatus.ASSIGNED
            await notify(
                self.db,
                organization_id=task.organization_id,
                user_id=to_user_id,
                title="Task delegated to you",
                body=task.title,
                entity_type="task",
                entity_id=task.id,
            )
        if to_target_type and to_target_id:
            task.assignment_target_type = to_target_type
            task.assignment_target_id = to_target_id
            task.status = TaskStatus.ASSIGNED
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=task.organization_id,
            event_type="task.reassigned",
            actor_id=actor_id,
            entity_type="task",
            entity_id=task.id,
            payload={
                "to_user_id": str(to_user_id) if to_user_id else None,
                "to_target_type": to_target_type.value if to_target_type else None,
                "to_target_id": str(to_target_id) if to_target_id else None,
            },
        )
        await write_audit(
            self.db,
            organization_id=task.organization_id,
            actor_id=actor_id,
            action="task.delegate",
            entity_type="task",
            entity_id=task.id,
            details={
                "to_user_id": str(to_user_id) if to_user_id else None,
                "to_target_type": to_target_type.value if to_target_type else None,
            },
        )
        return task

    async def complete_task(self, task_id: UUID, actor_id: UUID) -> Task:
        task = await self.db.get(Task, task_id)
        if not task:
            raise ValueError("Task not found")
        # Check dependencies
        deps = await self.db.execute(
            select(TaskDependency).where(TaskDependency.dependent_task_id == task_id)
        )
        for dep in deps.scalars().all():
            prereq = await self.db.get(Task, dep.prerequisite_task_id)
            if prereq and prereq.status != TaskStatus.COMPLETED:
                raise ValueError("Cannot complete task: prerequisite not completed")
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(UTC)
        await self.db.flush()
        # Unblock dependents
        dependents = await self.db.execute(
            select(TaskDependency).where(TaskDependency.prerequisite_task_id == task_id)
        )
        for dep in dependents.scalars().all():
            dependent = await self.db.get(Task, dep.dependent_task_id)
            if dependent and dependent.status == TaskStatus.BLOCKED:
                # check all prereqs
                all_deps = await self.db.execute(
                    select(TaskDependency).where(
                        TaskDependency.dependent_task_id == dependent.id
                    )
                )
                ready = True
                for d in all_deps.scalars().all():
                    p = await self.db.get(Task, d.prerequisite_task_id)
                    if p and p.status != TaskStatus.COMPLETED:
                        ready = False
                        break
                if ready:
                    dependent.status = TaskStatus.ASSIGNED
        await emit_event(
            self.db,
            organization_id=task.organization_id,
            event_type="task.completed",
            actor_id=actor_id,
            entity_type="task",
            entity_id=task.id,
            payload={"title": task.title},
        )
        if task.owner_id != actor_id:
            await notify(
                self.db,
                organization_id=task.organization_id,
                user_id=task.owner_id,
                title="Task completed",
                body=task.title,
                entity_type="task",
                entity_id=task.id,
            )
        # Update work item progress
        if task.work_item_id:
            await self._refresh_work_item_status(task.work_item_id)
        return task

    async def _refresh_work_item_status(self, work_item_id: UUID) -> None:
        wi = await self.db.get(WorkItem, work_item_id)
        if not wi:
            return
        result = await self.db.execute(select(Task).where(Task.work_item_id == work_item_id))
        tasks = list(result.scalars().all())
        if not tasks:
            return
        if all(t.status == TaskStatus.COMPLETED for t in tasks):
            wi.status = WorkItemStatus.COMPLETED
        elif any(t.status in (TaskStatus.IN_PROGRESS, TaskStatus.ASSIGNED, TaskStatus.COMPLETED) for t in tasks):
            wi.status = WorkItemStatus.IN_PROGRESS

    async def work_item_progress(self, work_item_id: UUID) -> dict[str, Any]:
        wi = await self.db.scalar(
            select(WorkItem)
            .options(
                selectinload(WorkItem.tasks).selectinload(Task.assignees),
                selectinload(WorkItem.participants),
            )
            .where(WorkItem.id == work_item_id)
        )
        if not wi:
            raise ValueError("Work item not found")
        tasks = wi.tasks
        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        overdue = sum(
            1
            for t in tasks
            if t.deadline
            and t.status != TaskStatus.COMPLETED
            and as_utc(t.deadline) < utc_now()
        )
        return {
            "work_item_id": wi.id,
            "title": wi.title,
            "status": wi.status.value,
            "total_tasks": total,
            "completed_tasks": completed,
            "overdue_tasks": overdue,
            "progress_pct": round((completed / total) * 100, 1) if total else 0.0,
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status.value,
                    "deadline": t.deadline,
                    "assignment_target_type": (
                        t.assignment_target_type.value if t.assignment_target_type else None
                    ),
                    "assignment_target_id": t.assignment_target_id,
                    "assignees": [
                        {"user_id": a.user_id, "role": a.role.value} for a in t.assignees
                    ],
                }
                for t in tasks
            ],
            "participants": [
                {"user_id": p.user_id, "role": p.role.value} for p in wi.participants
            ],
        }

    async def list_work_items(
        self,
        organization_id: UUID,
        *,
        status: WorkItemStatus | None = None,
        owner_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        limit: int = 100,
    ) -> list[WorkItem]:
        q = (
            select(WorkItem)
            .where(WorkItem.organization_id == organization_id)
            .order_by(WorkItem.created_at.desc())
            .limit(limit)
        )
        if status:
            q = q.where(WorkItem.status == status)
        if owner_id:
            q = q.where(WorkItem.owner_id == owner_id)
        if vehicle_id:
            q = q.where(WorkItem.vehicle_id == vehicle_id)
        return list((await self.db.execute(q)).scalars().all())

    async def add_work_item_participant(
        self,
        *,
        work_item_id: UUID,
        user_id: UUID,
        role: ParticipantRole = ParticipantRole.MEMBER,
        actor_id: UUID | None = None,
    ) -> WorkItemParticipant:
        wi = await self.db.get(WorkItem, work_item_id)
        if not wi:
            raise ValueError("Work item not found")
        existing = await self.db.scalar(
            select(WorkItemParticipant).where(
                WorkItemParticipant.work_item_id == work_item_id,
                WorkItemParticipant.user_id == user_id,
            )
        )
        if existing:
            return existing
        row = WorkItemParticipant(work_item_id=work_item_id, user_id=user_id, role=role)
        self.db.add(row)
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=wi.organization_id,
            event_type="work_item.participant_added",
            actor_id=actor_id,
            entity_type="work_item",
            entity_id=work_item_id,
            payload={"user_id": str(user_id), "role": role.value},
        )
        await notify(
            self.db,
            organization_id=wi.organization_id,
            user_id=user_id,
            title="Added to work item",
            body=wi.title,
            entity_type="work_item",
            entity_id=work_item_id,
        )
        return row

    async def add_task_participant(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
        role: TaskRole = TaskRole.FOLLOWER,
        actor_id: UUID | None = None,
    ) -> TaskParticipant:
        task = await self.db.get(Task, task_id)
        if not task:
            raise ValueError("Task not found")
        existing = await self.db.scalar(
            select(TaskParticipant).where(
                TaskParticipant.task_id == task_id,
                TaskParticipant.user_id == user_id,
                TaskParticipant.role == role,
            )
        )
        if existing:
            return existing
        row = TaskParticipant(task_id=task_id, user_id=user_id, role=role)
        self.db.add(row)
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=task.organization_id,
            event_type="task.participant_added",
            actor_id=actor_id,
            entity_type="task",
            entity_id=task_id,
            payload={"user_id": str(user_id), "role": role.value},
        )
        return row

    async def list_tasks(
        self,
        organization_id: UUID,
        *,
        work_item_id: UUID | None = None,
        assignee_id: UUID | None = None,
        status: TaskStatus | None = None,
        overdue_only: bool = False,
        limit: int = 100,
    ) -> list[Task]:
        q = (
            select(Task)
            .options(selectinload(Task.assignees))
            .where(Task.organization_id == organization_id)
            .order_by(Task.created_at.desc())
            .limit(limit)
        )
        if work_item_id:
            q = q.where(Task.work_item_id == work_item_id)
        if status:
            q = q.where(Task.status == status)
        if assignee_id:
            q = q.join(TaskAssignee, TaskAssignee.task_id == Task.id).where(
                TaskAssignee.user_id == assignee_id
            )
        if overdue_only:
            now = utc_now()
            # SQLite often stores naive datetimes; filter in Python for safe tz compare
            rows = list((await self.db.execute(q)).scalars().unique().all())
            return [
                t
                for t in rows
                if t.deadline
                and t.status != TaskStatus.COMPLETED
                and as_utc(t.deadline) is not None
                and as_utc(t.deadline) < now  # type: ignore[operator]
            ]
        return list((await self.db.execute(q)).scalars().unique().all())

    async def user_workload(self, user_id: UUID) -> dict[str, Any]:
        open_statuses = [
            TaskStatus.OPEN,
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS,
            TaskStatus.BLOCKED,
        ]
        tasks = list(
            (
                await self.db.execute(
                    select(Task)
                    .join(TaskAssignee, TaskAssignee.task_id == Task.id)
                    .where(
                        TaskAssignee.user_id == user_id,
                        Task.status.in_(open_statuses),
                    )
                    .order_by(Task.created_at.desc())
                )
            )
            .scalars()
            .unique()
            .all()
        )
        now = utc_now()
        overdue = [t for t in tasks if t.deadline and as_utc(t.deadline) < now]
        wi_ids = {t.work_item_id for t in tasks if t.work_item_id}
        return {
            "user_id": user_id,
            "open_tasks": len(tasks),
            "overdue_tasks": len(overdue),
            "active_work_items": len(wi_ids),
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status.value,
                    "work_item_id": t.work_item_id,
                    "deadline": t.deadline,
                    "sla_state": t.sla_state.value,
                }
                for t in tasks
            ],
        }


class SlaService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_policy(
        self,
        *,
        organization_id: UUID,
        name: str,
        priority: Priority,
        response_minutes: int,
        warning_minutes: int,
        escalate_on_breach: bool = True,
    ) -> SlaPolicy:
        policy = SlaPolicy(
            organization_id=organization_id,
            name=name,
            priority=priority,
            response_minutes=response_minutes,
            warning_minutes=warning_minutes,
            escalate_on_breach=escalate_on_breach,
        )
        self.db.add(policy)
        await self.db.flush()
        return policy

    async def evaluate_task(self, task_id: UUID, now: datetime | None = None) -> Task:
        now = now or datetime.now(UTC)
        task = await self.db.get(Task, task_id)
        if not task:
            raise ValueError("Task not found")
        if task.status == TaskStatus.COMPLETED or task.sla_state == SlaState.NONE:
            return task

        deadline = task.deadline
        warning_at = None
        if task.sla_policy_id:
            policy = await self.db.get(SlaPolicy, task.sla_policy_id)
            if policy:
                from datetime import timedelta

                created = task.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                deadline = deadline or (created + timedelta(minutes=policy.response_minutes))
                warning_at = created + timedelta(minutes=policy.warning_minutes)

        if deadline and deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)

        prev = task.sla_state
        if deadline and now >= deadline:
            task.sla_state = SlaState.BREACHED
            if task.sla_policy_id:
                policy = await self.db.get(SlaPolicy, task.sla_policy_id)
                if policy and policy.escalate_on_breach:
                    task.sla_state = SlaState.ESCALATED
                    await emit_event(
                        self.db,
                        organization_id=task.organization_id,
                        event_type="sla.breached",
                        entity_type="task",
                        entity_id=task.id,
                    )
                    await emit_event(
                        self.db,
                        organization_id=task.organization_id,
                        event_type="sla.escalated",
                        entity_type="task",
                        entity_id=task.id,
                    )
                    await notify(
                        self.db,
                        organization_id=task.organization_id,
                        user_id=task.owner_id,
                        title="SLA breached — escalated",
                        body=task.title,
                        channel=NotificationChannel.SYSTEM,
                        entity_type="task",
                        entity_id=task.id,
                    )
            elif prev != SlaState.BREACHED:
                await emit_event(
                    self.db,
                    organization_id=task.organization_id,
                    event_type="sla.breached",
                    entity_type="task",
                    entity_id=task.id,
                )
                await notify(
                    self.db,
                    organization_id=task.organization_id,
                    user_id=task.owner_id,
                    title="SLA breached",
                    body=task.title,
                    channel=NotificationChannel.SYSTEM,
                    entity_type="task",
                    entity_id=task.id,
                )
        elif warning_at and now >= warning_at and task.sla_state == SlaState.ACTIVE:
            task.sla_state = SlaState.WARNING
            await emit_event(
                self.db,
                organization_id=task.organization_id,
                event_type="sla.warning",
                entity_type="task",
                entity_id=task.id,
            )
            await notify(
                self.db,
                organization_id=task.organization_id,
                user_id=task.owner_id,
                title="SLA warning",
                body=task.title,
                channel=NotificationChannel.SYSTEM,
                entity_type="task",
                entity_id=task.id,
            )
        await self.db.flush()
        return task

    async def evaluate_case(self, case_id: UUID, now: datetime | None = None) -> CommunicationCase:
        now = now or datetime.now(UTC)
        case = await self.db.get(CommunicationCase, case_id)
        if not case:
            raise ValueError("Case not found")
        if case.status in (CaseStatus.COMPLETED, CaseStatus.CANCELLED) or case.sla_state == SlaState.NONE:
            return case
        deadline = case.deadline
        warning_at = None
        if case.sla_policy_id:
            policy = await self.db.get(SlaPolicy, case.sla_policy_id)
            if policy:
                from datetime import timedelta

                created = case.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                deadline = deadline or (created + timedelta(minutes=policy.response_minutes))
                warning_at = created + timedelta(minutes=policy.warning_minutes)
        if deadline and deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
        if deadline and now >= deadline:
            case.sla_state = SlaState.BREACHED
            case.status = CaseStatus.ESCALATED
            await emit_event(
                self.db,
                organization_id=case.organization_id,
                event_type="case.escalated",
                entity_type="case",
                entity_id=case.id,
            )
            if case.owner_id:
                await notify(
                    self.db,
                    organization_id=case.organization_id,
                    user_id=case.owner_id,
                    title=f"Case {case.case_number} escalated (SLA)",
                    body=case.subject,
                    channel=NotificationChannel.SYSTEM,
                    entity_type="case",
                    entity_id=case.id,
                )
        elif warning_at and now >= warning_at and case.sla_state == SlaState.ACTIVE:
            case.sla_state = SlaState.WARNING
            await emit_event(
                self.db,
                organization_id=case.organization_id,
                event_type="sla.warning",
                entity_type="case",
                entity_id=case.id,
            )
        await self.db.flush()
        return case


class TimelineService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def for_entity(self, entity_type: str, entity_id: UUID) -> list[Event]:
        result = await self.db.execute(
            select(Event)
            .where(Event.entity_type == entity_type, Event.entity_id == entity_id)
            .order_by(Event.created_at)
        )
        return list(result.scalars().all())

    async def for_user_activity(self, user_id: UUID) -> list[Event]:
        result = await self.db.execute(
            select(Event).where(Event.actor_id == user_id).order_by(Event.created_at.desc())
        )
        return list(result.scalars().all())

    async def for_work_item(self, work_item_id: UUID) -> list[Event]:
        """Include work item events plus related task/case events."""
        task_ids = (
            await self.db.execute(select(Task.id).where(Task.work_item_id == work_item_id))
        ).scalars().all()
        case_ids = (
            await self.db.execute(
                select(CommunicationCase.id).where(CommunicationCase.work_item_id == work_item_id)
            )
        ).scalars().all()
        result = await self.db.execute(
            select(Event)
            .where(
                (
                    (Event.entity_type == "work_item") & (Event.entity_id == work_item_id)
                )
                | ((Event.entity_type == "task") & (Event.entity_id.in_(list(task_ids) or [work_item_id])))
                | ((Event.entity_type == "case") & (Event.entity_id.in_(list(case_ids) or [work_item_id])))
            )
            .order_by(Event.created_at)
        )
        return list(result.scalars().all())
