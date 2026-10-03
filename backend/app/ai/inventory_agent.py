"""InventoryAgent — aging, demand, and opportunity detection via tools only."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools import ToolContext, ToolExecutor
from app.core.config import get_settings
from app.core.permissions import PermissionCode, require_any_permission
from app.models import User
from app.services import get_user_permissions


@dataclass
class InventoryAgentResult:
    request_id: str
    ok: bool
    intent: str
    message: str
    clarification: str | None = None
    opportunities_found: int = 0
    cases_created: list[str] = field(default_factory=list)
    work_item_ids: list[str] = field(default_factory=list)
    tool_trace: list[dict[str, Any]] = field(default_factory=list)


class InventoryAgent:
    """Scans aged inventory against branch/customer demand; recommends or creates opportunities."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run(
        self,
        *,
        user: User,
        message: str | None = None,
        min_days: int | None = None,
        min_branch_requests: int | None = None,
        auto_create: bool | None = None,
    ) -> InventoryAgentResult:
        request_id = str(uuid.uuid4())
        permissions = await get_user_permissions(self.db, user)
        require_any_permission(
            permissions, PermissionCode.AGENT_RUN, PermissionCode.INVENTORY_READ
        )

        settings = get_settings()
        aging_days = min_days if min_days is not None else settings.inventory_aging_days
        min_branches = (
            min_branch_requests
            if min_branch_requests is not None
            else settings.inventory_min_branch_requests
        )
        should_create = (
            auto_create if auto_create is not None else settings.inventory_auto_create_opportunity
        )

        # Light intent from optional free-text
        text = (message or "").lower()
        scan_only = any(s in text for s in ("scan", "فقط", "report", "گزارش", "list"))
        if "create" in text or "بساز" in text or "ایجاد" in text:
            should_create = True
        if scan_only and "create" not in text and "بساز" not in text:
            should_create = False
        if should_create and PermissionCode.CASE_WRITE not in permissions and PermissionCode.ORG_ADMIN not in permissions:
            should_create = False

        ctx = ToolContext(
            self.db,
            organization_id=user.organization_id,
            user=user,
            permissions=permissions,
            request_id=request_id,
            agent="InventoryAgent",
            model="rules-v1",
            prompt_version="inv-1",
        )
        executor = ToolExecutor(ctx)
        trace: list[dict[str, Any]] = []

        aging = await executor.execute("list_aging_inventory", {"min_days": aging_days})
        trace.append({"tool": "list_aging_inventory", "args": {"min_days": aging_days}, "result": aging})
        if not aging.get("ok"):
            return InventoryAgentResult(
                request_id=request_id,
                ok=False,
                intent="error",
                message=aging.get("error", "Aging scan failed"),
                tool_trace=trace,
            )

        detected = await executor.execute(
            "detect_inventory_opportunities",
            {"min_days": aging_days, "min_branch_requests": min_branches},
        )
        trace.append(
            {
                "tool": "detect_inventory_opportunities",
                "args": {"min_days": aging_days, "min_branch_requests": min_branches},
                "result": detected,
            }
        )
        if not detected.get("ok"):
            return InventoryAgentResult(
                request_id=request_id,
                ok=False,
                intent="error",
                message=detected.get("error", "Opportunity detection failed"),
                tool_trace=trace,
            )

        opps: list[dict[str, Any]] = (detected.get("data") or {}).get("opportunities") or []
        aging_count = (aging.get("data") or {}).get("count") or 0

        if not opps:
            return InventoryAgentResult(
                request_id=request_id,
                ok=True,
                intent="scan",
                message=(
                    f"Scanned {aging_count} aged vehicle(s) (≥{aging_days} days). "
                    "No inventory opportunities matched branch/customer demand signals."
                ),
                opportunities_found=0,
                tool_trace=trace,
            )

        cases_created: list[str] = []
        work_ids: list[str] = []

        if should_create:
            for opp in opps:
                result = await executor.execute(
                    "create_inventory_opportunity",
                    {
                        "vehicle_id": opp["id"],
                        "reasons": opp.get("reasons") or [],
                        "create_work_item": True,
                    },
                )
                trace.append(
                    {
                        "tool": "create_inventory_opportunity",
                        "args": {"vehicle_id": opp["id"]},
                        "result": result,
                    }
                )
                if not result.get("ok"):
                    return InventoryAgentResult(
                        request_id=request_id,
                        ok=False,
                        intent="create_opportunities",
                        message=result.get("error", "Failed to create opportunity"),
                        opportunities_found=len(opps),
                        cases_created=cases_created,
                        work_item_ids=work_ids,
                        tool_trace=trace,
                    )
                data = result.get("data") or {}
                if data.get("case_id"):
                    cases_created.append(data["case_id"])
                if data.get("work_item_id"):
                    work_ids.append(data["work_item_id"])

            lines = [
                f"Found {len(opps)} opportunity(ies); created {len(cases_created)} case(s)."
            ]
            for opp in opps:
                lines.append(
                    f"- {opp.get('brand')} {opp.get('model')} "
                    f"#{opp.get('stock_number')} · {opp.get('days_in_stock')}d · "
                    f"{', '.join(opp.get('reasons') or [])}"
                )
            return InventoryAgentResult(
                request_id=request_id,
                ok=True,
                intent="create_opportunities",
                message="\n".join(lines),
                opportunities_found=len(opps),
                cases_created=cases_created,
                work_item_ids=work_ids,
                tool_trace=trace,
            )

        # Recommend only
        lines = [f"Found {len(opps)} recommended inventory opportunity(ies) (not created):"]
        for opp in opps:
            lines.append(
                f"- vehicle={opp['id']} {opp.get('brand')} {opp.get('model')} "
                f"#{opp.get('stock_number')} · score={opp.get('score')} · "
                f"{', '.join(opp.get('reasons') or [])}"
            )
        return InventoryAgentResult(
            request_id=request_id,
            ok=True,
            intent="recommend",
            message="\n".join(lines),
            opportunities_found=len(opps),
            tool_trace=trace,
        )
