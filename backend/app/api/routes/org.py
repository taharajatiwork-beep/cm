from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_org_by_slug
from app.core.permissions import (
    PermissionCode,
    admin_role_permission_codes,
    require_any_permission,
    require_permission,
)
from app.core.security import create_access_token
from app.db.session import get_db
from app.schemas import (
    BootstrapIn,
    BranchCreate,
    BranchOut,
    DepartmentCreate,
    DepartmentOut,
    LoginIn,
    MeOut,
    OrganizationOut,
    RelationshipCreate,
    RelationshipOut,
    TeamCreate,
    TeamOut,
    TokenOut,
    UserCreate,
    UserOut,
)
from app.services import OrgService
from app.services.sessions import (
    issue_session,
    login_allowed,
    record_login_failure,
    record_login_success,
    revoke_all,
    rotate_refresh,
)

router = APIRouter(tags=["auth-org"])


@router.post("/auth/bootstrap", response_model=TokenOut)
async def bootstrap(body: BootstrapIn, db: AsyncSession = Depends(get_db)):
    """Dev helper: create org + admin role with all permissions + admin user."""
    from app.models import Organization

    svc = OrgService(db)
    existing = await db.scalar(select(Organization).where(Organization.slug == body.organization_slug))
    if existing:
        raise HTTPException(400, "Organization slug already exists")
    org = await svc.create_organization(body.organization_name, body.organization_slug)
    role = await svc.create_role(
        org.id,
        name="Admin",
        code="admin",
        permission_codes=admin_role_permission_codes(),
        data_scope_level="organization",
    )
    # Manager / Seller / Marketing roles for demos
    await svc.create_role(
        org.id,
        name="Manager",
        code="manager",
        permission_codes=[
            PermissionCode.USER_READ,
            PermissionCode.RELATIONSHIP_WRITE,
            PermissionCode.CONVERSATION_READ,
            PermissionCode.CONVERSATION_WRITE,
            PermissionCode.WORK_ITEM_READ,
            PermissionCode.WORK_ITEM_WRITE,
            PermissionCode.CASE_READ,
            PermissionCode.CASE_WRITE,
            PermissionCode.TASK_READ,
            PermissionCode.TASK_WRITE,
            PermissionCode.TASK_ASSIGN,
            PermissionCode.TASK_DELEGATE,
            PermissionCode.NOTIFICATION_READ,
            PermissionCode.EVENT_READ,
            PermissionCode.SLA_MANAGE,
            PermissionCode.INVENTORY_READ,
            PermissionCode.INVENTORY_WRITE,
            PermissionCode.SEARCH,
            PermissionCode.RAG_READ,
            PermissionCode.RAG_INDEX,
            PermissionCode.AGENT_RUN,
            PermissionCode.KB_READ,
            PermissionCode.KB_WRITE,
            PermissionCode.CUSTOMER_READ,
            PermissionCode.CUSTOMER_WRITE,
            PermissionCode.CAMPAIGN_READ,
            PermissionCode.CAMPAIGN_WRITE,
        ],
        data_scope_level="branch",
    )
    await svc.create_role(
        org.id,
        name="Seller",
        code="seller",
        permission_codes=[
            PermissionCode.CONVERSATION_READ,
            PermissionCode.CONVERSATION_WRITE,
            PermissionCode.WORK_ITEM_READ,
            PermissionCode.CASE_READ,
            PermissionCode.TASK_READ,
            PermissionCode.TASK_WRITE,
            PermissionCode.NOTIFICATION_READ,
            PermissionCode.INVENTORY_READ,
            PermissionCode.SEARCH,
            PermissionCode.RAG_READ,
            PermissionCode.KB_READ,
            PermissionCode.CUSTOMER_READ,
            PermissionCode.CAMPAIGN_READ,
        ],
        data_scope_level="team",
    )
    await svc.create_role(
        org.id,
        name="Marketing",
        code="marketing",
        permission_codes=[
            PermissionCode.CONVERSATION_READ,
            PermissionCode.CONVERSATION_WRITE,
            PermissionCode.WORK_ITEM_READ,
            PermissionCode.CASE_READ,
            PermissionCode.TASK_READ,
            PermissionCode.TASK_WRITE,
            PermissionCode.NOTIFICATION_READ,
            PermissionCode.INVENTORY_READ,
            PermissionCode.SEARCH,
            PermissionCode.RAG_READ,
            PermissionCode.KB_READ,
            PermissionCode.CAMPAIGN_READ,
            PermissionCode.CAMPAIGN_WRITE,
        ],
        data_scope_level="team",
    )
    admin = await svc.create_user(
        organization_id=org.id,
        email=body.admin_email,
        full_name=body.admin_name,
        password=body.admin_password,
        role_id=role.id,
    )
    token = create_access_token(admin.id, extra={"org_id": str(org.id)})
    return TokenOut(access_token=token)


