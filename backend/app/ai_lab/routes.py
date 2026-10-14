"""AI Lab API — marketing analysis tasks for Grok Bot."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_lab.models import AiTask
from app.ai_lab.schemas import (
    BotCallbackIn,
    BotResultBody,
    EvaluationIn,
    ManualResultIn,
    RecommendationDecisionIn,
    SnapshotIn,
    TaskCreateIn,
)
from app.ai_lab.service import apply_bot_payload, poll_github_for_task, send_outbound_webhook
from app.ai_lab.signing import verify
from app.ai_lab.snapshots import build_snapshot
from app.api.deps import AuthContext, get_current_user, handle_authz
from app.core.config import get_settings
from app.core.permissions import AuthorizationError, PermissionCode, require_any_permission
from app.db.session import get_db

router = APIRouter(prefix="/ai-lab", tags=["ai-lab"])

MAX_RESULT_BYTES = 256 * 1024
_PHONE_RE = re.compile(r"09\d{9}")


def _settings_ok() -> None:
    if not get_settings().ai_lab_enabled:
        raise HTTPException(status_code=404, detail="AI Lab is disabled")


def _require_perf(auth: AuthContext = Depends(get_current_user)) -> AuthContext:
    _settings_ok()
    try:
        require_any_permission(
            auth.permissions,
            PermissionCode.PERF_READ,
            PermissionCode.PERF_WRITE,
            PermissionCode.PERF_APPROVE,
            PermissionCode.ORG_ADMIN,
        )
    except AuthorizationError as exc:
        raise handle_authz(exc) from exc
    return auth


def _task_out(row: AiTask) -> dict:
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
        "input": json.loads(row.input_json or "{}"),
        "snapshot": json.loads(row.snapshot_json or "{}"),
        "status": row.status,
        "result": result,
        "error": row.error,
        "rating": row.rating,
        "useful": row.useful,
        "eval_note": row.eval_note,
        "decisions": decisions,
        "accepted_count": accepted,
        "latency_seconds": latency,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "last_polled_at": row.last_polled_at.isoformat() if row.last_polled_at else None,
    }


async def _expire_if_needed(db: AsyncSession, row: AiTask) -> None:
    settings = get_settings()
    if row.status not in ("pending", "sent", "waiting"):
        return
    ttl = timedelta(hours=settings.ai_lab_task_ttl_hours)
    if row.created_at and datetime.now(UTC) - row.created_at.replace(tzinfo=UTC) > ttl:
        row.status = "expired"
        row.error = "Task expired"
        await db.flush()


@router.get("/config")
async def lab_config(auth: AuthContext = Depends(get_current_user)) -> dict:
    try:
        require_any_permission(
            auth.permissions,
            PermissionCode.PERF_READ,
            PermissionCode.PERF_WRITE,
            PermissionCode.PERF_APPROVE,
            PermissionCode.ORG_ADMIN,
        )
    except AuthorizationError as exc:
        raise handle_authz(exc) from exc
    settings = get_settings()
    return {
        "enabled": settings.ai_lab_enabled,
        "mode": settings.ai_lab_mode,
        "result_source": settings.ai_lab_result_source,
    }


@router.get("/evaluation-summary")
async def evaluation_summary(
    auth: AuthContext = Depends(_require_perf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = list(
        (
            await db.scalars(
                select(AiTask).where(
                    AiTask.organization_id == auth.organization_id,
                    AiTask.status == "done",
                )
            )
        ).all()
    )
    by_kind: dict[str, dict] = {}
    for row in rows:
        bucket = by_kind.setdefault(row.kind, {"count": 0, "ratings": [], "accepted": 0, "total_recs": 0, "latencies": []})
        bucket["count"] += 1
        if row.rating is not None:
            bucket["ratings"].append(row.rating)
        try:
            result = json.loads(row.result_json or "{}")
            recs = result.get("recommendations") or []
            bucket["total_recs"] += len(recs)
        except json.JSONDecodeError:
            recs = []
        try:
            decisions = json.loads(row.decisions_json or "{}")
        except json.JSONDecodeError:
            decisions = {}
        bucket["accepted"] += sum(1 for v in decisions.values() if v == "accepted")
        if row.completed_at and row.created_at:
            bucket["latencies"].append(int((row.completed_at - row.created_at).total_seconds()))
    summary = {}
    for kind, data in by_kind.items():
        ratings = data["ratings"]
        latencies = sorted(data["latencies"])
        median_latency = latencies[len(latencies) // 2] if latencies else None
        summary[kind] = {
            "tasks": data["count"],
            "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "accept_rate": round(data["accepted"] / data["total_recs"], 2) if data["total_recs"] else None,
            "median_latency_seconds": median_latency,
        }
    return {"by_kind": summary}


@router.post("/snapshot")
async def preview_snapshot(
    body: SnapshotIn,
    auth: AuthContext = Depends(_require_perf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    snap = await build_snapshot(db, auth.organization_id, body.kind, body.input)
    blob = json.dumps(snap, ensure_ascii=False)
    if _PHONE_RE.search(blob):
        raise HTTPException(status_code=500, detail="Snapshot failed PII guard")
    return snap


@router.post("/tasks")
async def create_task(
    body: TaskCreateIn,
    auth: AuthContext = Depends(_require_perf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    snap = await build_snapshot(db, auth.organization_id, body.kind, body.input)
    blob = json.dumps(snap, ensure_ascii=False)
    if _PHONE_RE.search(blob):
        raise HTTPException(status_code=500, detail="Snapshot failed PII guard")
    row = AiTask(
        organization_id=auth.organization_id,
        created_by=auth.user.id,
        kind=body.kind,
        input_json=json.dumps(body.input, ensure_ascii=False),
        snapshot_json=blob,
        status="pending",
    )
    db.add(row)
    await db.flush()
    settings = get_settings()
    if settings.ai_lab_mode == "webhook":
        await send_outbound_webhook(row)
    await db.flush()
    return _task_out(row)


@router.get("/tasks")
async def list_tasks(
    auth: AuthContext = Depends(_require_perf),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = list(
        (
            await db.scalars(
                select(AiTask)
                .where(AiTask.organization_id == auth.organization_id)
                .order_by(AiTask.created_at.desc())
                .limit(100)
            )
        ).all()
    )
    for row in rows:
        await _expire_if_needed(db, row)
    return [_task_out(r) for r in rows]


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: UUID,
    auth: AuthContext = Depends(_require_perf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.get(AiTask, task_id)
    if not row or row.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="Task not found")
    await _expire_if_needed(db, row)
    return _task_out(row)


@router.post("/tasks/{task_id}/manual-result")
async def manual_result(
    task_id: UUID,
    body: ManualResultIn,
    auth: AuthContext = Depends(_require_perf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.get(AiTask, task_id)
    if not row or row.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="Task not found")
    if row.status == "done":
        return _task_out(row)
    payload = body.payload
    if "task_id" not in payload:
        payload = {"task_id": str(task_id), **payload}
    apply_bot_payload(row, payload)
    await db.flush()
    return _task_out(row)


@router.post("/tasks/{task_id}/poll")
async def poll_task_now(
    task_id: UUID,
    auth: AuthContext = Depends(_require_perf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    if settings.ai_lab_result_source != "github":
        raise HTTPException(status_code=400, detail="GitHub polling is not enabled")
    row = await db.get(AiTask, task_id)
    if not row or row.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="Task not found")
    if row.status not in ("waiting", "sent"):
        return _task_out(row)
    await poll_github_for_task(db, row)
    await db.flush()
    return _task_out(row)


@router.patch("/tasks/{task_id}/recommendations/{rec_id}")
async def recommendation_decision(
    task_id: UUID,
    rec_id: str,
    body: RecommendationDecisionIn,
    auth: AuthContext = Depends(_require_perf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.get(AiTask, task_id)
    if not row or row.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        decisions = json.loads(row.decisions_json or "{}")
    except json.JSONDecodeError:
        decisions = {}
    decisions[rec_id] = body.decision
    row.decisions_json = json.dumps(decisions, ensure_ascii=False)
    await db.flush()
    return _task_out(row)


@router.patch("/tasks/{task_id}/evaluation")
async def evaluate_task(
    task_id: UUID,
    body: EvaluationIn,
    auth: AuthContext = Depends(_require_perf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.get(AiTask, task_id)
    if not row or row.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="Task not found")
    row.rating = body.rating
    row.useful = body.useful
    row.eval_note = body.eval_note
    await db.flush()
    return _task_out(row)


@router.post("/results")
async def inbound_results(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    _settings_ok()
    settings = get_settings()
    raw = await request.body()
    if len(raw) > MAX_RESULT_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")
    ts = request.headers.get("X-Grok-Timestamp", "")
    sig = request.headers.get("X-Grok-Signature", "")
    if not verify(settings.ai_lab_inbound_secret, ts, sig, raw):
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON") from None
    try:
        parsed = BotCallbackIn.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = await db.get(AiTask, parsed.task_id)
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    if row.status == "done" and row.result_json:
        return {"ok": True, "idempotent": True}
    apply_bot_payload(row, payload)
    await db.flush()
    return {"ok": True}
