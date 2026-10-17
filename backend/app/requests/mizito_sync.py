"""همگام‌سازی diff کارت‌های میزیتو → پروژهٔ کار. فقط فیلدهای مالک میزیتو نوشته می‌شوند."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Organization, Task, TaskAssignee, TaskDependency, TaskNote, TaskParticipant, Team, User
from app.models.enums import TaskRole, TaskStatus
from app.perf.models import PmIntegration
from app.perf.services.mizito import card_url_prefix, for_perf, iso, mizito_full_read, now
from app.requests.mizito_lanes import LANE_BY_SLUG, lane_slug_for_mizito_project_title
from app.requests.models import (
    DesignDeliverable,
    Shoot,
    WorkAttachment,
    WorkMizitoChange,
    WorkMizitoLaneBoard,
    WorkMizitoSyncRun,
    WorkProject,
    WorkProjectMember,
    WorkRequest,
)
from app.requests.spine import ensure_thread

_PROJECT_STATUS = {"idea": "new", "todo": "new", "in_progress": "in_progress", "review": "in_progress"}
_DONE_MIZITO = frozenset({"done", "paid", "cancelled", "not_in_cost_tracking"})
_SKIP_IMPORT = frozenset({"sales_circulars"})
_BACKOFF = timedelta(hours=1)
_LOG_FIELDS = ("title", "mizito_lane", "mizito_board", "status", "mizito_code", "due_date")


def _project_status(card: dict) -> str:
    if card.get("completed") or str(card.get("status") or "") in _DONE_MIZITO:
        return "done"
    return _PROJECT_STATUS.get(str(card.get("status") or ""), "in_progress")


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def card_hash(card: dict, lane: str) -> str:
    items = [
        {"id": str(item.get("id") or ""), "title": str(item.get("title") or ""), "checked": bool(item.get("checked"))}
        for item in card.get("checklist_items") or []
        if isinstance(item, dict)
    ]
    payload = {
        "lane": lane,
        "title": str(card.get("title") or ""),
        "board_id": str(card.get("board_id") or ""),
        "board": str(card.get("board") or ""),
        "status": str(card.get("status") or ""),
        "completed": bool(card.get("completed")),
        "code": str(card.get("code") or ""),
        "weight": card.get("weight") or 0,
        "progress": card.get("progress") or 0,
        "deadline": card.get("deadline"),
        "modified_at": card.get("modified_at"),
        "assignees": list(card.get("assignees") or []),
        "checklist": items,
        "attachments": card.get("attachments") or 0,
        "has_comments": bool(card.get("has_comments")),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _values(card: dict, lane: str) -> dict[str, Any]:
    deadline = _parse_dt(card.get("deadline"))
    return {
        "title": str(card.get("title") or "کارت میزیتو")[:200],
        "kind": LANE_BY_SLUG[lane].title,
        "status": _project_status(card),
        "due_date": deadline.date() if deadline else None,
        "mizito_lane": lane,
        "mizito_project_id": str(card.get("project_id") or "")[:64] or None,
        "mizito_board": str(card.get("board") or "")[:200] or None,
        "mizito_board_id": str(card.get("board_id") or "")[:64] or None,
        "mizito_board_position": card.get("board_position") if isinstance(card.get("board_position"), int) else None,
        "mizito_status": str(card.get("status") or "")[:40] or None,
        "mizito_weight": float(card.get("weight") or 0),
        "mizito_created_at": _parse_dt(card.get("created_at")),
        "mizito_modified_at": _parse_dt(card.get("modified_at")),
        "mizito_completed_at": _parse_dt(card.get("completed_at")),
        "mizito_deadline": deadline,
        "mizito_code": str(card.get("code") or "")[:40] or None,
        "mizito_progress": int(card.get("progress") or 0),
        "mizito_checklist_done": int(card.get("checklist_done") or 0),
        "mizito_checklist_total": int(card.get("checklist_total") or 0),
        "mizito_attachments": int(card.get("attachments") or 0),
        "mizito_has_comments": bool(card.get("has_comments")),
        "mizito_assignee_ids": json.dumps(list(card.get("assignees") or []), ensure_ascii=False),
    }


async def _actor_id(db: AsyncSession, organization_id: UUID) -> UUID:
    row = await db.scalar(select(User.id).where(User.organization_id == organization_id).order_by(User.email.asc()).limit(1))
    if row is None:
        raise RuntimeError("هیچ کاربری برای سازمان پیدا نشد")
    return row


def _next_code(existing: list[str], prefix: str = "MZ-") -> tuple[str, int]:
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    max_n = 0
    for code in existing:
        match = pattern.match(str(code or ""))
        if match:
            max_n = max(max_n, int(match.group(1)))
    return f"{prefix}{max_n + 1:04d}", max_n + 1


def _log(
    db: AsyncSession,
    organization_id: UUID,
    project_id: UUID | None,
    kind: str,
    field: str,
    old: Any,
    new: Any,
    status: str = "applied",
) -> None:
    db.add(
        WorkMizitoChange(
            organization_id=organization_id,
            project_id=project_id,
            kind=kind,
            field=field,
            old_value=str(old if old is not None else ""),
            new_value=str(new if new is not None else ""),
            status=status,
        )
    )


async def _upsert_boards(db: AsyncSession, organization_id: UUID, rows: list[dict]) -> None:
    current = list(
        await db.scalars(select(WorkMizitoLaneBoard).where(WorkMizitoLaneBoard.organization_id == organization_id))
    )
    by_key = {(row.lane_slug, row.board_id): row for row in current}
    seen: set[tuple[str, str]] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        slug = str(raw.get("lane_slug") or "").strip()
        board_id = str(raw.get("board_id") or "").strip()
        title = str(raw.get("title") or "")[:200]
        if not slug or not board_id or not title:
            continue
        position = raw.get("position") if isinstance(raw.get("position"), int) else 0
        key = (slug, board_id)
        seen.add(key)
        row = by_key.get(key)
        if row is None:
            db.add(
                WorkMizitoLaneBoard(
                    organization_id=organization_id,
                    lane_slug=slug,
                    board_id=board_id,
                    title=title,
                    position=position,
                    removed=False,
                )
            )
        else:
            row.title = title
            row.position = position
            row.removed = False
    for key, row in by_key.items():
        if key not in seen:
            row.removed = True
    await db.flush()


async def _sync_checklist(db: AsyncSession, organization_id: UUID, project: WorkProject, card: dict, actor: UUID) -> None:
    items = [item for item in (card.get("checklist_items") or []) if isinstance(item, dict) and item.get("id")]
    existing = list(
        await db.scalars(select(Task).where(Task.organization_id == organization_id, Task.project_id == project.id))
    )
    by_ref = {str(task.external_ref): task for task in existing if task.external_ref}
    seen: set[str] = set()
    for item in items:
        ref = str(item.get("id"))[:80]
        seen.add(ref)
        title = str(item.get("title") or "مورد چک‌لیست")[:255]
        done = bool(item.get("checked"))
        status = TaskStatus.COMPLETED if done else TaskStatus.OPEN
        task = by_ref.get(ref)
        if task is None:
            task = Task(
                organization_id=organization_id,
                project_id=project.id,
                title=title,
                description="از چک‌لیست میزیتو",
                owner_id=actor,
                status=status,
                external_ref=ref,
            )
            db.add(task)
            await db.flush()
            db.add(TaskAssignee(task_id=task.id, user_id=actor, role=TaskRole.ASSIGNEE))
        else:
            task.title = title
            task.status = status
    for ref, task in by_ref.items():
        if ref not in seen and task.status != TaskStatus.CANCELLED:
            task.status = TaskStatus.CANCELLED


async def apply_mizito_cards(
    db: AsyncSession,
    organization_id: UUID,
    snap: dict,
    *,
    actor: UUID | None = None,
) -> dict[str, Any]:
    """اعمال diff. اعضای پروژه، بودجه، مسئول و وظایف دستی دست نمی‌خورند."""
    actor = actor or await _actor_id(db, organization_id)
    await _upsert_boards(db, organization_id, snap.get("lane_boards") or [])
    truncated_titles = set(snap.get("truncated_projects") or [])
    cards = [card for card in (snap.get("cards") or []) if isinstance(card, dict)]
    existing = list(
        await db.scalars(
            select(WorkProject).where(
                WorkProject.organization_id == organization_id,
                WorkProject.mizito_card_id.is_not(None),
            )
        )
    )
    by_card = {str(row.mizito_card_id): row for row in existing}
    codes = list(await db.scalars(select(WorkProject.code).where(WorkProject.organization_id == organization_id)))
    _, seq = _next_code(list(codes))
    teams = {
        row.code: row.id
        for row in (await db.scalars(select(Team).where(Team.organization_id == organization_id))).all()
    }
    created = updated = unchanged = pending = skipped = 0
    seen: set[str] = set()

    for card in cards:
        lane = lane_slug_for_mizito_project_title(str(card.get("project") or ""))
        card_id = str(card.get("id") or "").strip()
        if not lane or not card_id:
            skipped += 1
            continue
        if lane in _SKIP_IMPORT:
            skipped += 1
            continue
        seen.add(card_id)
        digest = card_hash(card, lane)
        row = by_card.get(card_id)
        values = _values(card, lane)
        team_id = teams.get(LANE_BY_SLUG[lane].team_code)
        if row is None:
            code = f"MZ-{seq:04d}"
            seq += 1
            row = WorkProject(
                organization_id=organization_id,
                code=code,
                lead_user_id=actor,
                created_by=actor,
                team_id=team_id,
                mizito_card_id=card_id,
                mizito_hash=digest,
                mizito_missing_runs=0,
                **values,
            )
            if values["mizito_created_at"]:
                row.created_at = values["mizito_created_at"]
            db.add(row)
            await db.flush()
            await ensure_thread(db, organization_id=organization_id, actor_id=actor, project_id=row.id, topic=values["title"])
            _log(db, organization_id, row.id, "created", "title", "", values["title"])
            by_card[card_id] = row
            created += 1
        elif row.mizito_hash == digest and not row.mizito_removed_at and not row.mizito_missing_runs:
            unchanged += 1
            await _sync_checklist(db, organization_id, row, card, actor)
            continue
        else:
            changes = []
            for field in _LOG_FIELDS:
                old = getattr(row, field)
                new = values[field]
                if str(old if old is not None else "") != str(new if new is not None else ""):
                    changes.append((field, old, new))
            for key, value in values.items():
                setattr(row, key, value)
            if team_id:
                row.team_id = team_id
            row.mizito_hash = digest
            row.mizito_missing_runs = 0
            row.mizito_removed_at = None
            row.updated_at = datetime.now(UTC)
            for field, old, new in changes:
                _log(db, organization_id, row.id, "updated", field, old, new)
            await _clear_pending(db, organization_id, row.id)
            updated += 1
        await _sync_checklist(db, organization_id, row, card, actor)

    truncated_ids = {
        str(card.get("project_id") or "")
        for card in cards
        if str(card.get("project") or "") in truncated_titles
    }
    for row in existing:
        if not row.mizito_card_id or row.mizito_card_id in seen or row.mizito_removed_at:
            continue
        if row.mizito_project_id and row.mizito_project_id in truncated_ids:
            continue
        row.mizito_missing_runs = int(row.mizito_missing_runs or 0) + 1
        if row.mizito_missing_runs < 2:
            continue
        open_pending = await db.scalar(
            select(WorkMizitoChange.id).where(
                WorkMizitoChange.organization_id == organization_id,
                WorkMizitoChange.project_id == row.id,
                WorkMizitoChange.status == "pending",
            )
        )
        if open_pending:
            continue
        _log(db, organization_id, row.id, "missing", "mizito_card_id", row.mizito_card_id, "", status="pending")
        pending += 1

    await db.flush()
    return {
        "ok": True,
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "pending": pending,
        "skipped": skipped,
        "truncated": bool(snap.get("truncated")),
        "truncated_projects": list(truncated_titles),
    }


async def _clear_pending(db: AsyncSession, organization_id: UUID, project_id: UUID) -> None:
    rows = list(
        await db.scalars(
            select(WorkMizitoChange).where(
                WorkMizitoChange.organization_id == organization_id,
                WorkMizitoChange.project_id == project_id,
                WorkMizitoChange.status == "pending",
            )
        )
    )
    for row in rows:
        row.status = "ignored"
        row.decided_at = datetime.now(UTC)


async def purge_manual_work_data(db: AsyncSession, organization_id: UUID) -> dict[str, int]:
    project_ids = list(
        await db.scalars(
            select(WorkProject.id).where(
                WorkProject.organization_id == organization_id,
                WorkProject.mizito_card_id.is_(None),
            )
        )
    )
    if project_ids:
        task_ids = select(Task.id).where(Task.project_id.in_(project_ids))
        await db.execute(delete(TaskAssignee).where(TaskAssignee.task_id.in_(task_ids)))
        await db.execute(delete(TaskParticipant).where(TaskParticipant.task_id.in_(task_ids)))
        await db.execute(
            delete(TaskDependency).where(
                or_(TaskDependency.dependent_task_id.in_(task_ids), TaskDependency.prerequisite_task_id.in_(task_ids))
            )
        )
        await db.execute(delete(TaskNote).where(TaskNote.task_id.in_(task_ids)))
        await db.execute(delete(Task).where(Task.project_id.in_(project_ids)))
        await db.execute(delete(DesignDeliverable).where(DesignDeliverable.project_id.in_(project_ids)))
        await db.execute(delete(Shoot).where(Shoot.project_id.in_(project_ids)))
        await db.execute(delete(WorkProjectMember).where(WorkProjectMember.project_id.in_(project_ids)))
        await db.execute(delete(WorkAttachment).where(WorkAttachment.project_id.in_(project_ids)))
        await db.execute(delete(WorkProject).where(WorkProject.id.in_(project_ids)))
    req_ids = list(await db.scalars(select(WorkRequest.id).where(WorkRequest.organization_id == organization_id)))
    if req_ids:
        req_task_ids = select(Task.id).where(Task.request_id.in_(req_ids))
        await db.execute(delete(TaskAssignee).where(TaskAssignee.task_id.in_(req_task_ids)))
        await db.execute(delete(TaskParticipant).where(TaskParticipant.task_id.in_(req_task_ids)))
        await db.execute(
            delete(TaskDependency).where(
                or_(
                    TaskDependency.dependent_task_id.in_(req_task_ids),
                    TaskDependency.prerequisite_task_id.in_(req_task_ids),
                )
            )
        )
        await db.execute(delete(TaskNote).where(TaskNote.task_id.in_(req_task_ids)))
        await db.execute(delete(Task).where(Task.request_id.in_(req_ids)))
        await db.execute(delete(WorkAttachment).where(WorkAttachment.request_id.in_(req_ids)))
        await db.execute(delete(WorkRequest).where(WorkRequest.id.in_(req_ids)))
    await db.flush()
    return {"projects_removed": len(project_ids), "requests_removed": len(req_ids)}


async def sync_mizito_cards_to_projects(
    db: AsyncSession,
    organization_id: UUID,
    *,
    token: str,
    purge_manual: bool = False,
) -> dict[str, Any]:
    purged = await purge_manual_work_data(db, organization_id) if purge_manual else {"projects_removed": 0, "requests_removed": 0}
    snap = await mizito_full_read(token)
    if not snap.get("connected"):
        await _record_run(db, organization_id, ok=False, error=str(snap.get("reason") or "میزیتو وصل نشد"))
        await _remember_error(db, organization_id, str(snap.get("reason") or ""))
        return {"ok": False, "reason": snap.get("reason") or "میزیتو وصل نشد", "purged": purged}
    result = await apply_mizito_cards(db, organization_id, snap)
    await _save_perf_snapshot(db, organization_id, snap)
    await _record_run(
        db,
        organization_id,
        ok=True,
        created=result["created"],
        updated=result["updated"],
        unchanged=result["unchanged"],
        pending=result["pending"],
        truncated=result["truncated"],
        truncated_projects=result["truncated_projects"],
    )
    result["purged"] = purged
    return result


async def _save_perf_snapshot(db: AsyncSession, organization_id: UUID, snap: dict) -> None:
    perf = for_perf(snap)
    row = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
    if row is None:
        row = PmIntegration(organization_id=organization_id)
        db.add(row)
    payload = {
        "connected": True,
        "reason": "",
        "projects": perf.get("projects") or [],
        "cards": perf.get("cards") or [],
        "open_count": perf.get("open_count") or 0,
        "total_count": perf.get("total_count") or 0,
        "lane_boards": perf.get("lane_boards") or [],
    }
    row.mizito_snapshot = json.dumps(payload, ensure_ascii=False)
    row.mizito_read_at = now()
    await db.flush()


async def _remember_error(db: AsyncSession, organization_id: UUID, reason: str) -> None:
    if "401" not in reason and "پذیرفته نشد" not in reason:
        return
    row = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
    if row is None:
        return
    stored: dict = {}
    if (row.mizito_snapshot or "").strip():
        try:
            parsed = json.loads(row.mizito_snapshot)
            if isinstance(parsed, dict):
                stored = parsed
        except json.JSONDecodeError:
            stored = {}
    stored["last_error"] = reason[:500]
    stored["last_error_at"] = iso(now())
    stored["connected"] = False
    row.mizito_snapshot = json.dumps(stored, ensure_ascii=False)
    await db.flush()


async def _record_run(
    db: AsyncSession,
    organization_id: UUID,
    *,
    ok: bool,
    error: str = "",
    created: int = 0,
    updated: int = 0,
    unchanged: int = 0,
    pending: int = 0,
    truncated: bool = False,
    truncated_projects: list[str] | None = None,
) -> None:
    started = now()
    db.add(
        WorkMizitoSyncRun(
            organization_id=organization_id,
            started_at=started,
            finished_at=started,
            ok=ok,
            error=error[:500],
            created_count=created,
            updated_count=updated,
            unchanged_count=unchanged,
            pending_count=pending,
            truncated=truncated,
            truncated_projects=", ".join(truncated_projects or []),
        )
    )
    await db.flush()


def _is_auth_error(text: str) -> bool:
    return "401" in text or "پذیرفته نشد" in text


async def should_backoff(db: AsyncSession, organization_id: UUID) -> bool:
    """بعد از ۴۰۱، تا یک ساعت یا تا ذخیرهٔ توکن تازه، دوباره به میزیتو نزن."""
    run = await db.scalar(
        select(WorkMizitoSyncRun)
        .where(WorkMizitoSyncRun.organization_id == organization_id)
        .order_by(WorkMizitoSyncRun.finished_at.desc())
        .limit(1)
    )
    if run is None or run.ok or not _is_auth_error(run.error or "") or not run.finished_at:
        return False
    finished = run.finished_at if run.finished_at.tzinfo else run.finished_at.replace(tzinfo=UTC)
    if datetime.now(UTC) - finished >= _BACKOFF:
        return False
    integration = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
    updated = integration.updated_at if integration else None
    if updated is not None:
        updated = updated if updated.tzinfo else updated.replace(tzinfo=UTC)
        if updated > finished:
            return False
    return True


async def sync_status(db: AsyncSession, organization_id: UUID) -> dict:
    run = await db.scalar(
        select(WorkMizitoSyncRun)
        .where(WorkMizitoSyncRun.organization_id == organization_id)
        .order_by(WorkMizitoSyncRun.started_at.desc())
        .limit(1)
    )
    pending = await db.scalar(
        select(WorkMizitoChange.id).where(
            WorkMizitoChange.organization_id == organization_id,
            WorkMizitoChange.status == "pending",
        )
    )
    from sqlalchemy import func

    pending_count = await db.scalar(
        select(func.count()).select_from(WorkMizitoChange).where(
            WorkMizitoChange.organization_id == organization_id,
            WorkMizitoChange.status == "pending",
        )
    )
    return {
        "last_run": None
        if run is None
        else {
            "ok": run.ok,
            "error": run.error,
            "started_at": iso(run.started_at),
            "finished_at": iso(run.finished_at),
            "created": run.created_count,
            "updated": run.updated_count,
            "unchanged": run.unchanged_count,
            "pending": run.pending_count,
            "truncated": run.truncated,
            "truncated_projects": run.truncated_projects,
        },
        "pending_count": int(pending_count or 0),
        "has_pending": bool(pending),
        "card_url_prefix": card_url_prefix(),
    }


async def decide_change(db: AsyncSession, organization_id: UUID, change_id: UUID, actor_id: UUID, approve: bool) -> dict:
    row = await db.get(WorkMizitoChange, change_id)
    if row is None or row.organization_id != organization_id or row.status != "pending":
        raise LookupError("تغییر پیدا نشد")
    row.status = "approved" if approve else "ignored"
    row.decided_by = actor_id
    row.decided_at = datetime.now(UTC)
    if approve and row.project_id:
        project = await db.get(WorkProject, row.project_id)
        if project and project.organization_id == organization_id:
            project.mizito_removed_at = datetime.now(UTC)
    elif row.project_id:
        project = await db.get(WorkProject, row.project_id)
        if project and project.organization_id == organization_id:
            project.mizito_missing_runs = 0
    await db.flush()
    return {"id": str(row.id), "status": row.status}


async def run_org_mizito_sync(db: AsyncSession, organization_id: UUID, token: str) -> dict[str, Any]:
    if await should_backoff(db, organization_id):
        return {"ok": False, "skipped": "backoff", "reason": "توکن میزیتو رد شده؛ تا ذخیرهٔ توکن تازه یا یک ساعت صبر می‌شود."}
    return await sync_mizito_cards_to_projects(db, organization_id, token=token, purge_manual=False)
