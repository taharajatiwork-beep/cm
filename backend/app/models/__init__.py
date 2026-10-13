from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.ai_audit import AiActionLog  # noqa: F401
from app.models.campaign import Campaign  # noqa: F401
from app.models.customer import Customer  # noqa: F401
from app.models.divar import DivarListing  # noqa: F401
from app.models.embeddings import Embedding  # noqa: F401
from app.models.enterprise import (  # noqa: F401
    AiUsage,
    ApprovalRequest,
    ApprovalStep,
    IdempotencyRecord,
    JobLock,
    KpiSnapshot,
    RefreshToken,
    ReportSchedule,
    StoredFile,
    TeamNotice,
    UserPermissionGrant,
    UserTeam,
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
from app.models.inventory import (  # noqa: F401 — register metadata
    InventoryRequest,
    Vehicle,
    VehicleBranch,
    VehicleHistory,
    VehiclePrice,
)
from app.models.pricing import PostSlot  # noqa: F401
from app.calendar.models import CalendarEntry, CalendarMonth  # noqa: F401
from app.requests import models as _request_models  # noqa: F401
from app.perf.models import (  # noqa: F401
    PmBlacklist,
    PmCampaign,
    PmCarRequest,
    PmCost,
    PmIntegration,
    PmLead,
    PmMizitoCursor,
    PmMizitoRequest,
    PmPage,
    PmPagePrice,
    PmPanel,
    PmPaymentRequest,
    PmPhoneTouch,
    PmPishgamAudit,
    PmPishgamPreview,
    PmRecipient,
    PmRecipientList,
    PmRefCity,
    PmRefDeviceBrand,
    PmRefDeviceType,
    PmRefProvince,
    PmSmsSend,
    PmStory,
)
from app.models.knowledge import Document, DocumentChunk  # noqa: F401
from app.models.telegram import (  # noqa: F401
    TelegramAccount,
    TelegramOutbox,
    TelegramPendingConfirm,
    TelegramProcessedUpdate,
)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    branches: Mapped[list[Branch]] = relationship(back_populates="organization")
    departments: Mapped[list[Department]] = relationship(back_populates="organization")
    teams: Mapped[list[Team]] = relationship(back_populates="organization")
    users: Mapped[list[User]] = relationship(back_populates="organization")


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="branches")


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="departments")
    teams: Mapped[list[Team]] = relationship(back_populates="department")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    parent_team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="teams")
    department: Mapped[Department | None] = relationship(back_populates="teams")
    parent_team: Mapped[Team | None] = relationship(remote_side=[id])


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    permissions: Mapped[list[RolePermission]] = relationship(back_populates="role")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), nullable=False)
    permission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permissions.id"), nullable=False)

    role: Mapped[Role] = relationship(back_populates="permissions")
    permission: Mapped[Permission] = relationship()


class DataScope(Base):
    __tablename__ = "data_scopes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=False)  # organization|branch|department|team|self
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("organization_id", "email"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))
    role_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("roles.id"))
    manager_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="users")
    role: Mapped[Role | None] = relationship()
    manager: Mapped[User | None] = relationship(remote_side="User.id")
    skills: Mapped[list[UserSkill]] = relationship(back_populates="user")