@router.post("/auth/login", response_model=TokenOut)
async def login(body: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    if not login_allowed(request.client.host if request.client else "unknown", body.email):
        raise HTTPException(429, "Too many login attempts")
    org = await get_org_by_slug(db, body.organization_slug)
    svc = OrgService(db)
    user = await svc.authenticate(org.id, body.email, body.password)
    if not user:
        await record_login_failure(db, org.id, body.email)
        raise HTTPException(401, "Invalid credentials")
    if user.locked_until is not None:
        from datetime import UTC, datetime

        locked = user.locked_until if user.locked_until.tzinfo else user.locked_until.replace(tzinfo=UTC)
        if locked > datetime.now(UTC):
            raise HTTPException(423, "Account locked")
    if user.totp_enabled:
        from app.core.security import verify_totp

        code = request.headers.get("x-totp-code", "")
        if not verify_totp(user.totp_secret or "", code):
            raise HTTPException(401, "Invalid authenticator code")
    await record_login_success(db, user)
    access, refresh = await issue_session(db, user)
    _set_refresh_cookie(response, refresh)
    return TokenOut(access_token=access)


class TotpEnableIn(BaseModel):
    code: str


@router.post("/auth/totp/setup")
async def totp_setup(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.core.security import new_totp_secret

    secret = new_totp_secret()
    ctx.user.totp_secret = secret
    ctx.user.totp_enabled = False
    otpauth = f"otpauth://totp/CM:{ctx.user.email}?secret={secret}&issuer=CM"
    return {"secret": secret, "otpauth": otpauth, "enabled": False}


@router.post("/auth/totp/enable")
async def totp_enable(
    body: TotpEnableIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.core.security import verify_totp

    if not ctx.user.totp_secret or not verify_totp(ctx.user.totp_secret, body.code):
        raise HTTPException(400, "Invalid authenticator code")
    ctx.user.totp_enabled = True
    return {"enabled": True}


def _set_refresh_cookie(response: Response, refresh: str) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    response.set_cookie(
        "cm_refresh",
        refresh,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/",
    )


@router.post("/auth/refresh", response_model=TokenOut)
async def refresh_session(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw = request.cookies.get("cm_refresh")
    if not raw:
        raise HTTPException(401, "No refresh cookie")
    pair = await rotate_refresh(db, raw)
    if not pair:
        raise HTTPException(401, "Refresh token revoked")
    access, refresh = pair
    _set_refresh_cookie(response, refresh)
    return TokenOut(access_token=access)


@router.post("/auth/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw = request.cookies.get("cm_refresh")
    if raw:
        await rotate_refresh(db, raw, revoke_only=True)
    response.delete_cookie("cm_refresh", path="/")
    return {"ok": True}


@router.post("/auth/logout-all")
async def logout_all(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await revoke_all(db, ctx.user.id)
    return {"ok": True}


@router.get("/auth/me", response_model=MeOut)
async def me(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models import Branch, Role, Team

    base = UserOut.model_validate(ctx.user)
    branch_name = None
    if ctx.user.branch_id:
        branch = await db.get(Branch, ctx.user.branch_id)
        branch_name = branch.name if branch else None
    team_home_team_id = ctx.user.team_id
    if ctx.user.team_id:
        team = await db.get(Team, ctx.user.team_id)
        if team and team.parent_team_id:
            team_home_team_id = team.parent_team_id
    role_code: str | None = None
    role_name: str | None = None
    if ctx.user.role_id:
        role = await db.get(Role, ctx.user.role_id)
        if role:
            role_code = role.code
            role_name = role.name
    return MeOut(
        **base.model_dump(),
        permissions=sorted(ctx.permissions),
        role_code=role_code,
        role_name=role_name,
        branch_name=branch_name,
        team_home_team_id=team_home_team_id,
    )


@router.get("/org", response_model=OrganizationOut)
async def get_org(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models import Organization

    org = await db.get(Organization, ctx.organization_id)
    return org


@router.post("/org/branches", response_model=BranchOut)
async def create_branch(
    body: BranchCreate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_permission(ctx.permissions, PermissionCode.ORG_ADMIN)
    return await OrgService(db).create_branch(ctx.organization_id, body.name, body.code, body.city)


@router.post("/org/departments", response_model=DepartmentOut)
async def create_department(
    body: DepartmentCreate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_permission(ctx.permissions, PermissionCode.ORG_ADMIN)
    return await OrgService(db).create_department(ctx.organization_id, body.name, body.code)


@router.post("/org/teams", response_model=TeamOut)
async def create_team(
    body: TeamCreate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_permission(ctx.permissions, PermissionCode.ORG_ADMIN)
    return await OrgService(db).create_team(
        ctx.organization_id, body.name, body.code, body.department_id
    )


@router.post("/org/users", response_model=UserOut)
async def create_user(
    body: UserCreate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_permission(ctx.permissions, PermissionCode.USER_WRITE)
    try:
        return await OrgService(db).create_user(
            organization_id=ctx.organization_id,
            email=body.email,
            full_name=body.full_name,
            password=body.password,
            role_id=body.role_id,
            branch_id=body.branch_id,
            department_id=body.department_id,
            team_id=body.team_id,
            manager_id=body.manager_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/org/permissions")
async def list_permission_codes(ctx: AuthContext = Depends(get_current_user)):
    """Every permission code the system knows, for the role editor UI."""
    require_permission(ctx.permissions, PermissionCode.ORG_ADMIN)
    return sorted(p.value for p in PermissionCode)


@router.get("/org/roles")
async def list_roles(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models import Role

    result = await db.execute(select(Role).where(Role.organization_id == ctx.organization_id))
    roles = result.scalars().all()
    return [{"id": r.id, "name": r.name, "code": r.code} for r in roles]


@router.post("/org/relationships", response_model=RelationshipOut)
async def create_relationship(
    body: RelationshipCreate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_permission(ctx.permissions, PermissionCode.RELATIONSHIP_WRITE)
    return await OrgService(db).add_relationship(
        ctx.organization_id,
        body.from_user_id,
        body.to_user_id,
        body.relationship_type,
        actor_id=ctx.user.id,
    )


@router.get("/org/users/{user_id}/relationships", response_model=list[RelationshipOut])
async def list_user_relationships(
    user_id: str,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    return await OrgService(db).list_relationships(UUID(user_id), organization_id=ctx.organization_id)


@router.get("/org/users/{user_id}/managers", response_model=list[UserOut])
async def list_managers(
    user_id: str,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    return await OrgService(db).who_manages(UUID(user_id), organization_id=ctx.organization_id)


@router.get("/org/teams/{team_id}/members", response_model=list[UserOut])
async def list_team_members(
    team_id: str,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    try:
        return await OrgService(db).team_members(UUID(team_id), organization_id=ctx.organization_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/org/eligible-assignees", response_model=list[UserOut])
async def eligible_assignees(
    team_id: str | None = None,
    branch_id: str | None = None,
    department_id: str | None = None,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    return await OrgService(db).eligible_assignees(
        ctx.organization_id,
        team_id=UUID(team_id) if team_id else None,
        branch_id=UUID(branch_id) if branch_id else None,
        department_id=UUID(department_id) if department_id else None,
    )


@router.get("/people", response_model=list[UserOut])
async def list_people(
    q: str | None = None,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_any_permission(
        ctx.permissions, PermissionCode.USER_READ, PermissionCode.WORK_ITEM_READ
    )
    return await OrgService(db).list_people(ctx.organization_id, q=q, scope=ctx.scope)


@router.get("/people/{user_id}", response_model=UserOut)
async def get_person(
    user_id: str,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    require_any_permission(
        ctx.permissions, PermissionCode.USER_READ, PermissionCode.WORK_ITEM_READ
    )
    user = await OrgService(db).get_user(UUID(user_id))
    if not user or user.organization_id != ctx.organization_id:
        raise HTTPException(404, "User not found")
    return user


@router.get("/people/{user_id}/reports", response_model=list[UserOut])
async def list_direct_reports(
    user_id: str,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    require_any_permission(
        ctx.permissions, PermissionCode.USER_READ, PermissionCode.WORK_ITEM_READ
    )
    return await OrgService(db).who_reports_to(UUID(user_id), organization_id=ctx.organization_id)


@router.get("/branches", response_model=list[BranchOut])
async def list_branches(
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_any_permission(
        ctx.permissions, PermissionCode.USER_READ, PermissionCode.WORK_ITEM_READ
    )
    return await OrgService(db).list_branches(ctx.organization_id)


@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments(
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_any_permission(
        ctx.permissions, PermissionCode.USER_READ, PermissionCode.WORK_ITEM_READ
    )
    return await OrgService(db).list_departments(ctx.organization_id)


@router.get("/teams", response_model=list[TeamOut])
async def list_teams(
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_any_permission(
        ctx.permissions, PermissionCode.USER_READ, PermissionCode.WORK_ITEM_READ,
        PermissionCode.REQUEST_CREATE, PermissionCode.REQUEST_TRIAGE,
        PermissionCode.REQUEST_MANAGE,
    )
    return await OrgService(db).list_teams(ctx.organization_id)


@router.get("/relationships", response_model=list[RelationshipOut])
async def list_relationships(
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_any_permission(
        ctx.permissions, PermissionCode.USER_READ, PermissionCode.WORK_ITEM_READ
    )
    return await OrgService(db).list_org_relationships(ctx.organization_id)
