"""کانبان پروژه‌ها: ستون = برد میزیتو، کارت = پروژهٔ CM."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext
from app.models import User
from app.requests.mizito_lanes import LANE_BY_SLUG, is_archive_board_title
from app.requests.models import WorkMizitoLaneBoard, WorkProject
from app.requests.project_access import apply_project_visibility, base_visible_projects

_SKIP_IMPORT = frozenset({"sales_circulars"})
_DONE = "done"


def _board_key(board_id: str | None, board_title: str | None) -> str:
    bid = (board_id or "").strip()
    if bid:
        return bid
    return f"title:{(board_title or '').strip()}"


def _search_clause(q: str):
    needle = f"%{q.strip()}%"
    return or_(WorkProject.title.ilike(needle), WorkProject.code.ilike(needle))


def _lane_filters(lane_slug: str, source: str, q: str, hide_done: bool) -> list:
    clauses = [WorkProject.mizito_lane == lane_slug]
    if source == "mizito":
        clauses.append(WorkProject.mizito_card_id.is_not(None))
    elif source == "cm":
        clauses.append(WorkProject.mizito_card_id.is_(None))
    if q.strip():
        clauses.append(_search_clause(q))
    if hide_done:
        clauses.append(WorkProject.status != _DONE)
    return clauses


async def _visible_lane_query(
    db: AsyncSession, ctx: AuthContext, lane_slug: str, source: str, q: str, hide_done: bool
) -> Select:
    query = base_visible_projects(ctx.organization_id).where(*_lane_filters(lane_slug, source, q, hide_done))
    return await apply_project_visibility(query, db, ctx)


def _board_filter(board_id: str):
    if board_id == "cm":
        return WorkProject.mizito_card_id.is_(None)
    if board_id.startswith("title:"):
        title = board_id[6:]
        return and_(
            or_(WorkProject.mizito_board_id.is_(None), WorkProject.mizito_board_id == ""),
            WorkProject.mizito_board == title,
        )
    return WorkProject.mizito_board_id == board_id


async def _count_board(
    db: AsyncSession, base: Select, board_id: str, *, count_done_split: bool
) -> tuple[int, int, int]:
    scoped = base.where(_board_filter(board_id))
    total = await db.scalar(select(func.count()).select_from(scoped.subquery())) or 0
    if not count_done_split:
        return int(total), 0, 0
    open_q = scoped.where(WorkProject.status != _DONE)
    done_q = scoped.where(WorkProject.status == _DONE)
    open_count = await db.scalar(select(func.count()).select_from(open_q.subquery())) or 0
    done_count = await db.scalar(select(func.count()).select_from(done_q.subquery())) or 0
    return int(total), int(open_count), int(done_count)


async def _assignee_labels(db: AsyncSession, organization_id: UUID, raw: str | None) -> tuple[list[str], int]:
    if not raw:
        return [], 0
    try:
        ids = json.loads(raw)
    except json.JSONDecodeError:
        return [], 0
    if not isinstance(ids, list):
        return [], 0
    uuids: list[UUID] = []
    for item in ids:
        try:
            uuids.append(UUID(str(item)))
        except ValueError:
            continue
    if not uuids:
        return [], 0
    users = list(await db.scalars(select(User).where(User.organization_id == organization_id, User.id.in_(uuids))))
    names = [u.full_name or u.email or "" for u in users]
    names = [n for n in names if n][:3]
    return names, max(0, len(uuids) - len(names))


def _iso_dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _project_brief(row: WorkProject, assignee_names: list[str], assignee_extra: int) -> dict:
    due = row.mizito_deadline
    if due is None and row.due_date:
        due = datetime.combine(row.due_date, datetime.min.time(), tzinfo=UTC)
    overdue = False
    if due is not None:
        now = datetime.now(UTC).date()
        due_date = due.date() if isinstance(due, datetime) else due
        overdue = due_date < now and row.status != _DONE
    due_out = None
    if isinstance(due, datetime):
        due_out = due.isoformat()
    elif row.due_date:
        due_out = row.due_date.isoformat()
    return {
        "id": str(row.id),
        "code": row.code,
        "title": row.title,
        "status": row.status,
        "source": "mizito" if row.mizito_card_id else "cm",
        "mizito_card_id": row.mizito_card_id,
        "mizito_status": row.mizito_status,
        "mizito_code": row.mizito_code,
        "weight": row.mizito_weight or 0,
        "due": due_out,
        "overdue": overdue,
        "checklist_done": row.mizito_checklist_done or 0,
        "checklist_total": row.mizito_checklist_total or 0,
        "attachments": row.mizito_attachments or 0,
        "has_comments": bool(row.mizito_has_comments),
        "modified_at": _iso_dt(row.mizito_modified_at),
        "assignee_names": assignee_names,
        "assignee_extra": assignee_extra,
    }


async def _briefs_for_rows(db: AsyncSession, organization_id: UUID, rows: list[WorkProject]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        names, extra = await _assignee_labels(db, organization_id, row.mizito_assignee_ids)
        out.append(_project_brief(row, names, extra))
    return out


async def _fetch_column_projects(
    db: AsyncSession,
    base: Select,
    board_id: str,
    offset: int,
    limit: int,
) -> list[WorkProject]:
    query = base.where(_board_filter(board_id))
    query = query.order_by(WorkProject.mizito_weight.asc().nulls_last(), WorkProject.title.asc())
    return list(await db.scalars(query.offset(offset).limit(limit)))


async def mizito_lane_kanban(
    db: AsyncSession,
    ctx: AuthContext,
    lane_slug: str,
    source: str = "",
    q: str = "",
    hide_done: bool = False,
    include_archive: bool = False,
    per_column: int = 20,
) -> dict:
    lane = LANE_BY_SLUG.get(lane_slug)
    if lane is None:
        return {"lane": lane_slug, "lane_title": "", "columns": [], "import_ready": False, "lane_total": 0}

    base = await _visible_lane_query(db, ctx, lane_slug, source, q, hide_done)
    visible_ids = base.with_only_columns(WorkProject.id).subquery()

    boards = list(
        await db.scalars(
            select(WorkMizitoLaneBoard)
            .where(
                WorkMizitoLaneBoard.organization_id == ctx.organization_id,
                WorkMizitoLaneBoard.lane_slug == lane_slug,
                WorkMizitoLaneBoard.removed.is_(False),
            )
            .order_by(WorkMizitoLaneBoard.position.asc(), WorkMizitoLaneBoard.title.asc())
        )
    )
    column_defs: list[dict] = [
        {
            "board_id": b.board_id,
            "title": b.title,
            "position": b.position,
            "is_archive": is_archive_board_title(b.title),
        }
        for b in boards
    ]
    known = {c["board_id"] for c in column_defs}
    orphan_rows = await db.execute(
        select(
            WorkProject.mizito_board_id,
            WorkProject.mizito_board,
            func.min(WorkProject.mizito_board_position).label("pos"),
        )
        .where(WorkProject.id.in_(select(visible_ids.c.id)))
        .where(WorkProject.mizito_card_id.is_not(None))
        .group_by(WorkProject.mizito_board_id, WorkProject.mizito_board)
    )
    for row in orphan_rows:
        key = _board_key(row.mizito_board_id, row.mizito_board)
        if key in known:
            continue
        title = row.mizito_board or "بدون برد"
        column_defs.append(
            {
                "board_id": key,
                "title": title,
                "position": row.pos if row.pos is not None else 999,
                "is_archive": is_archive_board_title(title),
            }
        )
        known.add(key)

    column_defs.sort(key=lambda col: (col["position"], col["title"]))
    ordered: list[dict] = []
    lane_total = 0
    for col_def in column_defs:
        if not include_archive and col_def["is_archive"] and not q.strip():
            continue
        bid = col_def["board_id"]
        total, open_count, done_count = await _count_board(db, base, bid, count_done_split=True)
        if total == 0 and not q.strip():
            continue
        lane_total += total
        rows = await _fetch_column_projects(db, base, bid, 0, per_column)
        projects = await _briefs_for_rows(db, ctx.organization_id, rows)
        ordered.append(
            {
                "board_id": bid,
                "title": col_def["title"],
                "position": col_def["position"],
                "is_archive": col_def["is_archive"],
                "total": total,
                "open_count": open_count,
                "done_count": done_count,
                "projects": projects,
                "has_more": total > len(projects),
            }
        )

    if source != "mizito":
        cm_total, cm_open, cm_done = await _count_board(db, base, "cm", count_done_split=True)
        if cm_total > 0 or q.strip():
            cm_rows = await _fetch_column_projects(db, base, "cm", 0, per_column)
            cm_briefs = await _briefs_for_rows(db, ctx.organization_id, cm_rows)
            lane_total += cm_total
            ordered.append(
                {
                    "board_id": "cm",
                    "title": "پروژه‌های CM",
                    "position": 10000,
                    "is_archive": False,
                    "total": cm_total,
                    "open_count": cm_open,
                    "done_count": cm_done,
                    "projects": sorted(cm_briefs, key=lambda item: item["title"]),
                    "has_more": cm_total > len(cm_briefs),
                }
            )

    return {
        "lane": lane_slug,
        "lane_title": lane.title,
        "import_ready": lane_slug not in _SKIP_IMPORT,
        "lane_total": lane_total,
        "columns": ordered,
    }


async def mizito_kanban_column(
    db: AsyncSession,
    ctx: AuthContext,
    lane_slug: str,
    board_id: str,
    source: str = "",
    q: str = "",
    hide_done: bool = False,
    offset: int = 0,
    limit: int = 20,
) -> dict:
    base = await _visible_lane_query(db, ctx, lane_slug, source, q, hide_done)
    total, open_count, done_count = await _count_board(db, base, board_id, count_done_split=True)
    rows = await _fetch_column_projects(db, base, board_id, offset, limit)
    projects = await _briefs_for_rows(db, ctx.organization_id, rows)
    return {
        "board_id": board_id,
        "total": total,
        "open_count": open_count,
        "done_count": done_count,
        "projects": projects,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(projects) < total,
    }
