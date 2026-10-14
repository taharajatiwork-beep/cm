"""AI Lab API — marketing analysis tasks for Grok Bot."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_lab.followup import ensure_followup_on_accept
from app.ai_lab.models import AiRecFollowup, AiTask
from app.ai_lab.routes_helpers import followups_for_task, task_out as _task_out
from app.ai_lab.schemas import (
    BotCallbackIn,
    EvaluationIn,
    ManualResultIn,
    RecToTaskIn,
    RecommendationDecisionIn,
    SnapshotIn,
    TaskCreateIn,
)
from app.ai_lab.service import (
    apply_bot_payload,
    create_ai_task,
    notify_task_done,
    poll_github_for_task,
)
from app.models.enums import Priority
from app.services.work import WorkService
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


async def _task_response(db: AsyncSession, row: AiTask) -> dict:
    fu = await followups_for_task(db, row.id)
    return _task_out(row, fu)


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
    followup_rows = list(
        (
            await db.scalars(
                select(AiRecFollowup).join(AiTask, AiRecFollowup.ai_task_id == AiTask.id).where(
                    AiTask.organization_id == auth.organization_id
                )
            )
        ).all()
    )
    cpl_deltas: list[float] = []
    for fu in followup_rows:
        if not fu.followup_json:
            continue
        try:
            b = json.loads(fu.baseline_json or "{}")
            f = json.loads(fu.followup_json or "{}")
            bc, fc = b.get("cpl"), f.get("cpl")
            if bc and fc and bc > 0:
                cpl_deltas.append((fc - bc) / bc * 100)
        except json.JSONDecodeError:
            continue
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
    return {
        "by_kind": summary,
        "avg_accepted_cpl_change_pct": round(sum(cpl_deltas) / len(cpl_deltas), 1) if cpl_deltas else None,
    }


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
    blob_preview = json.dumps(
        await build_snapshot(db, auth.organization_id, body.kind, body.input),
        ensure_ascii=False,
    )
    if _PHONE_RE.search(blob_preview):
        raise HTTPException(status_code=500, detail="Snapshot failed PII guard")
    row = await create_ai_task(
        db,
        organization_id=auth.organization_id,
        user_id=auth.user.id,
        kind=body.kind,
        input_data=body.input,
        trigger="manual",
    )
    return await _task_response(db, row)


@router.get("/tasks")
async def list_tasks(
    auth: AuthContext = Depends(_require_perf),
    db: AsyncSession = Depends(get_db),
    kind: str | None = Query(None),
    trigger: str | None = Query(None),
) -> list[dict]:
    q = select(AiTask).where(AiTask.organization_id == auth.organization_id)
    if kind:
        q = q.where(AiTask.kind == kind)
    if trigger:
        q = q.where(AiTask.trigger == trigger)
    rows = list((await db.scalars(q.order_by(AiTask.created_at.desc()).limit(100))).all())
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
    return await _task_response(db, row)


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
        return await _task_response(db, row)
    payload = body.payload
    if "task_id" not in payload:
        payload = {"task_id": str(task_id), **payload}
    apply_bot_payload(row, payload)
    await db.flush()
    return await _task_response(db, row)


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
        return await _task_response(db, row)
    await poll_github_for_task(db, row)
    await db.flush()
    return await _task_response(db, row)


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
    if body.decision == "accepted":
        settings = get_settings()
        await ensure_followup_on_accept(db, row, rec_id, followup_days=settings.ai_lab_followup_days)
    await db.flush()
    return await _task_response(db, row)


@router.post("/tasks/{task_id}/recommendations/{rec_id}/to-task")
async def recommendation_to_task(
    task_id: UUID,
    rec_id: str,
    body: RecToTaskIn,
    auth: AuthContext = Depends(_require_perf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        require_any_permission(auth.permissions, PermissionCode.TASK_WRITE, PermissionCode.ORG_ADMIN)
    except AuthorizationError as exc:
        raise handle_authz(exc) from exc
    row = await db.get(AiTask, task_id)
    if not row or row.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        result = json.loads(row.result_json or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="No result on task")
    rec = next((r for r in (result.get("recommendations") or []) if r.get("id") == rec_id), None)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    existing_fu = await db.scalar(
        select(AiRecFollowup).where(AiRecFollowup.ai_task_id == row.id, AiRecFollowup.rec_id == rec_id)
    )
    if existing_fu and existing_fu.cm_task_id:
        try:
            decisions = json.loads(row.decisions_json or "{}")
        except json.JSONDecodeError:
            decisions = {}
        decisions[rec_id] = "accepted"
        row.decisions_json = json.dumps(decisions, ensure_ascii=False)
        await db.flush()
        out = await _task_response(db, row)
        out["cm_task_id"] = str(existing_fu.cm_task_id)
        return out
    prio_map = {"low": Priority.LOW, "medium": Priority.MEDIUM, "high": Priority.HIGH, "critical": Priority.URGENT}
    owner = body.owner_id or auth.user.id
    deadline_dt = None
    if body.deadline:
        try:
            deadline_dt = datetime.combine(date.fromisoformat(body.deadline), datetime.min.time(), tzinfo=UTC)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid deadline") from None
    desc = f"{rec.get('reason', '')}\n\nاثر: {rec.get('expected_impact', '')}\n\nAI Lab: /ai-lab"
    svc = WorkService(db)
    cm_task = await svc.create_task(
        organization_id=auth.organization_id,
        title=(rec.get("action") or "AI recommendation")[:255],
        owner_id=owner,
        description=desc,
        priority=prio_map.get(body.priority, Priority.MEDIUM),
        deadline=deadline_dt,
        actor_permissions=auth.permissions,
    )
    try:
        decisions = json.loads(row.decisions_json or "{}")
    except json.JSONDecodeError:
        decisions = {}
    decisions[rec_id] = "accepted"
    row.decisions_json = json.dumps(decisions, ensure_ascii=False)
    settings = get_settings()
    await ensure_followup_on_accept(
        db, row, rec_id, cm_task_id=cm_task.id, followup_days=settings.ai_lab_followup_days
    )
    await db.flush()
    out = await _task_response(db, row)
    out["cm_task_id"] = str(cm_task.id)
    return out


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
    return await _task_response(db, row)


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
    if row.status == "done":
        await notify_task_done(db, row)
    await db.flush()
    return {"ok": True}
