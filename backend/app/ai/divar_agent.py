"""DivarAgent — prepare assisted listings from inventory via Divar pilot tools."""

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
class DivarAgentResult:
    request_id: str
    ok: bool
    intent: str
    message: str
    clarification: str | None = None
    listings_prepared: int = 0
    listing_ids: list[str] = field(default_factory=list)
    work_item_ids: list[str] = field(default_factory=list)
    tool_trace: list[dict[str, Any]] = field(default_factory=list)


class DivarAgent:
    """Orchestrates Divar assisted listing. Never auto-submits ads."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run(
        self,
        *,
        user: User,
        message: str | None = None,
        vehicle_id: str | None = None,
        auto_create: bool | None = None,
        limit: int = 5,
    ) -> DivarAgentResult:
        request_id = str(uuid.uuid4())
        permissions = await get_user_permissions(self.db, user)
        require_any_permission(
            permissions, PermissionCode.AGENT_RUN, PermissionCode.CAMPAIGN_WRITE
        )

        settings = get_settings()
        should_create = (
            auto_create if auto_create is not None else settings.divar_auto_prepare
        )

        text = (message or "").lower()
        list_only = any(s in text for s in ("list", "لیست", "pipeline", "گزارش", "candidates"))
        scan_only = any(s in text for s in ("scan", "فقط", "report"))
        if "create" in text or "بساز" in text or "آگهی" in text or "prepare" in text:
            should_create = True
        if (list_only or scan_only) and not any(
            s in text for s in ("create", "بساز", "آگهی", "prepare")
        ):
            should_create = False
        if auto_create is not None:
            should_create = auto_create

        ctx = ToolContext(
            self.db,
            organization_id=user.organization_id,
            user=user,
            permissions=permissions,
            request_id=request_id,
            agent="DivarAgent",
            model="rules-v1",
            prompt_version="divar-1",
        )
        executor = ToolExecutor(ctx)
        trace: list[dict[str, Any]] = []

        if list_only and not vehicle_id:
            candidates = await executor.execute("list_divar_candidates", {})
            trace.append({"tool": "list_divar_candidates", "args": {}, "result": candidates})
            if not candidates.get("ok"):
                return self._fail(request_id, candidates, trace)
            rows = (candidates.get("data") or {}).get("candidates") or []
            lines = [f"Divar candidates (IN_STOCK, not yet listed): {len(rows)}"]
            for c in rows[:20]:
                lines.append(
                    f"- {c.get('brand')} {c.get('model')} #{c.get('stock_number')} "
                    f"id={c.get('id')}"
                )
            existing = await executor.execute("list_divar_listings", {})
            trace.append({"tool": "list_divar_listings", "args": {}, "result": existing})
            return DivarAgentResult(
                request_id=request_id,
                ok=True,
                intent="candidates",
                message="\n".join(lines),
                tool_trace=trace,
            )

        # Single vehicle or batch prepare
        vehicle_ids: list[str] = []
        if vehicle_id:
            vehicle_ids = [vehicle_id]
        else:
            candidates = await executor.execute("list_divar_candidates", {})
            trace.append({"tool": "list_divar_candidates", "args": {}, "result": candidates})
            if not candidates.get("ok"):
                return self._fail(request_id, candidates, trace)
            rows = (candidates.get("data") or {}).get("candidates") or []
            if not rows:
                return DivarAgentResult(
                    request_id=request_id,
                    ok=True,
                    intent="scan",
                    message="No IN_STOCK vehicles pending Divar listing.",
                    tool_trace=trace,
                )
            vehicle_ids = [r["id"] for r in rows[:limit]]

        if not should_create:
            lines = [
                f"Would prepare {len(vehicle_ids)} Divar listing(s) (not created — human submit still required):"
            ]
            for vid in vehicle_ids:
                lines.append(f"- vehicle={vid}")
            return DivarAgentResult(
                request_id=request_id,
                ok=True,
                intent="recommend",
                message="\n".join(lines),
                listings_prepared=0,
                tool_trace=trace,
            )

        listing_ids: list[str] = []
        work_ids: list[str] = []
        for vid in vehicle_ids:
            result = await executor.execute(
                "prepare_divar_listing",
                {"vehicle_id": vid, "create_task": True},
            )
            trace.append(
                {
                    "tool": "prepare_divar_listing",
                    "args": {"vehicle_id": vid},
                    "result": result,
                }
            )
            if not result.get("ok"):
                return DivarAgentResult(
                    request_id=request_id,
                    ok=False,
                    intent="prepare",
                    message=result.get("error", "Prepare failed"),
                    listings_prepared=len(listing_ids),
                    listing_ids=listing_ids,
                    work_item_ids=work_ids,
                    tool_trace=trace,
                )
            data = result.get("data") or {}
            if data.get("listing_id"):
                listing_ids.append(data["listing_id"])
            if data.get("work_item_id"):
                work_ids.append(data["work_item_id"])

        lines = [
            f"Prepared {len(listing_ids)} Divar listing(s). Final submit is human-only."
        ]
        for lid in listing_ids:
            lines.append(f"- listing={lid}")
        return DivarAgentResult(
            request_id=request_id,
            ok=True,
            intent="prepare",
            message="\n".join(lines),
            listings_prepared=len(listing_ids),
            listing_ids=listing_ids,
            work_item_ids=work_ids,
            tool_trace=trace,
        )

    @staticmethod
    def _fail(
        request_id: str, result: dict[str, Any], trace: list[dict[str, Any]]
    ) -> DivarAgentResult:
        return DivarAgentResult(
            request_id=request_id,
            ok=False,
            intent="error",
            message=result.get("error", "Tool failed"),
            tool_trace=trace,
        )
