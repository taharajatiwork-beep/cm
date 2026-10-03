"""SalesAgent — pipeline scan, inventory match, stale follow-up via tools only."""

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
class SalesAgentResult:
    request_id: str
    ok: bool
    intent: str
    message: str
    clarification: str | None = None
    follow_ups_found: int = 0
    cases_created: list[str] = field(default_factory=list)
    work_item_ids: list[str] = field(default_factory=list)
    task_ids: list[str] = field(default_factory=list)
    tool_trace: list[dict[str, Any]] = field(default_factory=list)


class SalesAgent:
    """Sales pipeline orchestration on Core cases + inventory matching."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run(
        self,
        *,
        user: User,
        message: str | None = None,
        stale_days: int | None = None,
        auto_create: bool | None = None,
        case_id: str | None = None,
    ) -> SalesAgentResult:
        request_id = str(uuid.uuid4())
        permissions = await get_user_permissions(self.db, user)
        require_any_permission(
            permissions, PermissionCode.AGENT_RUN, PermissionCode.CUSTOMER_READ
        )

        settings = get_settings()
        days = stale_days if stale_days is not None else settings.sales_stale_days
        should_create = (
            auto_create if auto_create is not None else settings.sales_auto_create_follow_up
        )

        text = (message or "").lower()
        pipeline_only = any(s in text for s in ("pipeline", "لیست", "list", "گزارش"))
        match_only = any(s in text for s in ("match", "موجودی", "match inventory"))
        scan_only = any(s in text for s in ("scan", "فقط", "report"))
        if "create" in text or "بساز" in text or "پیگیری" in text or "follow" in text:
            should_create = True
        if (pipeline_only or match_only or scan_only) and not any(
            s in text for s in ("create", "بساز", "پیگیری", "follow")
        ):
            should_create = False
        if should_create and PermissionCode.CASE_WRITE not in permissions and PermissionCode.ORG_ADMIN not in permissions:
            should_create = False

        ctx = ToolContext(
            self.db,
            organization_id=user.organization_id,
            user=user,
            permissions=permissions,
            request_id=request_id,
            agent="SalesAgent",
            model="rules-v1",
            prompt_version="sales-1",
        )
        executor = ToolExecutor(ctx)
        trace: list[dict[str, Any]] = []

        # Explicit single-case match
        if case_id or match_only:
            target = case_id
            if not target:
                pipe = await executor.execute("list_sales_pipeline", {})
                trace.append({"tool": "list_sales_pipeline", "args": {}, "result": pipe})
                if not pipe.get("ok"):
                    return self._fail(request_id, pipe, trace)
                cases = (pipe.get("data") or {}).get("cases") or []
                if not cases:
                    return SalesAgentResult(
                        request_id=request_id,
                        ok=True,
                        intent="match",
                        message="No open sales cases to match.",
                        tool_trace=trace,
                    )
                target = cases[0]["id"]

            match = await executor.execute("match_buyer_to_inventory", {"case_id": target})
            trace.append(
                {"tool": "match_buyer_to_inventory", "args": {"case_id": target}, "result": match}
            )
            if not match.get("ok"):
                return self._fail(request_id, match, trace)
            data = match.get("data") or {}
            lines = [
                f"Matched case {data.get('case_number')}: {data.get('match_count', 0)} vehicle(s)."
            ]
            for v in data.get("matches") or []:
                lines.append(
                    f"- {v.get('brand')} {v.get('model')} #{v.get('stock_number')} "
                    f"(VIN …{str(v.get('vin', ''))[-6:]})"
                )
            if not data.get("matches"):
                lines.append("No in-stock match for subject hints — clarify model/stock.")
            return SalesAgentResult(
                request_id=request_id,
                ok=True,
                intent="match",
                message="\n".join(lines),
                tool_trace=trace,
            )

        if pipeline_only:
            pipe = await executor.execute("list_sales_pipeline", {})
            trace.append({"tool": "list_sales_pipeline", "args": {}, "result": pipe})
            if not pipe.get("ok"):
                return self._fail(request_id, pipe, trace)
            cases = (pipe.get("data") or {}).get("cases") or []
            lines = [f"Sales pipeline: {len(cases)} open case(s)."]
            for c in cases[:15]:
                lines.append(
                    f"- {c.get('case_number')} [{c.get('type')}] {c.get('subject')} "
                    f"· {c.get('days_open')}d · {c.get('status')}"
                )
            return SalesAgentResult(
                request_id=request_id,
                ok=True,
                intent="pipeline",
                message="\n".join(lines),
                tool_trace=trace,
            )

        detected = await executor.execute("detect_sales_follow_ups", {"stale_days": days})
        trace.append(
            {
                "tool": "detect_sales_follow_ups",
                "args": {"stale_days": days},
                "result": detected,
            }
        )
        if not detected.get("ok"):
            return self._fail(request_id, detected, trace)

        follow_ups: list[dict[str, Any]] = (detected.get("data") or {}).get("follow_ups") or []
        if not follow_ups:
            return SalesAgentResult(
                request_id=request_id,
                ok=True,
                intent="scan",
                message=f"No stale sales cases (≥{days} days) needing follow-up.",
                follow_ups_found=0,
                tool_trace=trace,
            )

        cases_created: list[str] = []
        work_ids: list[str] = []
        task_ids: list[str] = []

        if should_create:
            for item in follow_ups:
                vehicle_id = item.get("vehicle_id")
                matches = item.get("inventory_matches") or []
                if not vehicle_id and matches:
                    vehicle_id = matches[0].get("id")
                result = await executor.execute(
                    "create_sales_follow_up",
                    {
                        "case_id": item["id"],
                        "vehicle_id": vehicle_id,
                        "reasons": item.get("reasons") or [],
                    },
                )
                trace.append(
                    {
                        "tool": "create_sales_follow_up",
                        "args": {"case_id": item["id"]},
                        "result": result,
                    }
                )
                if not result.get("ok"):
                    return SalesAgentResult(
                        request_id=request_id,
                        ok=False,
                        intent="create_follow_ups",
                        message=result.get("error", "Failed to create follow-up"),
                        follow_ups_found=len(follow_ups),
                        cases_created=cases_created,
                        work_item_ids=work_ids,
                        task_ids=task_ids,
                        tool_trace=trace,
                    )
                data = result.get("data") or {}
                if data.get("case_id"):
                    cases_created.append(data["case_id"])
                if data.get("work_item_id"):
                    work_ids.append(data["work_item_id"])
                if data.get("task_id"):
                    task_ids.append(data["task_id"])

            lines = [
                f"Found {len(follow_ups)} stale case(s); created {len(cases_created)} follow-up(s)."
            ]
            for item in follow_ups:
                lines.append(
                    f"- {item.get('case_number')} · {item.get('days_open')}d · "
                    f"{', '.join(item.get('reasons') or [])}"
                )
            return SalesAgentResult(
                request_id=request_id,
                ok=True,
                intent="create_follow_ups",
                message="\n".join(lines),
                follow_ups_found=len(follow_ups),
                cases_created=cases_created,
                work_item_ids=work_ids,
                task_ids=task_ids,
                tool_trace=trace,
            )

        lines = [f"Found {len(follow_ups)} recommended sales follow-up(s) (not created):"]
        for item in follow_ups:
            lines.append(
                f"- {item.get('case_number')} score={item.get('score')} · "
                f"{', '.join(item.get('reasons') or [])}"
            )
        return SalesAgentResult(
            request_id=request_id,
            ok=True,
            intent="recommend",
            message="\n".join(lines),
            follow_ups_found=len(follow_ups),
            tool_trace=trace,
        )

    @staticmethod
    def _fail(
        request_id: str, result: dict[str, Any], trace: list[dict[str, Any]]
    ) -> SalesAgentResult:
        return SalesAgentResult(
            request_id=request_id,
            ok=False,
            intent="error",
            message=result.get("error", "Tool failed"),
            tool_trace=trace,
        )
