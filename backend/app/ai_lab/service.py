"""AI Lab task lifecycle helpers (webhook send, apply results, GitHub poll)."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from uuid import UUID

import httpx
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_lab.github_results import envelope_to_callback, fetch_result_file
from app.ai_lab.models import AiTask
from app.ai_lab.polling import due_for_poll, is_poll_timeout, task_age_seconds
from app.ai_lab.schemas import BotCallbackIn
from app.ai_lab.signing import sign
from app.ai_lab.snapshots import build_snapshot
from app.core.config import get_settings


def apply_bot_payload(row: AiTask, payload: dict) -> None:
    row.raw_result = json.dumps(payload, ensure_ascii=False)
    try:
        parsed = BotCallbackIn.model_validate(payload)
    except ValidationError as exc:
        row.status = "failed"
        row.error = f"Invalid bot payload: {exc}"
        row.completed_at = datetime.now(UTC)
        return
    if parsed.status == "failed":
        row.status = "failed"
        row.error = parsed.error or "Bot reported failure"
        row.completed_at = datetime.now(UTC)
        return
    assert parsed.result is not None
    row.result_json = parsed.result.model_dump_json()
    row.status = "done"
    row.error = None
    row.completed_at = datetime.now(UTC)


def apply_bot_callback(row: AiTask, parsed: BotCallbackIn) -> None:
    apply_bot_payload(row, parsed.model_dump(mode="json"))


async def notify_task_done(db: AsyncSession, row: AiTask) -> None:
    if row.trigger == "manual" or row.status != "done":
        return
    try:
        result = json.loads(row.result_json or "{}")
        summary = (result.get("summary") or "")[:400]
    except json.JSONDecodeError:
        summary = ""
    from app.services.notifications import notify

    title = "AI Lab: تحلیل آماده است"
    body = f"{row.kind}\n{summary}\n/ai-lab"
    await notify(
        db,
        organization_id=row.organization_id,
        user_id=row.created_by,
        title=title,
        body=body,
        entity_type="ai_task",
        entity_id=row.id,
    )


async def create_ai_task(
    db: AsyncSession,
    *,
    organization_id: UUID,
    user_id: UUID,
    kind: str,
    input_data: dict,
    trigger: str = "manual",
) -> AiTask:
    snap = await build_snapshot(db, organization_id, kind, input_data)
    row = AiTask(
        organization_id=organization_id,
        created_by=user_id,
        kind=kind,
        input_json=json.dumps(input_data, ensure_ascii=False),
        snapshot_json=json.dumps(snap, ensure_ascii=False),
        status="pending",
        trigger=trigger,
    )
    db.add(row)
    await db.flush()
    settings = get_settings()
    if settings.ai_lab_mode == "webhook":
        await send_outbound_webhook(row)
    await db.flush()
    return row


async def send_outbound_webhook(row: AiTask) -> None:
    settings = get_settings()
    if settings.ai_lab_mode != "webhook":
        return
    if not settings.llm_external_enabled:
        row.status = "failed"
        row.error = "External LLM/webhook disabled (LLM_EXTERNAL_ENABLED=false)"
        return
    if not settings.ai_lab_outbound_url.strip():
        row.status = "failed"
        row.error = "AI_LAB_OUTBOUND_URL not configured"
        return
    body: dict = {
        "task_id": str(row.id),
        "kind": row.kind,
        "input": json.loads(row.input_json or "{}"),
        "snapshot": json.loads(row.snapshot_json or "{}"),
        "created_at": row.created_at.isoformat() if row.created_at else datetime.now(UTC).isoformat(),
    }
    if settings.ai_lab_result_source != "github":
        body["callback_url"] = _callback_url()
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    ts = str(int(time.time()))
    signature = sign(settings.ai_lab_outbound_secret, ts, raw)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "Content-Type": "application/json",
                "X-CM-Timestamp": ts,
                "X-CM-Signature": signature,
            }
            bearer = (settings.ai_lab_outbound_bearer or "").strip()
            if bearer:
                headers["Authorization"] = f"Bearer {bearer}"
            res = await client.post(settings.ai_lab_outbound_url, content=raw, headers=headers)
        if res.status_code >= 400:
            row.status = "failed"
            row.error = f"Outbound webhook HTTP {res.status_code}"
            return
        row.sent_at = datetime.now(UTC)
        row.status = "waiting" if settings.ai_lab_result_source == "github" else "sent"
    except httpx.HTTPError as exc:
        row.status = "failed"
        row.error = f"Outbound webhook error: {exc}"


def _callback_url() -> str:
    settings = get_settings()
    base = (settings.ai_lab_callback_base or "").strip().rstrip("/")
    if not base:
        for origin in settings.cors_origins.split(","):
            origin = origin.strip().rstrip("/")
            if origin.startswith("https://"):
                base = f"{origin}/api"
                break
    if not base:
        base = "http://localhost:8000"
    return f"{base}/ai-lab/results"


async def poll_github_for_task(db: AsyncSession, row: AiTask) -> None:
    """Poll GitHub once for a waiting task. Idempotent when already done."""
    settings = get_settings()
    if settings.ai_lab_result_source != "github":
        return
    if row.status not in ("waiting", "sent"):
        return
    if row.status == "done" and row.result_json:
        return
    now = datetime.now(UTC)
    row.last_polled_at = now
    if not row.created_at:
        return
    age = task_age_seconds(row.created_at, now)
    if is_poll_timeout(age):
        row.status = "failed"
        row.error = "timeout"
        row.completed_at = now
        await db.flush()
        return
    repo = settings.ai_lab_github_repo.strip()
    token = settings.ai_lab_github_token_ro.strip()
    if not repo or not token:
        row.status = "failed"
        row.error = "GitHub polling not configured"
        row.completed_at = now
        await db.flush()
        return
    fetched = await fetch_result_file(repo, row.id, token)
    if fetched.transient_error:
        await db.flush()
        return
    if not fetched.found:
        await db.flush()
        return
    if fetched.apply_error:
        row.status = "failed"
        row.error = fetched.apply_error
        row.completed_at = now
        await db.flush()
        return
    assert fetched.payload is not None
    callback, err = envelope_to_callback(fetched.payload, row.id, settings.ai_lab_inbound_secret)
    if err == "invalid signature":
        row.status = "failed"
        row.error = "invalid signature"
        row.completed_at = now
        await db.flush()
        return
    if err or callback is None:
        row.status = "failed"
        row.error = err or "invalid result"
        row.completed_at = now
        await db.flush()
        return
    if row.status == "done" and row.result_json:
        await db.flush()
        return
    apply_bot_callback(row, callback)
    if row.status == "done":
        await notify_task_done(db, row)
    await db.flush()


async def poll_github_due_tasks(db: AsyncSession) -> int:
    """Poll all tasks that are due. Returns count polled."""
    from sqlalchemy import select

    settings = get_settings()
    if not settings.ai_lab_enabled or settings.ai_lab_result_source != "github":
        return 0
    rows = list(
        (
            await db.scalars(
                select(AiTask).where(AiTask.status.in_(("waiting", "sent")))
            )
        ).all()
    )
    count = 0
    now = datetime.now(UTC)
    for row in rows:
        if not row.created_at:
            continue
        if not due_for_poll(row.created_at, row.last_polled_at, now):
            continue
        await poll_github_for_task(db, row)
        count += 1
    return count
