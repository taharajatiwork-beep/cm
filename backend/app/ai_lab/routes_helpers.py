"""Shared route helpers for AI Lab."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_lab.models import AiRecFollowup, AiTask


async def followups_for_task(db: AsyncSession, task_id: UUID) -> dict[str, dict]:
    rows = list((await db.scalars(select(AiRecFollowup).where(AiRecFollowup.ai_task_id == task_id))).all())
    out: dict[str, dict] = {}
    for row in rows:
        try:
            baseline = json.loads(row.baseline_json or "{}")
        except json.JSONDecodeError:
            baseline = {}
        try:
            followup = json.loads(row.followup_json or "{}") if row.followup_json else None
        except json.JSONDecodeError:
            followup = None
        out[row.rec_id] = {
            "cm_task_id": str(row.cm_task_id) if row.cm_task_id else None,
            "baseline": baseline,
            "followup": followup,
            "followup_due_on": row.followup_due_on.isoformat(),
            "measured_at": row.measured_at.isoformat() if row.measured_at else None,
        }
    return out


def task_out(row: AiTask, followups: dict[str, dict] | None = None) -> dict:
    latency = None
    if row.completed_at and row.created_at:
        latency = int((row.completed_at - row.created_at).total_seconds())
    try:
        result = json.loads(row.result_json) if row.result_json else None
    except json.JSONDecodeError:
        result = None
    try:
        decisions = json.loads(row.decisions_json or "{}")
    except json.JSONDecodeError:
        decisions = {}
    accepted = sum(1 for v in decisions.values() if v == "accepted")
    return {
        "id": str(row.id),
        "kind": row.kind,
        "trigger": getattr(row, "trigger", "manual") or "manual",
        "input": json.loads(row.input_json or "{}"),
        "snapshot": json.loads(row.snapshot_json or "{}"),
        "status": row.status,
        "result": result,
        "error": row.error,
        "rating": row.rating,
        "useful": row.useful,
        "eval_note": row.eval_note,
        "decisions": decisions,
        "followups": followups or {},
        "accepted_count": accepted,
        "latency_seconds": latency,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "last_polled_at": row.last_polled_at.isoformat() if row.last_polled_at else None,
    }
