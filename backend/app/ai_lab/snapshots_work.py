"""AI Lab snapshots from Mizito-synced work projects and CM tasks (aggregates, no PII)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_lab.schemas import FinanceReconcileIn, MyWorkReviewIn, ProjectsHealthIn, TeamLoadIn
from app.api.deps import AuthContext
from app.models import Task, TaskAssignee
from app.models.enums import TaskStatus
from app.perf.services.mizito_finance import mizito_finance
from app.requests.models import WorkProject
from app.requests.project_access import apply_project_visibility

_STALE_TOP = 25


def _anon_key(raw: str, mapping: dict[str, str]) -> str:
    if raw not in mapping:
        mapping[raw] = f"A{len(mapping) + 1}"
    return mapping[raw]


def _assignee_keys(raw: str | None, mapping: dict[str, str]) -> list[str]:
    if not raw:
        return []
    try:
        ids = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(ids, list):
        return []
    out: list[str] = []
    for item in ids:
        if item is None:
            continue
        key = str(item).strip()
        if not key:
            continue
        digest = sha256(key.encode()).hexdigest()[:12]
        out.append(_anon_key(digest, mapping))
    return out


def _is_open_mizito(row: WorkProject) -> bool:
    if row.mizito_removed_at:
        return False
    if row.mizito_completed_at:
        return False
    status = (row.mizito_status or "").lower()
    if status in ("done", "paid", "cancelled"):
        return False
    return bool(row.mizito_card_id)


async def _mizito_projects(
    db: AsyncSession,
    org: UUID,
    lane: str,
) -> list[WorkProject]:
    q = select(WorkProject).where(
        WorkProject.organization_id == org,
        WorkProject.mizito_card_id.is_not(None),
    )
    if lane.strip():
        q = q.where(WorkProject.mizito_lane == lane.strip())
    return list((await db.scalars(q)).all())


async def projects_health_snapshot(db: AsyncSession, org: UUID, inp: ProjectsHealthIn) -> dict:
    now = datetime.now(UTC)
    stale_cutoff = now - timedelta(days=inp.stale_days)
    today = date.today()
    rows = [r for r in await _mizito_projects(db, org, inp.lane) if _is_open_mizito(r)]

    by_lane: dict[str, int] = {}
    by_board: dict[str, int] = {}
    by_status: dict[str, int] = {}
    stale_items: list[dict] = []
    overdue_count = 0
    low_checklist = 0

    for row in rows:
        lane_key = row.mizito_lane or "—"
        board_key = (row.mizito_board or "—").strip() or "—"
        status_key = row.mizito_status or "—"
        by_lane[lane_key] = by_lane.get(lane_key, 0) + 1
        by_board[board_key] = by_board.get(board_key, 0) + 1
        by_status[status_key] = by_status.get(status_key, 0) + 1

        modified = row.mizito_modified_at
        if modified and modified.tzinfo is None:
            modified = modified.replace(tzinfo=UTC)
        days_stale = None
        if modified and modified < stale_cutoff:
            days_stale = max(0, (now - modified).days)
        if days_stale is not None:
            stale_items.append(
                {
                    "code": row.mizito_code or row.code,
                    "title": (row.title or "")[:120],
                    "board": board_key,
                    "lane": lane_key,
                    "days_stale": days_stale,
                    "checklist": f"{row.mizito_checklist_done or 0}/{row.mizito_checklist_total or 0}",
                }
            )

        if row.mizito_deadline and row.mizito_deadline < today:
            overdue_count += 1
        total = row.mizito_checklist_total or 0
        done = row.mizito_checklist_done or 0
        if total > 0 and done / total < 0.5:
            low_checklist += 1

    stale_items.sort(key=lambda x: x["days_stale"], reverse=True)
    return {
        "kind": "projects_health",
        "lane_filter": inp.lane.strip(),
        "stale_days": inp.stale_days,
        "open_cards": len(rows),
        "overdue_count": overdue_count,
        "low_checklist_count": low_checklist,
        "by_lane": by_lane,
        "by_board": by_board,
        "by_status": by_status,
        "stale_samples": stale_items[:_STALE_TOP],
        "notes": "Mizito-synced cards only; assignee names not included.",
    }


async def team_load_snapshot(db: AsyncSession, org: UUID, inp: TeamLoadIn) -> dict:
    rows = [r for r in await _mizito_projects(db, org, inp.lane) if _is_open_mizito(r)]
    mapping: dict[str, str] = {}
    by_assignee: dict[str, int] = {}
    by_board: dict[str, int] = {}
    unassigned = 0

    for row in rows:
        board_key = (row.mizito_board or "—").strip() or "—"
        by_board[board_key] = by_board.get(board_key, 0) + 1
        keys = _assignee_keys(row.mizito_assignee_ids, mapping)
        if not keys:
            unassigned += 1
            continue
        for key in keys:
            by_assignee[key] = by_assignee.get(key, 0) + 1

    cm_open = list(
        (
            await db.scalars(
                select(Task).where(
                    Task.organization_id == org,
                    Task.status.in_(
                        (TaskStatus.OPEN, TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED)
                    ),
                )
            )
        ).all()
    )
    by_owner: dict[str, int] = {}
    overdue_cm = 0
    now = datetime.now(UTC)
    owner_map: dict[str, str] = {}
    for task in cm_open:
        oid = str(task.owner_id)
        digest = sha256(oid.encode()).hexdigest()[:12]
        label = _anon_key(f"cm:{digest}", owner_map)
        by_owner[label] = by_owner.get(label, 0) + 1
        if task.deadline:
            dl = task.deadline if task.deadline.tzinfo else task.deadline.replace(tzinfo=UTC)
            if dl < now:
                overdue_cm += 1

    board_sorted = sorted(by_board.items(), key=lambda x: x[1], reverse=True)[:15]
    assignee_sorted = sorted(by_assignee.items(), key=lambda x: x[1], reverse=True)[:20]

    return {
        "kind": "team_load",
        "lane_filter": inp.lane.strip(),
        "mizito_open_cards": len(rows),
        "mizito_unassigned_open": unassigned,
        "mizito_by_assignee": dict(assignee_sorted),
        "mizito_by_board": dict(board_sorted),
        "cm_open_tasks": len(cm_open),
        "cm_overdue_tasks": overdue_cm,
        "cm_by_owner": by_owner,
        "notes": "Assignees and owners anonymized (A1, A2, …).",
    }


async def finance_reconcile_snapshot(db: AsyncSession, org: UUID, _inp: FinanceReconcileIn) -> dict:
    raw = await mizito_finance(db, org)
    to_register = [
        {
            "code": item.get("code"),
            "title": (item.get("title") or "")[:100],
            "board": item.get("board"),
            "status": item.get("status"),
            "modified_at": item.get("modified_at"),
        }
        for item in raw.get("to_register") or []
    ]
    paid_without = [
        {
            "code": item.get("code"),
            "title": (item.get("title") or "")[:100],
            "status": item.get("status"),
            "modified_at": item.get("modified_at"),
        }
        for item in raw.get("paid_without_cost") or []
    ]
    panel_only = [
        {
            "campaign_code": item.get("campaign_code"),
            "cost_number": item.get("cost_number"),
            "amount_toman": item.get("amount_toman"),
        }
        for item in raw.get("panel_without_card") or []
    ]
    return {
        "kind": "finance_reconcile",
        "connected": raw.get("connected"),
        "read_at": raw.get("read_at"),
        "counts": raw.get("counts"),
        "to_register_count": raw.get("to_register_count"),
        "to_register_samples": to_register,
        "paid_without_cost_count": raw.get("paid_without_cost_count"),
        "paid_without_cost_samples": paid_without,
        "panel_without_card_count": raw.get("panel_without_card_count"),
        "panel_without_card_samples": panel_only,
        "notes": "No IBAN or payment identifiers; descriptions stripped.",
    }


async def my_work_review_snapshot(db: AsyncSession, auth: AuthContext, _inp: MyWorkReviewIn) -> dict:
    if auth is None:
        raise HTTPException(status_code=400, detail="Auth required for my_work_review")
    org = auth.organization_id
    user_id = auth.user.id
    now = datetime.now(UTC)

    assigned_ids = set(
        (await db.scalars(select(TaskAssignee.task_id).where(TaskAssignee.user_id == user_id))).all()
    )
    tasks = list(
        (
            await db.scalars(
                select(Task).where(
                    Task.organization_id == org,
                    Task.status.in_(
                        (TaskStatus.OPEN, TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED)
                    ),
                )
            )
        ).all()
    )
    mine = [t for t in tasks if t.owner_id == user_id or t.id in assigned_ids]
    task_rows = []
    overdue = 0
    for task in mine:
        dl = task.deadline
        is_over = False
        if dl:
            dlt = dl if dl.tzinfo else dl.replace(tzinfo=UTC)
            is_over = dlt < now
            if is_over:
                overdue += 1
        age_days = (now - (task.created_at.replace(tzinfo=UTC) if task.created_at else now)).days
        task_rows.append(
            {
                "title": (task.title or "")[:120],
                "priority": task.priority.value if task.priority else None,
                "status": task.status.value if task.status else None,
                "overdue": is_over,
                "age_days": age_days,
            }
        )

    q = select(WorkProject).where(WorkProject.organization_id == org)
    q = await apply_project_visibility(q, db, auth)
    projects = list((await db.scalars(q)).all())
    open_projects = [p for p in projects if (p.status or "") != "done"]
    project_rows = [
        {
            "code": p.mizito_code or p.code,
            "title": (p.title or "")[:120],
            "status": p.status,
            "mizito_board": p.mizito_board,
            "checklist": f"{p.mizito_checklist_done or 0}/{p.mizito_checklist_total or 0}",
        }
        for p in open_projects[:40]
    ]

    return {
        "kind": "my_work_review",
        "open_tasks": len(mine),
        "overdue_tasks": overdue,
        "tasks": task_rows[:30],
        "visible_open_projects": len(open_projects),
        "projects": project_rows,
        "notes": "Scoped to current user tasks and visible projects only.",
    }
