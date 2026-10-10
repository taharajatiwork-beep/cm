"""Central data-scope filter.

Levels: organization, branch, department, team, self.
Rows with a null scope column stay visible at that level so unassigned
records are not hidden from the people who created them. Organization-level
roles see the whole tenant.

A person also only sees another department's work when that row is actually
theirs (they own it, are assigned, or are a participant). Sales does not
see marketing projects, and marketing does not see sales cases, unless
they were explicitly pulled into that one item.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, false, or_, select
from sqlalchemy.sql import Select


@dataclass
class DataScopeContext:
    level: str
    user_id: UUID
    branch_id: UUID | None
    department_id: UUID | None
    team_id: UUID | None
    is_org_wide: bool
    team_ids: tuple[UUID, ...] = ()


def apply_scope(stmt: Select, model, scope: DataScopeContext | None) -> Select:
    clause = scope_clause(model, scope)
    if clause is None:
        return stmt
    return stmt.where(clause)


def scope_clause(model, scope: DataScopeContext | None):
    if scope is None or scope.is_org_wide or scope.level == "organization":
        return None

    base = _level_clause(model, scope)
    section = _section_clause(model, scope)
    personal = _personal_clause(model, scope)

    narrowed = base
    if section is not None:
        narrowed = section if narrowed is None else and_(narrowed, section)
    if personal is None:
        return narrowed
    if narrowed is None:
        return personal
    return or_(personal, narrowed)


def _level_clause(model, scope: DataScopeContext):
    level = scope.level
    cols = set(model.__table__.columns.keys())

    if level == "department" and "department_id" not in cols:
        level = "branch"
    if level == "team" and "team_id" not in cols:
        level = "branch" if "branch_id" in cols or "work_item_id" in cols else "self"

    if level == "branch":
        return _match_nullable(model, cols, "branch_id", scope.branch_id, scope)
    if level == "department":
        return _match_nullable(model, cols, "department_id", scope.department_id, scope)
    if level == "team_tree":
        ids = scope.team_ids or ((scope.team_id,) if scope.team_id else ())
        if "team_id" not in cols or not ids:
            return _self_clause(model, cols, scope)
        return or_(model.team_id.in_(ids), model.team_id.is_(None))
    if level == "team":
        return _match_nullable(model, cols, "team_id", scope.team_id, scope)
    if level == "self":
        return _self_clause(model, cols, scope)
    return None


def _section_clause(model, scope: DataScopeContext):
    """Keep a department's projects, cases and campaigns out of other departments.

    Rows with no department stay visible so older records and tests are unchanged.
    """
    if not scope.department_id:
        return None
    cols = set(model.__table__.columns.keys())
    # Colleagues stay visible across sections; only work records are split.
    if model.__tablename__ in ("work_items", "cases", "campaigns") and "department_id" in cols:
        return or_(
            model.department_id == scope.department_id,
            model.department_id.is_(None),
        )
    if model.__tablename__ == "tasks" and "work_item_id" in cols:
        from app.models import WorkItem

        return or_(
            model.work_item_id.is_(None),
            model.work_item_id.in_(
                select(WorkItem.id).where(
                    or_(
                        WorkItem.department_id == scope.department_id,
                        WorkItem.department_id.is_(None),
                    )
                )
            ),
        )
    if model.__tablename__ == "conversations":
        from app.models import Campaign, WorkItem

        same_work = model.work_item_id.in_(
            select(WorkItem.id).where(
                or_(
                    WorkItem.department_id == scope.department_id,
                    WorkItem.department_id.is_(None),
                )
            )
        )
        same_campaign = model.campaign_id.in_(
            select(Campaign.id).where(
                or_(
                    Campaign.department_id == scope.department_id,
                    Campaign.department_id.is_(None),
                )
            )
        )
        # A thread that is not tied to a project or campaign stays on the
        # existing branch/team rule. Only linked threads are split by section.
        unlinked = and_(model.work_item_id.is_(None), model.campaign_id.is_(None))
        return or_(unlinked, same_work, same_campaign)
    return None


def _personal_clause(model, scope: DataScopeContext):
    """Work the person was explicitly pulled into, even from another section."""
    if not scope.department_id:
        return None
    name = model.__tablename__
    if name == "work_items":
        from app.models import WorkItemParticipant

        return model.id.in_(
            select(WorkItemParticipant.work_item_id).where(
                WorkItemParticipant.user_id == scope.user_id
            )
        )
    if name == "tasks":
        from app.models import TaskAssignee

        return or_(
            model.owner_id == scope.user_id,
            model.id.in_(
                select(TaskAssignee.task_id).where(TaskAssignee.user_id == scope.user_id)
            ),
        )
    if name == "cases":
        return or_(model.owner_id == scope.user_id, model.created_by == scope.user_id)
    if name == "campaigns":
        # Creating a campaign for another section does not keep it on your list.
        return model.owner_id == scope.user_id
    if name == "conversations":
        from app.models import ConversationParticipant

        return model.id.in_(
            select(ConversationParticipant.conversation_id).where(
                ConversationParticipant.user_id == scope.user_id
            )
        )
    return None


async def row_is_visible(db, model, row_id, organization_id, scope: DataScopeContext | None) -> bool:
    clause = scope_clause(model, scope)
    query = select(model.id).where(model.id == row_id)
    if "organization_id" in model.__table__.columns:
        query = query.where(model.organization_id == organization_id)
    if clause is not None:
        query = query.where(clause)
    return (await db.scalar(query)) is not None


def _match_nullable(model, cols: set[str], name: str, value: UUID | None, scope: DataScopeContext):
    if name not in cols:
        if name == "branch_id" and "work_item_id" in cols:
            from app.models import WorkItem

            branch_ok = (
                or_(WorkItem.branch_id == value, WorkItem.branch_id.is_(None))
                if value
                else WorkItem.branch_id.is_(None)
            )
            return or_(
                model.work_item_id.is_(None),
                model.work_item_id.in_(select(WorkItem.id).where(branch_ok)),
            )
        return None
    col = getattr(model, name)
    if value is None:
        return col.is_(None)
    return or_(col == value, col.is_(None))


def _self_clause(model, cols: set[str], scope: DataScopeContext):
    clauses = []
    if model.__tablename__ == "users":
        clauses.append(model.id == scope.user_id)
    if model.__tablename__ == "conversations":
        from app.models import ConversationParticipant

        clauses.append(
            model.id.in_(
                select(ConversationParticipant.conversation_id).where(
                    ConversationParticipant.user_id == scope.user_id
                )
            )
        )
    if "owner_id" in cols:
        clauses.append(model.owner_id == scope.user_id)
    if "created_by" in cols:
        clauses.append(model.created_by == scope.user_id)
    if not clauses:
        return false()
    return or_(*clauses) if len(clauses) > 1 else clauses[0]
