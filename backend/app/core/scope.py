"""Central data-scope filter.

Levels: organization, branch, department, team, self.
Rows with a null scope column stay visible at that level so unassigned
records are not hidden from the people who created them. Org admins and
organization-level roles see the whole tenant.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import false, or_, select
from sqlalchemy.sql import Select


@dataclass
class DataScopeContext:
    level: str
    user_id: UUID
    branch_id: UUID | None
    department_id: UUID | None
    team_id: UUID | None
    is_org_wide: bool


def apply_scope(stmt: Select, model, scope: DataScopeContext | None) -> Select:
    clause = scope_clause(model, scope)
    if clause is None:
        return stmt
    return stmt.where(clause)


def scope_clause(model, scope: DataScopeContext | None):
    if scope is None or scope.is_org_wide or scope.level == "organization":
        return None

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
    if level == "team":
        return _match_nullable(model, cols, "team_id", scope.team_id, scope)
    if level == "self":
        return _self_clause(model, cols, scope)
    return None


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
