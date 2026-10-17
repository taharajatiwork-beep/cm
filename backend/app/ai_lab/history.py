"""Prior AI Lab results for Grok context (no PII)."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_lab.models import AiRecFollowup, AiTask
from app.ai_lab.workspaces import is_private_kind

HISTORY_MAX_BYTES = 4096


async def build_history(
    db: AsyncSession,
    organization_id: UUID,
    kind: str,
    scope: dict,
    viewer_id: UUID | None = None,
) -> list[dict]:
    """Last 3 done tasks of same kind (campaign scoped when applicable)."""
    q = (
        select(AiTask)
        .where(
            AiTask.organization_id == organization_id,
            AiTask.kind == kind,
            AiTask.status == "done",
        )
        .order_by(AiTask.completed_at.desc())
        .limit(20)
    )
    if is_private_kind(kind) and viewer_id is not None:
        q = q.where(AiTask.created_by == viewer_id)
    rows = list((await db.scalars(q)).all())
    if kind == "campaign_review":
        camp_id = scope.get("campaign_id")
        if camp_id:
            filtered = []
            for row in rows:
                try:
                    inp = json.loads(row.input_json or "{}")
                except json.JSONDecodeError:
                    continue
                if str(inp.get("campaign_id")) == str(camp_id):
                    filtered.append(row)
            rows = filtered
    rows = rows[:3]
    out: list[dict] = []
    for row in rows:
        try:
            result = json.loads(row.result_json or "{}")
        except json.JSONDecodeError:
            continue
        try:
            decisions = json.loads(row.decisions_json or "{}")
        except json.JSONDecodeError:
            decisions = {}
        recs = result.get("recommendations") or []
        decided = []
        for rec in recs:
            rid = rec.get("id")
            if not rid or rid not in decisions:
                continue
            decided.append(
                {
                    "id": rid,
                    "action": (rec.get("action") or "")[:200],
                    "decision": decisions[rid],
                }
            )
        followups = list(
            (
                await db.scalars(select(AiRecFollowup).where(AiRecFollowup.ai_task_id == row.id))
            ).all()
        )
        measured = []
        for fu in followups:
            if not fu.followup_json:
                continue
            try:
                measured.append(
                    {
                        "rec_id": fu.rec_id,
                        "baseline": json.loads(fu.baseline_json or "{}"),
                        "followup": json.loads(fu.followup_json),
                    }
                )
            except json.JSONDecodeError:
                continue
        out.append(
            {
                "task_id": str(row.id),
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "summary": (result.get("summary") or "")[:500],
                "decisions": decided,
                "outcomes": measured,
            }
        )
    return _trim_history(out)


def _trim_history(items: list[dict]) -> list[dict]:
    blob = json.dumps(items, ensure_ascii=False)
    if len(blob.encode("utf-8")) <= HISTORY_MAX_BYTES:
        return items
    trimmed: list[dict] = []
    for item in items:
        trimmed.append(item)
        if len(json.dumps(trimmed, ensure_ascii=False).encode("utf-8")) > HISTORY_MAX_BYTES:
            trimmed.pop()
            break
    return trimmed
