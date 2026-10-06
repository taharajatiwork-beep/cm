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
    PERF_READ = "perf.read"
    PERF_WRITE = "perf.write"
    PERF_APPROVE = "perf.approve"


class DataScopeLevel(StrEnum):
    ORGANIZATION = "organization"
    BRANCH = "branch"
    DEPARTMENT = "department"
    TEAM = "team"
    SELF = "self"


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
