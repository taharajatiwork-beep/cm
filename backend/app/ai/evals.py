"""Offline checks for the rules planner. No network and no live model."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.communication_agent import RulesPlanner
from app.integrations.telegram.resolver import EntityResolver

# Persian sentences and the tool the rules planner must select.
RULES_CASES = [
    {"text": "یک کار برای پیگیری فروش Camry بساز", "intent": "create_work", "tool": "search_inventory"},
    {"text": "آگهی تبلیغ را به رضا بسپار", "intent": "create_work", "tool": "find_users"},
    {"text": "برای این موضوع پرونده باز کن", "intent": "create_case", "tool": "_compose_case"},
    {"text": "موجودی پژو ۲۰۷ را نشان بده", "intent": "message", "tool": "search_inventory"},
    {"text": "پیام‌های مربوط به تحویل خودرو را پیدا کن", "intent": "message", "tool": "search_messages"},
]


async def evaluate_rules(db: AsyncSession, organization_id: UUID) -> list[dict]:
    planner = RulesPlanner(EntityResolver(db))
    rows = []
    for case in RULES_CASES:
        intent, calls, _clarification = await planner.plan(organization_id, case["text"])
        names = [call.name for call in calls]
        rows.append(
            {
                "text": case["text"],
                "intent": intent,
                "tools": names,
                "ok": intent == case["intent"] and case["tool"] in names,
            }
        )
    return rows
