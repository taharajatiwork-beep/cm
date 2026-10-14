"""Centralized permission codes and helpers."""

from enum import StrEnum


class PermissionCode(StrEnum):
    ORG_ADMIN = "org.admin"
    USER_READ = "user.read"
    USER_WRITE = "user.write"
    RELATIONSHIP_WRITE = "relationship.write"
    CONVERSATION_READ = "conversation.read"
    CONVERSATION_WRITE = "conversation.write"
    WORK_ITEM_READ = "work_item.read"
    WORK_ITEM_WRITE = "work_item.write"
    CASE_READ = "case.read"
    CASE_WRITE = "case.write"
    TASK_READ = "task.read"
    TASK_WRITE = "task.write"
    TASK_ASSIGN = "task.assign"
    TASK_DELEGATE = "task.delegate"
    NOTIFICATION_READ = "notification.read"
    EVENT_READ = "event.read"
    SLA_MANAGE = "sla.manage"
    INVENTORY_READ = "inventory.read"
    INVENTORY_WRITE = "inventory.write"
    SEARCH = "search.run"
    RAG_READ = "rag.read"
    RAG_INDEX = "rag.index"
    AGENT_RUN = "agent.run"
    KB_READ = "kb.read"
    KB_WRITE = "kb.write"
    CUSTOMER_READ = "customer.read"
    CUSTOMER_WRITE = "customer.write"
    CAMPAIGN_READ = "campaign.read"
    CAMPAIGN_WRITE = "campaign.write"
    PRICE_WRITE = "price.write"
    PRICE_APPROVE = "price.approve"
    EXPENSE_PAY = "expense.pay"
    REPORT_READ = "report.read"
    PERF_READ = "perf.read"
    PERF_WRITE = "perf.write"
    PERF_APPROVE = "perf.approve"
    # درخواست → پروژه → کمپین. مدیرها درخواست می‌سازند، تیم تبدیل به پروژه می‌کند.
    REQUEST_CREATE = "request.create"
    REQUEST_TRIAGE = "request.triage"
    REQUEST_MANAGE = "request.manage"
    EXPENSE_REQUEST = "expense.request"
    EXPENSE_APPROVE = "expense.approve"
    CALENDAR_READ = "calendar.read"
    INQUIRY_CREATE = "inquiry.create"


def admin_role_permission_codes() -> list[str]:
    """همهٔ مجوزها به‌جز alias منسوخ price.write — org.admin همچنان همهٔ چک‌ها را دور می‌زند."""
    return [code.value for code in PermissionCode if code != PermissionCode.PRICE_WRITE]


class DataScopeLevel(StrEnum):
    ORGANIZATION = "organization"
    BRANCH = "branch"
    DEPARTMENT = "department"
    TEAM_TREE = "team_tree"
    TEAM = "team"
    SELF = "self"


# فهرست‌های مشترک شرکت. هر نقش واردشده این‌ها را می‌بیند؛ ساخت و ویرایش جدا می‌ماند.
SHARED_READ: tuple[str, ...] = (
    PermissionCode.INVENTORY_READ,
    PermissionCode.USER_READ,
    PermissionCode.KB_READ,
)

# چهار قالب. قابلیت‌های اضافه (تأیید هزینه، قیمت، پرفورمنس) روی خود کاربر می‌نشینند، نه نقش جدا.
ROLE_TEMPLATES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "requester": (
        "مدیر",
        DataScopeLevel.SELF,
        (
            PermissionCode.REQUEST_CREATE,
            PermissionCode.CAMPAIGN_READ,
            PermissionCode.CONVERSATION_READ,
            PermissionCode.CONVERSATION_WRITE,
            PermissionCode.NOTIFICATION_READ,
            PermissionCode.SEARCH,
            *SHARED_READ,
        ),
    ),
    "lead": (
        "سرپرست",
        DataScopeLevel.TEAM_TREE,
        (
            PermissionCode.REQUEST_TRIAGE,
            PermissionCode.REQUEST_MANAGE,
            PermissionCode.CONVERSATION_READ,
            PermissionCode.CONVERSATION_WRITE,
            PermissionCode.TASK_READ,
            PermissionCode.TASK_WRITE,
            PermissionCode.TASK_ASSIGN,
            PermissionCode.WORK_ITEM_READ,
            PermissionCode.NOTIFICATION_READ,
            PermissionCode.EVENT_READ,
            PermissionCode.EXPENSE_REQUEST,
            PermissionCode.SEARCH,
            PermissionCode.CAMPAIGN_READ,
            *SHARED_READ,
        ),
    ),
    "member": (
        "عضو",
        DataScopeLevel.TEAM,
        (
            PermissionCode.TASK_READ,
            PermissionCode.TASK_WRITE,
            PermissionCode.CONVERSATION_READ,
            PermissionCode.CONVERSATION_WRITE,
            PermissionCode.NOTIFICATION_READ,
            PermissionCode.EXPENSE_REQUEST,
            *SHARED_READ,
        ),
    ),
    "reporter": (
        "گزارش‌گیر",
        DataScopeLevel.TEAM,
        (
            PermissionCode.REPORT_READ,
            PermissionCode.NOTIFICATION_READ,
            PermissionCode.USER_READ,
            PermissionCode.KB_READ,
        ),
    ),
}


class AuthorizationError(Exception):
    def __init__(self, message: str = "Not authorized"):
        self.message = message
        super().__init__(message)


def require_permission(user_permissions: set[str], code: str) -> None:
    if PermissionCode.ORG_ADMIN in user_permissions:
        return
    if code not in user_permissions:
        raise AuthorizationError(f"Missing permission: {code}")


def require_any_permission(user_permissions: set[str], *codes: str) -> None:
    if PermissionCode.ORG_ADMIN in user_permissions:
        return
    if any(c in user_permissions for c in codes):
        return
    raise AuthorizationError(f"Missing one of permissions: {', '.join(codes)}")


def require_price_approve(user_permissions: set[str]) -> None:
    require_any_permission(
        user_permissions,
        PermissionCode.PRICE_APPROVE,
        PermissionCode.PRICE_WRITE,
    )


def require_expense_pay(user_permissions: set[str]) -> None:
    require_any_permission(
        user_permissions,
        PermissionCode.EXPENSE_PAY,
        PermissionCode.PRICE_WRITE,
    )
