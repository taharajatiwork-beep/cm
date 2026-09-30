from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, handle_authz
from app.core.permissions import AuthorizationError, PermissionCode, require_permission
from app.db.session import get_db
from app.services import WorkService
from app.services.assignment import AssignmentEngine

router = APIRouter(prefix="/assignment", tags=["assignment"])


class RecommendBody(BaseModel):
    role_code: str | None = None
    branch_id: UUID | None = None
    department_id: UUID | None = None
    team_id: UUID | None = None
    required_skills: list[str] = []
    require_available: bool = True
    related_user_id: UUID | None = None
    limit: int = 10


class CandidateOut(BaseModel):
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
    reasons: list[str]


class RecommendOut(BaseModel):
    recommended_user_id: UUID | None
    auto_assign_allowed: bool
    filters_applied: dict
    candidates: list[CandidateOut]


class ApplyBody(BaseModel):
    task_id: UUID
    user_id: UUID | None = None  # if omitted, use recommendation filters
    role_code: str | None = None
    branch_id: UUID | None = None
    team_id: UUID | None = None
    required_skills: list[str] = []


class SkillBody(BaseModel):
    skill_code: str = Field(min_length=1)
    level: int = 1


@router.post("/recommend", response_model=RecommendOut)
async def recommend(
    body: RecommendBody,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await AssignmentEngine(db).recommend(
            organization_id=ctx.organization_id,
            actor_permissions=ctx.permissions,
            role_code=body.role_code,
            branch_id=body.branch_id,
            department_id=body.department_id,
            team_id=body.team_id,
            required_skills=body.required_skills,
            require_available=body.require_available,
            related_user_id=body.related_user_id,
            limit=body.limit,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e

    return RecommendOut(
        recommended_user_id=result.recommended_user_id,
        auto_assign_allowed=result.auto_assign_allowed,
        filters_applied=result.filters_applied,
        candidates=[
            CandidateOut(
                user_id=c.user_id,
                full_name=c.full_name,
                email=c.email,
                role_code=c.role_code,
                branch_id=c.branch_id,
                team_id=c.team_id,
                department_id=c.department_id,
                open_tasks=c.open_tasks,
                skills=c.skills,
                score=c.score,
                reasons=c.reasons,
            )
            for c in result.candidates
        ],
    )


@router.post("/apply")
async def apply_assignment(
    body: ApplyBody,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign task to a user. Auto-pick only when ASSIGNMENT_AUTO_ASSIGN_ENABLED=true."""
    engine = AssignmentEngine(db)
    try:
        require_permission(ctx.permissions, PermissionCode.TASK_ASSIGN)
        user_id = body.user_id
        if user_id is None:
            rec = await engine.recommend(
                organization_id=ctx.organization_id,
                actor_permissions=ctx.permissions,
                role_code=body.role_code,
                branch_id=body.branch_id,
                team_id=body.team_id,
                required_skills=body.required_skills,
            )
            if not rec.auto_assign_allowed:
                raise HTTPException(
                    400,
                    "Auto-assign disabled by business rule. Pass user_id explicitly.",
                )
            if not rec.recommended_user_id:
                raise HTTPException(404, "No eligible assignee")
            user_id = rec.recommended_user_id

        task = await WorkService(db).delegate_task(
            task_id=body.task_id,
            actor_id=ctx.user.id,
            actor_permissions=ctx.permissions,
            to_user_id=user_id,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    except ValueError as e:
        raise HTTPException(404, str(e)) from e

    return {"task_id": task.id, "assigned_user_id": user_id, "status": task.status.value}


@router.post("/users/{user_id}/skills")
async def add_skill(
    user_id: UUID,
    body: SkillBody,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.USER_WRITE)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    row = await AssignmentEngine(db).add_skill(user_id, body.skill_code, body.level)
    return {"user_id": user_id, "skill_code": row.skill_code, "level": row.level}
