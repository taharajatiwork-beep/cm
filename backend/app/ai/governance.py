"""AI Governance — human-in-the-loop approval for sensitive operations.

When REQUIRE_HUMAN_APPROVAL_FOR_SENSITIVE_AI=true:
- Sensitive tools return {approval_id, status: "pending_approval"} instead of executing
- Approval is requested via EnterpriseService.request_approval
- ToolExecutor checks approval status before execution
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings

# Tools that require human approval when the flag is enabled
SENSITIVE_TOOLS = frozenset(
    {
        "create_case",
        "create_task",
        "create_work_item",
        "assign_task",
        "assign_case",
        "prepare_divar_listing",
        "create_inventory_opportunity",
        "create_sales_follow_up",
        "create_purchase_opportunity",
        "escalate_case",
        "send_notification",
    }
)


def is_sensitive_tool(tool_name: str) -> bool:
    """Check if a tool requires human approval when governance is enabled."""
    return tool_name in SENSITIVE_TOOLS


def is_ai_governance_enabled() -> bool:
    """Check if human approval for sensitive AI operations is required."""
    return get_settings().require_human_approval_for_sensitive_ai


async def request_ai_approval(
    db,
    *,
    organization_id,
    requester_id,
    tool_name: str,
    title: str,
    payload: dict[str, Any],
    approver_ids: list,
) -> Any:
    """Create an approval request for a sensitive AI operation."""
    from app.services.enterprise_ops import EnterpriseService

    kind = f"ai.{tool_name}"
    return await EnterpriseService(db).request_approval(
        organization_id=organization_id,
        requester_id=requester_id,
        kind=kind,
        title=title,
        payload=payload,
        approver_ids=approver_ids,
    )


async def check_ai_approval(db, approval_id, actor_id) -> dict[str, Any]:
    """Check if an AI approval has been granted."""
    from app.services.enterprise_ops import EnterpriseService

    return await EnterpriseService(db).get_approval_status(approval_id, actor_id)