"""LLM-backed tool planner with RulesPlanner fallback.

Never invents entity IDs — only proposes search/find tools + compose markers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.ai.llm import LLMClient, get_llm_client
from app.ai.tools import TOOL_SPECS
from app.core.logging import get_logger
from app.integrations.telegram.resolver import EntityResolver

log = get_logger(__name__)


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]


ALLOWED_PLAN_TOOLS = {
    "search_inventory",
    "get_vehicle",
    "find_users",
    "find_team",
    "find_branch",
    "find_customers",
    "search_messages",
    "get_case",
    "get_pending_tasks",
    "recommend_assignees",
    "_compose_work",
    "_compose_case",
}


SYSTEM_PROMPT = """You are a planner for an automotive dealership operations platform.
Output ONLY a JSON object with this shape:
{
  "intent": "create_work" | "create_case" | "message" | "clarify",
  "clarification": null or string asking the user a question,
  "tools": [{"name": string, "args": object}]
}

Rules:
- Never invent vehicle IDs, user IDs, or customer IDs.
- To find vehicles use search_inventory with q / stock_number / brand / model.
- To find people use find_users with q = name fragment (Persian or Latin).
- To find customers use find_customers with q = name or phone.
- For multi-person work collaboration (پیگیری / تبلیغ / فروش / assign tasks) use intent create_work
  and end tools with {"name":"_compose_work","args":{"text":"<original user message>"}}.
- If ambiguous who/which vehicle, intent=clarify and set clarification; tools=[].
- Allowed tool names: """ + ", ".join(sorted(ALLOWED_PLAN_TOOLS))


class LLMPlanner:
    def __init__(self, resolver: EntityResolver, client: LLMClient | None = None):
        self.resolver = resolver
        self.client = client if client is not None else get_llm_client()

    async def plan(
        self, organization_id: UUID, text: str
    ) -> tuple[str, list[ToolCall], str | None]:
        from app.ai.communication_agent import RulesPlanner

        resolution = await self.resolver.resolve(organization_id, text)
        if resolution.ambiguous:
            return "clarify", [], resolution.clarification

        if self.client is None:
            intent, calls, clarification = await RulesPlanner(self.resolver).plan(
                organization_id, text
            )
            return intent, [ToolCall(c.name, c.args) for c in calls], clarification

        try:
            raw = await self.client.chat_json(system=SYSTEM_PROMPT, user=text)
            intent, calls, clarification = _normalize_plan(raw, text)
            if clarification:
                return "clarify", [], clarification
            if not calls and intent == "create_work":
                log.warning("llm_plan_incomplete_fallback")
                intent, calls, clarification = await RulesPlanner(self.resolver).plan(
                    organization_id, text
                )
                return intent, [ToolCall(c.name, c.args) for c in calls], clarification
            return intent, calls, None
        except Exception as exc:  # noqa: BLE001
            log.warning("llm_plan_failed_fallback", error=str(exc))
            intent, calls, clarification = await RulesPlanner(self.resolver).plan(
                organization_id, text
            )
            return intent, [ToolCall(c.name, c.args) for c in calls], clarification


def _normalize_plan(
    raw: dict[str, Any], original_text: str
) -> tuple[str, list[ToolCall], str | None]:
    intent = str(raw.get("intent") or "message")
    clarification = raw.get("clarification")
    if clarification:
        return "clarify", [], str(clarification)

    tools_raw = raw.get("tools") or []
    if isinstance(tools_raw, str):
        tools_raw = json.loads(tools_raw)

    calls: list[ToolCall] = []
    for item in tools_raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if name not in ALLOWED_PLAN_TOOLS:
            continue
        if name in TOOL_SPECS or name.startswith("_"):
            args = item.get("args") or {}
            if not isinstance(args, dict):
                args = {}
            if name in ("search_inventory", "find_users", "find_customers", "search_messages"):
                for bad in ("id", "user_id", "vehicle_id", "customer_id"):
                    args.pop(bad, None)
            if name == "_compose_work" and not args.get("text"):
                args["text"] = original_text
            calls.append(ToolCall(name=name, args=args))

    return intent, calls, None
