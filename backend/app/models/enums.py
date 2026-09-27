import enum


class RelationshipType(str, enum.Enum):
    MANAGES = "MANAGES"
    REPORTS_TO = "REPORTS_TO"
    WORKS_WITH = "WORKS_WITH"
    COLLABORATES_WITH = "COLLABORATES_WITH"
    MEMBER_OF = "MEMBER_OF"
    DELEGATES_TO = "DELEGATES_TO"


class Channel(str, enum.Enum):
    TELEGRAM = "TELEGRAM"
    WEB = "WEB"
    SYSTEM = "SYSTEM"
    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"
    PHONE = "PHONE"


class MessageType(str, enum.Enum):
    TEXT = "TEXT"
    VOICE = "VOICE"
    IMAGE = "IMAGE"
    DOCUMENT = "DOCUMENT"
    SYSTEM = "SYSTEM"
    AI = "AI"


class CaseType(str, enum.Enum):
    BRANCH_REQUEST = "BRANCH_REQUEST"
    BUYER_REQUEST = "BUYER_REQUEST"
    SELLER_REQUEST = "SELLER_REQUEST"
    FOLLOW_UP = "FOLLOW_UP"
    INVENTORY_OPPORTUNITY = "INVENTORY_OPPORTUNITY"
    CUSTOMER_INTEREST = "CUSTOMER_INTEREST"
    TRANSFER = "TRANSFER"
    ESCALATION = "ESCALATION"
    GENERAL_OPERATIONAL_REQUEST = "GENERAL_OPERATIONAL_REQUEST"


class CaseStatus(str, enum.Enum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_FOR_RESPONSE = "WAITING_FOR_RESPONSE"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ESCALATED = "ESCALATED"


class Priority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class WorkItemStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TaskStatus(str, enum.Enum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TaskRole(str, enum.Enum):
    OWNER = "OWNER"
    ASSIGNEE = "ASSIGNEE"
    REVIEWER = "REVIEWER"
    APPROVER = "APPROVER"
    FOLLOWER = "FOLLOWER"


class AssignmentTargetType(str, enum.Enum):
    USER = "USER"
    TEAM = "TEAM"
    DEPARTMENT = "DEPARTMENT"
    BRANCH = "BRANCH"


class SlaState(str, enum.Enum):
    NONE = "NONE"
    ACTIVE = "ACTIVE"
    WARNING = "WARNING"
    BREACHED = "BREACHED"
    ESCALATED = "ESCALATED"


class NotificationChannel(str, enum.Enum):
    TELEGRAM = "TELEGRAM"
    WEB = "WEB"
    SYSTEM = "SYSTEM"


class ParticipantRole(str, enum.Enum):
    OWNER = "OWNER"
    MEMBER = "MEMBER"
    WATCHER = "WATCHER"


class VehicleStatus(str, enum.Enum):
    IN_STOCK = "IN_STOCK"
    RESERVED = "RESERVED"
    SOLD = "SOLD"
    IN_TRANSIT = "IN_TRANSIT"
    UNDER_REVIEW = "UNDER_REVIEW"
    PURCHASE_REQUESTED = "PURCHASE_REQUESTED"
    SOLD_PENDING_DELIVERY = "SOLD_PENDING_DELIVERY"


class InventoryRequestStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


class InventoryRequestType(str, enum.Enum):
    AVAILABILITY_CHECK = "AVAILABILITY_CHECK"
    TRANSFER = "TRANSFER"
    INTEREST = "INTEREST"
    GENERAL = "GENERAL"


class CampaignStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
