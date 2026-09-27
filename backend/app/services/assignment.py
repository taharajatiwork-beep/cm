"""Deterministic assignment engine.

AI may recommend; business rules decide auto-assign.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.permissions import PermissionCode, require_permission
from app.models import Task, TaskAssignee, User, UserSkill
from app.models.enums import TaskStatus


@dataclass
class AssignmentCandidate:
    user_id: UUID
    full_name: str
    email: str
    role_code: str | None
    branch_id: UUID | None
    team_id: UUID | None
    department_id: UUID | None
    open_tasks: int
    skills: list[str]
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class AssignmentRecommendation:
    candidates: list[AssignmentCandidate]
    recommended_user_id: UUID | None
    auto_assign_allowed: bool
    filters_applied: dict[str, Any]


class AssignmentEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def recommend(
        self,
        *,
        organization_id: UUID,
        actor_permissions: set[str],
        role_code: str | None = None,
        branch_id: UUID | None = None,
        department_id: UUID | None = None,
        team_id: UUID | None = None,
        required_skills: list[str] | None = None,
        require_available: bool = True,
        related_user_id: UUID | None = None,
        limit: int = 10,
    ) -> AssignmentRecommendation:
        require_permission(actor_permissions, PermissionCode.TASK_ASSIGN)

        q = (
            select(User)
            .options(selectinload(User.role), selectinload(User.skills))
            .where(
                User.organization_id == organization_id,
                User.is_active.is_(True),
            )
        )
        if require_available:
            q = q.where(User.is_available.is_(True))
        if branch_id:
            q = q.where(User.branch_id == branch_id)
        if department_id:
            q = q.where(User.department_id == department_id)
        if team_id:
            q = q.where(User.team_id == team_id)

        users = list((await self.db.execute(q)).scalars().all())

        # Role filter
        if role_code:
            filtered = []
            for u in users:
                if u.role and u.role.code == role_code:
                    filtered.append(u)
            users = filtered

        collaborator_ids: set[UUID] = set()
        if related_user_id:
            from app.models import OrgRelationship
            from app.models.enums import RelationshipType

            rels = await self.db.execute(
                select(OrgRelationship).where(
                    (
                        (OrgRelationship.from_user_id == related_user_id)
                        & (
                            OrgRelationship.relationship_type.in_(
                                [
                                    RelationshipType.COLLABORATES_WITH,
                                    RelationshipType.WORKS_WITH,
                                    RelationshipType.MANAGES,
                                ]
                            )
                        )
                    )
                    | (
                        (OrgRelationship.to_user_id == related_user_id)
                        & (
                            OrgRelationship.relationship_type.in_(
                                [
                                    RelationshipType.COLLABORATES_WITH,
                                    RelationshipType.WORKS_WITH,
                                    RelationshipType.REPORTS_TO,
                                ]
                            )
                        )
                    )
                )
            )
            for rel in rels.scalars().all():
                collaborator_ids.add(rel.from_user_id)
                collaborator_ids.add(rel.to_user_id)
            collaborator_ids.discard(related_user_id)

        required_skills = [s.lower() for s in (required_skills or [])]
        candidates: list[AssignmentCandidate] = []
        for u in users:
            skill_codes = [s.skill_code.lower() for s in u.skills]
            if required_skills and not all(s in skill_codes for s in required_skills):
                continue

            open_tasks = await self._open_task_count(u.id)
            score = 100.0
            reasons: list[str] = ["active"]
            if require_available and u.is_available:
                reasons.append("available")
                score += 5
            if branch_id and u.branch_id == branch_id:
                reasons.append("branch_match")
                score += 15
            if team_id and u.team_id == team_id:
                reasons.append("team_match")
                score += 20
            if department_id and u.department_id == department_id:
                reasons.append("department_match")
                score += 10
            if role_code and u.role and u.role.code == role_code:
                reasons.append(f"role:{role_code}")
                score += 15
            if u.id in collaborator_ids:
                reasons.append("org_relationship")
                score += 12
            for sk in required_skills:
                if sk in skill_codes:
                    reasons.append(f"skill:{sk}")
                    score += 10
            # Lower workload is better
            score -= open_tasks * 5
            reasons.append(f"workload:{open_tasks}")

            candidates.append(
                AssignmentCandidate(
                    user_id=u.id,
                    full_name=u.full_name,
                    email=u.email,
                    role_code=u.role.code if u.role else None,
                    branch_id=u.branch_id,
                    team_id=u.team_id,
                    department_id=u.department_id,
                    open_tasks=open_tasks,
                    skills=skill_codes,
                    score=score,
                    reasons=reasons,
                )
            )

        candidates.sort(key=lambda c: (-c.score, c.open_tasks, c.full_name))
        candidates = candidates[: max(1, min(limit, 50))]

        settings = get_settings()
        auto_allowed = bool(settings.assignment_auto_assign_enabled)

        return AssignmentRecommendation(
            candidates=candidates,
            recommended_user_id=candidates[0].user_id if candidates else None,
            auto_assign_allowed=auto_allowed and bool(candidates),
            filters_applied={
                "role_code": role_code,
                "branch_id": str(branch_id) if branch_id else None,
                "department_id": str(department_id) if department_id else None,
                "team_id": str(team_id) if team_id else None,
                "required_skills": required_skills,
                "require_available": require_available,
                "related_user_id": str(related_user_id) if related_user_id else None,
            },
        )

    async def _open_task_count(self, user_id: UUID) -> int:
        count = await self.db.scalar(
            select(func.count())
            .select_from(Task)
            .join(TaskAssignee, TaskAssignee.task_id == Task.id)
            .where(
                TaskAssignee.user_id == user_id,
                Task.status.in_(
                    [TaskStatus.OPEN, TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED]
                ),
            )
        )
        return int(count or 0)

    async def add_skill(self, user_id: UUID, skill_code: str, level: int = 1) -> UserSkill:
        existing = await self.db.scalar(
            select(UserSkill).where(
                UserSkill.user_id == user_id,
                UserSkill.skill_code == skill_code.lower(),
            )
        )
        if existing:
            existing.level = level
            await self.db.flush()
            return existing
        row = UserSkill(user_id=user_id, skill_code=skill_code.lower(), level=level)
        self.db.add(row)
        await self.db.flush()
        return row
