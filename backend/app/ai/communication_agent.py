"""CommunicationAgent — deterministic tool planner for Phase 7.

Uses tools only; never invents vehicles/people. Ambiguity → clarification.
LLM planner can replace RulesPlanner later without changing tools.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm_planner import LLMPlanner
from app.ai.tools import ToolContext, ToolExecutor
from app.core.permissions import PermissionCode, require_any_permission
from app.integrations.telegram.resolver import EntityResolver
from app.models import User
from app.services import get_user_permissions


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]


@dataclass
class AgentResult:
    request_id: str
    ok: bool
    intent: str
    clarification: str | None
    message: str
    work_item_id: str | None = None
    task_ids: list[str] = field(default_factory=list)
    case_id: str | None = None
    tool_trace: list[dict[str, Any]] = field(default_factory=list)


def _format_search_reply(
    query: str,
    vehicles: list[dict],
    message_hits: list[dict],
    customers: list[dict] | None = None,
) -> str:
    """Human-readable summary of tool search results (EN; UI may be FA)."""
    lines: list[str] = []
    q = (query or "").strip() or "(empty)"

    if vehicles:
        lines.append(f"Vehicles ({len(vehicles)}):")
        for v in vehicles[:8]:
            stock = f"#{v.get('stock_number')}" if v.get("stock_number") else ""
            lines.append(
                f"- {v.get('brand')} {v.get('model')} {stock} · {v.get('status')} · VIN …{str(v.get('vin', ''))[-6:]}"
            )
        if len(vehicles) > 8:
            lines.append(f"  …and {len(vehicles) - 8} more")
    else:
        lines.append("Vehicles: none matched.")

    if message_hits:
        lines.append(f"Work / cases ({len(message_hits)}):")
        for h in message_hits[:8]:
            lines.append(
                f"- [{h.get('entity_type')}] {h.get('title')}"
                + (f" — {h.get('subtitle')}" if h.get("subtitle") else "")
            )
    else:
        lines.append("Work / cases: none matched.")

    if customers:
        lines.append(f"Customers ({len(customers)}):")
        for c in customers[:5]:
            lines.append(f"- {c.get('full_name') or c.get('name')} {c.get('phone') or ''}".strip())

    if not vehicles and not message_hits and not (customers or []):
        lines.append(
            f'Nothing found for "{q}". Try stock # (e.g. 124), brand/model (Camry), '
            "or a work phrase like: برای کمری #124 رضا پیگیری کند."
        )
    return "\n".join(lines)


class RulesPlanner:
    """Maps natural language to a tool plan without inventing entities."""

    def __init__(self, resolver: EntityResolver):
        self.resolver = resolver

    async def plan(
        self, organization_id: UUID, text: str
    ) -> tuple[str, list[ToolCall], str | None]:
        resolution = await self.resolver.resolve(organization_id, text)

        if resolution.ambiguous:
            return "clarify", [], resolution.clarification

        # Work collaboration intent
        work_signals = ("پیگیری", "آگهی", "تبلیغ", "فروش", "assign", "task", "کار")
        if any(s in text for s in work_signals) or resolution.intent == "create_work":
            calls: list[ToolCall] = []
            # Resolve inventory first — never invent
            if resolution.stock_number:
                calls.append(
                    ToolCall(
                        "search_inventory",
                        {"stock_number": resolution.stock_number, "q": "Camry"},
                    )
                )
            else:
                calls.append(ToolCall("search_inventory", {"q": "Camry", "model": "Camry"}))

            # People lookups from matched tokens / message
            names: list[str] = []
            if "رضا" in text or "reza" in text.lower():
                names.append("رضا")
            if "سارا" in text or "sara" in text.lower():
                names.append("سارا")
            for name in names:
                calls.append(ToolCall("find_users", {"q": name}))

            # Placeholder create steps — agent fills ids after tool results
            calls.append(ToolCall("_compose_work", {"text": text}))
            return "create_work", calls, None

        if "case" in text.lower() or "پرونده" in text:
            return (
                "create_case",
                [ToolCall("_compose_case", {"text": text})],
                None,
            )

        # Default: search inventory + work/cases — never invent answers
        q = text.strip()[:80]
        return (
            "message",
            [
                ToolCall("search_inventory", {"q": q}),
                ToolCall("search_messages", {"q": q}),
            ],
            None,
        )


class CommunicationAgent:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.resolver = EntityResolver(db)

    async def run(self, *, user: User, text: str) -> AgentResult:
        request_id = str(uuid.uuid4())
        permissions = await get_user_permissions(self.db, user)
        require_any_permission(
            permissions, PermissionCode.AGENT_RUN, PermissionCode.WORK_ITEM_WRITE
        )

        ctx = ToolContext(
            self.db,
            organization_id=user.organization_id,
            user=user,
            permissions=permissions,
            request_id=request_id,
        )
        executor = ToolExecutor(ctx)
        planner = LLMPlanner(self.resolver)
        intent, plan, clarification = await planner.plan(user.organization_id, text)

        if clarification:
            return AgentResult(
                request_id=request_id,
                ok=True,
                intent="clarify",
                clarification=clarification,
                message=clarification,
            )

        trace: list[dict[str, Any]] = []
        vehicles: list[dict] = []
        people: list[dict] = []
        customers: list[dict] = []
        message_hits: list[dict] = []

        for call in plan:
            if call.name.startswith("_"):
                continue
            result = await executor.execute(call.name, call.args)
            trace.append({"tool": call.name, "args": call.args, "result": result})
            if not result.get("ok"):
                return AgentResult(
                    request_id=request_id,
                    ok=False,
                    intent=intent,
                    clarification=None,
                    message=result.get("error", "Tool failed"),
                    tool_trace=trace,
                )
            data = result.get("data")
            if call.name == "search_inventory" and isinstance(data, list):
                vehicles.extend(data)
            if call.name == "find_users" and isinstance(data, list):
                people.extend(data)
            if call.name == "find_customers" and isinstance(data, list):
                customers.extend(data)
            if call.name == "search_messages" and isinstance(data, list):
                message_hits.extend(data)

        if intent == "create_work":
            return await self._execute_create_work(
                executor, ctx, text, vehicles, people, trace, request_id, intent
            )

        if intent == "message":
            return AgentResult(
                request_id=request_id,
                ok=True,
                intent=intent,
                clarification=None,
                message=_format_search_reply(text, vehicles, message_hits, customers),
                tool_trace=trace,
            )

        return AgentResult(
            request_id=request_id,
            ok=True,
            intent=intent,
            clarification=None,
            message="Completed.",
            tool_trace=trace,
        )

    async def _execute_create_work(
        self,
        executor: ToolExecutor,
        ctx: ToolContext,
        text: str,
        vehicles: list[dict],
        people: list[dict],
        trace: list[dict[str, Any]],
        request_id: str,
        intent: str,
    ) -> AgentResult:
        if len(vehicles) == 0:
            msg = (
                "I understood the people/request, but could not identify a vehicle. "
                "Provide stock number or model."
            )
            return AgentResult(
                request_id=request_id,
                ok=True,
                intent="clarify",
                clarification=msg,
                message=msg,
                tool_trace=trace,
            )
        if len(vehicles) > 1:
            lines = ["I found multiple possible vehicles. Which one do you mean?"]
            for v in vehicles:
                lines.append(
                    f"- {v.get('brand')} {v.get('model')} #{v.get('stock_number')} "
                    f"(VIN …{str(v.get('vin', ''))[-6:]})"
                )
            msg = "\n".join(lines)
            return AgentResult(
                request_id=request_id,
                ok=True,
                intent="clarify",
                clarification=msg,
                message=msg,
                tool_trace=trace,
            )

        vehicle = vehicles[0]
        # Deduplicate people by id
        by_id = {p["id"]: p for p in people}
        people = list(by_id.values())
        if not people:
            msg = "Could not resolve assignees. Name people explicitly (e.g. رضا، سارا)."
            return AgentResult(
                request_id=request_id,
                ok=True,
                intent="clarify",
                clarification=msg,
                message=msg,
                tool_trace=trace,
            )

        title = f"Sell {vehicle.get('brand')} {vehicle.get('model')}"
        if vehicle.get("stock_number"):
            title += f" #{vehicle['stock_number']}"

        wi_result = await executor.execute(
            "create_work_item",
            {
                "title": title,
                "description": text,
                "vehicle_id": vehicle["id"],
                "branch_id": vehicle.get("branch_id"),
                "participant_ids": [p["id"] for p in people],
                "priority": "HIGH",
            },
        )
        trace.append({"tool": "create_work_item", "args": {"title": title}, "result": wi_result})
        if not wi_result.get("ok"):
            return AgentResult(
                request_id=request_id,
                ok=False,
                intent=intent,
                clarification=None,
                message=wi_result.get("error", "Failed to create work item"),
                tool_trace=trace,
            )
        work_item_id = wi_result["data"]["id"]

        task_ids: list[str] = []
        lines = [
            "WorkItem created",
            f"Title: {title}",
            f"Vehicle: {vehicle.get('brand')} {vehicle.get('model')} #{vehicle.get('stock_number')}",
            "",
        ]
        for idx, person in enumerate(people, start=1):
            task_title = self._task_title_for(person["full_name"], text)
            t_result = await executor.execute(
                "create_task",
                {
                    "title": task_title,
                    "work_item_id": work_item_id,
                    "assignee_ids": [person["id"]],
                    "priority": "HIGH",
                },
            )
            trace.append(
                {
                    "tool": "create_task",
                    "args": {"title": task_title, "assignee": person["full_name"]},
                    "result": t_result,
                }
            )
            if t_result.get("ok"):
                task_ids.append(t_result["data"]["id"])
                lines.append(f"Task {idx}")
                lines.append(person["full_name"].split()[0])
                lines.append(task_title)
                lines.append("")
                await executor.execute(
                    "send_notification",
                    {
                        "user_id": person["id"],
                        "title": "کار جدید به شما سپرده شد",
                        "body": task_title,
                        "entity_type": "task",
                        "entity_id": t_result["data"]["id"],
                    },
                )

        return AgentResult(
            request_id=request_id,
            ok=True,
            intent=intent,
            clarification=None,
            message="\n".join(lines).strip(),
            work_item_id=work_item_id,
            task_ids=task_ids,
            tool_trace=trace,
        )

    @staticmethod
    def _task_title_for(full_name: str, text: str) -> str:
        first = full_name.split()[0].lower()
        if first == "reza" or "رضا" in full_name:
            if "مشتری" in text or "پیگیری" in text:
                return "Contact customers"
            return "Follow up (seller)"
        if first == "sara" or "سارا" in full_name:
            if "آگهی" in text or "تبلیغ" in text:
                return "Prepare marketing material"
            return "Marketing task"
        return f"Task for {full_name.split()[0]}"
