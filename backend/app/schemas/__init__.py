from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import (
    AssignmentTargetType,
    CaseStatus,
    CaseType,
    Channel,
    InventoryRequestStatus,
    InventoryRequestType,
    MessageType,
    NotificationChannel,
    Priority,
    RelationshipType,
    SlaState,
    TaskRole,
    TaskStatus,
    VehicleStatus,
    WorkItemStatus,
)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginIn(BaseModel):
    organization_slug: str
    email: EmailStr
    password: str


class BootstrapIn(BaseModel):
    organization_name: str
    organization_slug: str
    admin_email: EmailStr
    admin_name: str
    admin_password: str = Field(min_length=6)


class OrganizationOut(BaseModel):
    id: UUID
    name: str
    slug: str

    model_config = {"from_attributes": True}


class BranchCreate(BaseModel):
    name: str
    code: str
    city: str | None = None


class BranchOut(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    code: str
    city: str | None

    model_config = {"from_attributes": True}


class DepartmentCreate(BaseModel):
    name: str
    code: str


class DepartmentOut(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    code: str

    model_config = {"from_attributes": True}


class TeamCreate(BaseModel):
    name: str
    code: str
    department_id: UUID | None = None


class TeamOut(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    code: str
    department_id: UUID | None
    parent_team_id: UUID | None = None

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(min_length=6)
    role_id: UUID | None = None
    branch_id: UUID | None = None
    department_id: UUID | None = None
    team_id: UUID | None = None
    manager_id: UUID | None = None


class UserOut(BaseModel):
    id: UUID
    organization_id: UUID
    email: EmailStr
    full_name: str
    is_active: bool
    branch_id: UUID | None
    department_id: UUID | None
    team_id: UUID | None
    role_id: UUID | None
    manager_id: UUID | None

    model_config = {"from_attributes": True}


class MeOut(UserOut):
    permissions: list[str]
    role_code: str | None = None
    role_name: str | None = None
    branch_name: str | None = None
    team_home_team_id: UUID | None = None


class RelationshipCreate(BaseModel):
    from_user_id: UUID
    to_user_id: UUID
    relationship_type: RelationshipType


class RelationshipOut(BaseModel):
    id: UUID
    organization_id: UUID
    from_user_id: UUID
    to_user_id: UUID
    relationship_type: RelationshipType

    model_config = {"from_attributes": True}


class ConversationCreate(BaseModel):
    channel: Channel = Channel.WEB
    topic: str | None = None
    participant_ids: list[UUID]
    branch_id: UUID | None = None
    team_id: UUID | None = None
    work_item_id: UUID | None = None
    case_id: UUID | None = None
    vehicle_id: UUID | None = None
    customer_id: UUID | None = None
    campaign_id: UUID | None = None


class ConversationOut(BaseModel):
    id: UUID
    organization_id: UUID
    channel: Channel
    topic: str | None
    branch_id: UUID | None
    team_id: UUID | None
    work_item_id: UUID | None
    project_id: UUID | None = None
    pm_campaign_id: UUID | None = None
    case_id: UUID | None
    vehicle_id: UUID | None
    customer_id: UUID | None
    campaign_id: UUID | None
    participant_ids: list[UUID] = []
    last_message_text: str | None = None
    last_sender_id: UUID | None = None
    last_message_at: datetime | None = None
    needs_reply: bool = False

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    text: str
    channel: Channel = Channel.WEB
    message_type: MessageType = MessageType.TEXT
    reply_to_message_id: UUID | None = None


class MessageOut(BaseModel):
    id: UUID
    organization_id: UUID
    conversation_id: UUID
    channel: Channel
    sender_id: UUID | None
    text: str
    message_type: MessageType
    reply_to_message_id: UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkItemCreate(BaseModel):
    title: str
    description: str | None = None
    priority: Priority = Priority.MEDIUM
    branch_id: UUID | None = None
    vehicle_id: UUID | None = None
    customer_id: UUID | None = None
    deadline: datetime | None = None
    participant_ids: list[UUID] = []


class WorkItemOut(BaseModel):
    id: UUID
    organization_id: UUID
    title: str
    description: str | None
    status: WorkItemStatus
    priority: Priority
    owner_id: UUID
    branch_id: UUID | None
    vehicle_id: UUID | None
    customer_id: UUID | None
    deadline: datetime | None

    model_config = {"from_attributes": True}


class CaseCreate(BaseModel):
    subject: str
    type: CaseType = CaseType.GENERAL_OPERATIONAL_REQUEST
    work_item_id: UUID | None = None
    owner_id: UUID | None = None
    priority: Priority = Priority.MEDIUM
    branch_id: UUID | None = None
    vehicle_id: UUID | None = None
    customer_id: UUID | None = None
    deadline: datetime | None = None
    sla_policy_id: UUID | None = None


class CaseUpdate(BaseModel):
    """تغییر وضعیت/مسئول پرونده — فیلدهای نفرستاده‌شده دست‌نخورده می‌مانند."""
    status: CaseStatus | None = None
    owner_id: UUID | None = None


class CaseOut(BaseModel):
    id: UUID
    case_number: str
    organization_id: UUID
    work_item_id: UUID | None
    type: CaseType
    subject: str
    status: CaseStatus
    priority: Priority
    created_by: UUID
    owner_id: UUID | None
    vehicle_id: UUID | None = None
    customer_id: UUID | None = None
    branch_id: UUID | None = None
    sla_state: SlaState
    deadline: datetime | None

    model_config = {"from_attributes": True}


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    work_item_id: UUID | None = None
    case_id: UUID | None = None
    project_id: UUID | None = None
    request_id: UUID | None = None
    priority: Priority = Priority.MEDIUM
    assignee_ids: list[UUID] = []
    assignment_target_type: AssignmentTargetType | None = None
    assignment_target_id: UUID | None = None
    deadline: datetime | None = None
    sla_policy_id: UUID | None = None


class TaskAssigneeOut(BaseModel):
    user_id: UUID
    role: TaskRole

    model_config = {"from_attributes": True}


class TaskOut(BaseModel):
    id: UUID
    organization_id: UUID
    work_item_id: UUID | None
    case_id: UUID | None
    project_id: UUID | None = None
    request_id: UUID | None = None
    title: str
    description: str | None
    status: TaskStatus
    priority: Priority
    owner_id: UUID
    assignment_target_type: AssignmentTargetType | None
    assignment_target_id: UUID | None
    deadline: datetime | None
    sla_state: SlaState

    model_config = {"from_attributes": True}


class TaskDependencyCreate(BaseModel):
    dependent_task_id: UUID
    prerequisite_task_id: UUID


class DelegateIn(BaseModel):
    to_user_id: UUID | None = None
    to_target_type: AssignmentTargetType | None = None
    to_target_id: UUID | None = None


class SlaPolicyCreate(BaseModel):
    name: str
    priority: Priority
    response_minutes: int
    warning_minutes: int
    escalate_on_breach: bool = True


class SlaPolicyOut(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    priority: Priority
    response_minutes: int
    warning_minutes: int
    escalate_on_breach: bool

    model_config = {"from_attributes": True}


class NotificationOut(BaseModel):
    id: UUID
    user_id: UUID
    channel: NotificationChannel
    title: str
    body: str
    entity_type: str | None
    entity_id: UUID | None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class EventOut(BaseModel):
    id: UUID
    event_type: str
    actor_id: UUID | None
    entity_type: str
    entity_id: UUID
    payload: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProgressOut(BaseModel):
    work_item_id: UUID
    title: str
    status: str
    total_tasks: int
    completed_tasks: int
    overdue_tasks: int
    progress_pct: float
    tasks: list[dict]
    participants: list[dict] = []


class VehicleCreate(BaseModel):
    vin: str | None = None
    brand: str
    model: str
    year: int
    stock_number: str | None = None
    color: str | None = None
    trim: str | None = None
    mileage: int | None = None
    purchase_price: int | None = None
    sale_price: int | None = None
    currency: str = "IRR"
    description: str | None = None
    notes: str | None = None
    body_type: str | None = None
    transmission: str | None = None
    fuel_type: str | None = None
    engine: str | None = None
    plate_number: str | None = None
    doors: int | None = None
    seats: int | None = None
    options: str | None = None
    exterior_condition: str | None = None
    interior_condition: str | None = None
    import_source: str | None = None
    branch_id: UUID | None = None
    owner_id: UUID | None = None
    status: VehicleStatus = VehicleStatus.IN_STOCK
    delivery_note: str | None = None


class VehicleUpdate(BaseModel):
    vin: str | None = None
    brand: str | None = None
    model: str | None = None
    year: int | None = None
    stock_number: str | None = None
    color: str | None = None
    trim: str | None = None
    mileage: int | None = None
    sale_price: int | None = None
    purchase_price: int | None = None
    status: VehicleStatus | None = None
    branch_id: UUID | None = None
    delivery_note: str | None = None
    description: str | None = None
    notes: str | None = None
    body_type: str | None = None
    transmission: str | None = None
    fuel_type: str | None = None
    engine: str | None = None
    plate_number: str | None = None
    doors: int | None = None
    seats: int | None = None
    options: str | None = None
    exterior_condition: str | None = None
    interior_condition: str | None = None


class VehicleOut(BaseModel):
    id: UUID
    organization_id: UUID
    stock_number: str | None
    vin: str | None
    brand: str
    model: str
    year: int
    color: str | None
    trim: str | None
    mileage: int | None
    purchase_price: int | None
    sale_price: int | None
    currency: str
    description: str | None = None
    notes: str | None = None
    body_type: str | None = None
    transmission: str | None = None
    fuel_type: str | None = None
    engine: str | None = None
    plate_number: str | None = None
    doors: int | None = None
    seats: int | None = None
    options: str | None = None
    exterior_condition: str | None = None
    interior_condition: str | None = None
    import_source: str | None = None
    branch_id: UUID | None
    owner_id: UUID | None
    status: VehicleStatus
    delivery_note: str | None = None
    price_updated_at: datetime | None = None
    price_updated_by: UUID | None = None
    stock_updated_at: datetime | None = None
    stock_updated_by: UUID | None = None

    model_config = {"from_attributes": True}


class VehicleImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[str] = []
    vehicles: list[VehicleOut] = []


class VehicleStatusChange(BaseModel):
    to_status: VehicleStatus
    note: str | None = None


class VehicleBranchLink(BaseModel):
    branch_id: UUID
    is_primary: bool = False
    note: str | None = None


class VehicleHistoryOut(BaseModel):
    id: UUID
    vehicle_id: UUID
    actor_id: UUID | None
    from_status: VehicleStatus | None
    to_status: VehicleStatus
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InventoryRequestCreate(BaseModel):
    subject: str
    requesting_branch_id: UUID
    vehicle_id: UUID | None = None
    target_branch_id: UUID | None = None
    request_type: InventoryRequestType = InventoryRequestType.GENERAL
    notes: str | None = None
    work_item_id: UUID | None = None
    case_id: UUID | None = None


class InventoryRequestOut(BaseModel):
    id: UUID
    organization_id: UUID
    vehicle_id: UUID | None
    requesting_branch_id: UUID
    target_branch_id: UUID | None
    requested_by: UUID
    request_type: InventoryRequestType
    status: InventoryRequestStatus
    subject: str
    notes: str | None
    work_item_id: UUID | None
    case_id: UUID | None

    model_config = {"from_attributes": True}


class VehicleContextOut(BaseModel):
    vehicle: VehicleOut
    work_items: list[WorkItemOut]
    cases: list[CaseOut]
    inventory_requests: list[InventoryRequestOut]
    history: list[VehicleHistoryOut]
