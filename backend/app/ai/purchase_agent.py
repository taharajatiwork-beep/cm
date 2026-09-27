"""PurchaseAgent — unmet demand + stale seller offers via tools only."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools import ToolContext, ToolExecutor
from app.core.config import get_settings
from app.core.permissions import PermissionCode, require_permission
from app.models import User
from app.services import get_user_permissions


@dataclass
class PurchaseAgentResult:
    request_id: str
    ok: bool
    intent: str
    message: str
    clarification: str | None = None
    opportunities_found: int = 0
    cases_created: list[str] = field(default_factory=list)
    work_item_ids: list[str] = field(default_factory=list)
    task_ids: list[str] = field(default_factory=list)
    tool_trace: list[dict[str, Any]] = field(default_factory=list)


class PurchaseAgent:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def run(
        self,
        *,
        user: User,
        message: str | None = None,
        stale_days: int | None = None,
        auto_create: bool | None = None,
    ) -> PurchaseAgentResult:
        request_id = str(uuid.uuid4())
        permissions = await get_user_permissions(self.db, user)
        require_permission(permissions, PermissionCode.AGENT_RUN)

        settings = get_settings()
        days = stale_days if stale_days is not None else settings.purchase_stale_days
        should_create = (
            auto_create
            if auto_create is not None
            else settings.purchase_auto_create_opportunity
        )

        text = (message or "").lower()
        pipeline_only = any(s in text for s in ("pipeline", "لیست", "list", "گزارش"))
        scan_only = any(s in text for s in ("scan", "فقط", "report"))
        if "create" in text or "بساز" in text or "خرید" in text or "purchase" in text:
            should_create = True
        if (pipeline_only or scan_only) and not any(
            s in text for s in ("create", "بساز", "خرید", "purchase")
        ):
            # "scan purchase" still contains purchase — only force create off for pure scan/list
            if scan_only or pipeline_only:
                should_create = False
        if auto_create is not None:
            should_create = auto_create

        ctx = ToolContext(
            self.db,
            organization_id=user.organization_id,
            user=user,
            permissions=permissions,
            request_id=request_id,
            agent="PurchaseAgent",
            model="rules-v1",
            prompt_version="purchase-1",
        )
        executor = ToolExecutor(ctx)
        trace: list[dict[str, Any]] = []

        if pipeline_only:
            pipe = await executor.execute("list_purchase_pipeline", {})
            trace.append({"tool": "list_purchase_pipeline", "args": {}, "result": pipe})
            if not pipe.get("ok"):
                return self._fail(request_id, pipe, trace)
            cases = (pipe.get("data") or {}).get("cases") or []
            lines = [f"Purchase pipeline: {len(cases)} open seller offer(s)."]
            for c in cases[:15]:
                lines.append(
                    f"- {c.get('case_number')} {c.get('subject')} · {c.get('days_open')}d"
                )
            return PurchaseAgentResult(
                request_id=request_id,
                ok=True,
                intent="pipeline",
                message="\n".join(lines),
                tool_trace=trace,
            )

        detected = await executor.execute(
            "detect_purchase_opportunities", {"stale_days": days}
        )
        trace.append(
            {
                "tool": "detect_purchase_opportunities",
                "args": {"stale_days": days},
                "result": detected,
            }
        )
        if not detected.get("ok"):
            return self._fail(request_id, detected, trace)

        opps: list[dict[str, Any]] = (detected.get("data") or {}).get("opportunities") or []
        if not opps:
            return PurchaseAgentResult(
                request_id=request_id,
                ok=True,
                intent="scan",
                message="No purchase opportunities (unmet demand or stale seller offers).",
                opportunities_found=0,
                tool_trace=trace,
            )

        cases_created: list[str] = []
        work_ids: list[str] = []
        task_ids: list[str] = []

        if should_create:
            for opp in opps:
                args: dict[str, Any] = {
                    "kind": opp.get("kind"),
                    "brand": opp.get("brand"),
                    "model": opp.get("model"),
                    "label": opp.get("label"),
                    "reasons": opp.get("reasons") or [],
                }
                if opp.get("kind") == "stale_seller_offer":
                    args["source_case_id"] = opp.get("id")
                result = await executor.execute("create_purchase_opportunity", args)
                trace.append(
                    {
                        "tool": "create_purchase_opportunity",
                        "args": args,
                        "result": result,
                    }
                )
                if not result.get("ok"):
                    return PurchaseAgentResult(
                        request_id=request_id,
                        ok=False,
                        intent="create_opportunities",
                        message=result.get("error", "Failed to create purchase opportunity"),
                        opportunities_found=len(opps),
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
                f"Found {len(opps)} opportunity(ies); created {len(cases_created)} case(s)."
            ]
            for opp in opps:
                lines.append(
                    f"- [{opp.get('kind')}] {opp.get('label')} · "
                    f"{', '.join(opp.get('reasons') or [])}"
                )
            return PurchaseAgentResult(
                request_id=request_id,
                ok=True,
                intent="create_opportunities",
                message="\n".join(lines),
                opportunities_found=len(opps),
                cases_created=cases_created,
                work_item_ids=work_ids,
                task_ids=task_ids,
                tool_trace=trace,
            )

        lines = [f"Found {len(opps)} recommended purchase opportunity(ies) (not created):"]
        for opp in opps:
            lines.append(
                f"- [{opp.get('kind')}] {opp.get('label')} score={opp.get('score')} · "
                f"{', '.join(opp.get('reasons') or [])}"
            )
        return PurchaseAgentResult(
            request_id=request_id,
            ok=True,
            intent="recommend",
            message="\n".join(lines),
            opportunities_found=len(opps),
            tool_trace=trace,
        )

    @staticmethod
    def _fail(
        request_id: str, result: dict[str, Any], trace: list[dict[str, Any]]
    ) -> PurchaseAgentResult:
        return PurchaseAgentResult(
            request_id=request_id,
            ok=False,
            intent="error",
            message=result.get("error", "Tool failed"),
            tool_trace=trace,
        )