class UserSkill(Base):
    __tablename__ = "user_skills"
    __table_args__ = (UniqueConstraint("user_id", "skill_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    skill_code: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="skills")


class OrgRelationship(Base):
    __tablename__ = "relationships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "from_user_id",
            "to_user_id",
            "relationship_type",
            name="uq_relationship",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    from_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    to_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    relationship_type: Mapped[RelationshipType] = mapped_column(
        Enum(RelationshipType, name="relationship_type"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    channel: Mapped[Channel] = mapped_column(Enum(Channel, name="channel"), nullable=False)
    topic: Mapped[str | None] = mapped_column(String(255))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))
    work_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("work_items.id"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    pm_campaign_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"))  # CRM
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("campaigns.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # آرشیو: پر شدن این فلد یعنی آرشیو؛ topic دست نمی‌خورد (Consistency / مرحله ۶)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    participants: Mapped[list[ConversationParticipant]] = relationship(back_populates="conversation")
    messages: Mapped[list[Message]] = relationship(back_populates="conversation")


class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"
    __table_args__ = (UniqueConstraint("conversation_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[ParticipantRole] = mapped_column(
        Enum(ParticipantRole, name="participant_role"), default=ParticipantRole.MEMBER
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="participants")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    channel: Mapped[Channel] = mapped_column(Enum(Channel, name="channel", create_constraint=False), nullable=False)
    channel_message_id: Mapped[str | None] = mapped_column(String(255))
    sender_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    topic_id: Mapped[str | None] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[MessageType] = mapped_column(
        Enum(MessageType, name="message_type"), default=MessageType.TEXT
    )
    reply_to_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"))
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    perf_campaign_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class SlaPolicy(Base):
    __tablename__ = "sla_policies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[Priority] = mapped_column(Enum(Priority, name="priority"), nullable=False)
    response_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    escalate_on_breach: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkItem(Base):
    __tablename__ = "work_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[WorkItemStatus] = mapped_column(
        Enum(WorkItemStatus, name="work_item_status"), default=WorkItemStatus.OPEN
    )
    priority: Mapped[Priority] = mapped_column(Enum(Priority, name="priority", create_constraint=False), default=Priority.MEDIUM)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    participants: Mapped[list[WorkItemParticipant]] = relationship(back_populates="work_item")
    tasks: Mapped[list[Task]] = relationship(back_populates="work_item")
    cases: Mapped[list[CommunicationCase]] = relationship(back_populates="work_item")


class WorkItemParticipant(Base):
    __tablename__ = "work_item_participants"
    __table_args__ = (UniqueConstraint("work_item_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    work_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_items.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[ParticipantRole] = mapped_column(
        Enum(ParticipantRole, name="participant_role", create_constraint=False),
        default=ParticipantRole.MEMBER,
    )

    work_item: Mapped[WorkItem] = relationship(back_populates="participants")


class CommunicationCase(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    case_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    work_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("work_items.id"))
    type: Mapped[CaseType] = mapped_column(Enum(CaseType, name="case_type"), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus, name="case_status"), default=CaseStatus.OPEN)
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, name="priority", create_constraint=False), default=Priority.MEDIUM
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_policy_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sla_policies.id"))
    sla_state: Mapped[SlaState] = mapped_column(Enum(SlaState, name="sla_state"), default=SlaState.NONE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    work_item: Mapped[WorkItem | None] = relationship(back_populates="cases")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    work_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("work_items.id"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus, name="task_status"), default=TaskStatus.OPEN)
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, name="priority", create_constraint=False), default=Priority.MEDIUM
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Team/dept/branch assignment target (person may be unresolved)
    assignment_target_type: Mapped[AssignmentTargetType | None] = mapped_column(
        Enum(AssignmentTargetType, name="assignment_target_type")
    )
    assignment_target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_policy_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sla_policies.id"))
    sla_state: Mapped[SlaState] = mapped_column(
        Enum(SlaState, name="sla_state", create_constraint=False), default=SlaState.NONE
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    work_item: Mapped[WorkItem | None] = relationship(back_populates="tasks")
    assignees: Mapped[list[TaskAssignee]] = relationship(back_populates="task")
    participants: Mapped[list[TaskParticipant]] = relationship(back_populates="task")
    dependencies_as_dependent: Mapped[list[TaskDependency]] = relationship(
        back_populates="dependent_task",
        foreign_keys="TaskDependency.dependent_task_id",
    )


class TaskAssignee(Base):
    __tablename__ = "task_assignees"
    __table_args__ = (UniqueConstraint("task_id", "user_id", "role"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[TaskRole] = mapped_column(Enum(TaskRole, name="task_role"), default=TaskRole.ASSIGNEE)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[Task] = relationship(back_populates="assignees")


class TaskParticipant(Base):
    __tablename__ = "task_participants"
    __table_args__ = (UniqueConstraint("task_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[TaskRole] = mapped_column(
        Enum(TaskRole, name="task_role", create_constraint=False), default=TaskRole.FOLLOWER
    )

    task: Mapped[Task] = relationship(back_populates="participants")


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (UniqueConstraint("dependent_task_id", "prerequisite_task_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    dependent_task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    prerequisite_task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dependent_task: Mapped[Task] = relationship(
        back_populates="dependencies_as_dependent",
        foreign_keys=[dependent_task_id],
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Event(Base):
    """Append-only organizational event log."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    payload: Mapped[str | None] = mapped_column(Text)  # JSON string
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # زنجیرهٔ هش (audit tamper-evident): prev_hash به سطر قبلی در همان سازمان اشاره می‌کند
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    row_hash: Mapped[str | None] = mapped_column(String(64))
    # شمارهٔ ترتیبی در زنجیره (شروع از ۱) — ترتیب را صریح می‌کند چون created_at
    # در SQLite میلی‌ثانیه‌ای نیست و چند سطر می‌توانند زمان یکسان داشته باشند.
    chain_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
