from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.permissions import PermissionCode
from app.core.scope import DataScopeContext, apply_scope
from app.core.security import hash_password, validate_password, verify_password
from app.models import (
    Branch,
    DataScope,
    Department,
    Organization,
    OrgRelationship,
    Permission,
    Role,
    RolePermission,
    Team,
    User,
)
from app.models.enums import RelationshipType
from app.services.audit import emit_event


async def get_user_permissions(db: AsyncSession, user: User) -> set[str]:
    if not user.role_id:
        return set()
    result = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == user.role_id)
    )
    return set(result.scalars().all())


class OrgService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_organization(self, name: str, slug: str) -> Organization:
        org = Organization(name=name, slug=slug)
        self.db.add(org)
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=org.id,
            event_type="organization.created",
            entity_type="organization",
            entity_id=org.id,
            payload={"name": name, "slug": slug},
        )
        return org

    async def create_branch(
        self, organization_id: UUID, name: str, code: str, city: str | None = None
    ) -> Branch:
        branch = Branch(organization_id=organization_id, name=name, code=code, city=city)
        self.db.add(branch)
        await self.db.flush()
        return branch

    async def create_department(self, organization_id: UUID, name: str, code: str) -> Department:
        dept = Department(organization_id=organization_id, name=name, code=code)
        self.db.add(dept)
        await self.db.flush()
        return dept

    async def create_team(
        self,
        organization_id: UUID,
        name: str,
        code: str,
        department_id: UUID | None = None,
    ) -> Team:
        team = Team(
            organization_id=organization_id,
            name=name,
            code=code,
            department_id=department_id,
        )
        self.db.add(team)
        await self.db.flush()
        return team

    async def ensure_permissions(self) -> None:
        for code in PermissionCode:
            existing = await self.db.scalar(select(Permission).where(Permission.code == code.value))
            if not existing:
                self.db.add(Permission(code=code.value, description=code.value))
        await self.db.flush()

    async def grant_role_permissions(self, role_id: UUID, permission_codes: list[str]) -> None:
        """Add any missing permissions to an existing role (idempotent)."""
        await self.ensure_permissions()
        for pcode in permission_codes:
            code = pcode.value if hasattr(pcode, "value") else str(pcode)
            perm = await self.db.scalar(select(Permission).where(Permission.code == code))
            if not perm:
                continue
            exists = await self.db.scalar(
                select(RolePermission).where(
                    RolePermission.role_id == role_id,
                    RolePermission.permission_id == perm.id,
                )
            )
            if not exists:
                self.db.add(RolePermission(role_id=role_id, permission_id=perm.id))
        await self.db.flush()

    async def create_role(
        self,
        organization_id: UUID,
        name: str,
        code: str,
        permission_codes: list[str],
        data_scope_level: str = "organization",
    ) -> Role:
        await self.ensure_permissions()
        role = Role(organization_id=organization_id, name=name, code=code)
        self.db.add(role)
        await self.db.flush()
        for pcode in permission_codes:
            perm = await self.db.scalar(select(Permission).where(Permission.code == pcode))
            if perm:
                self.db.add(RolePermission(role_id=role.id, permission_id=perm.id))
        self.db.add(DataScope(role_id=role.id, level=data_scope_level))
        await self.db.flush()
        return role

    async def create_user(
        self,
        *,
        organization_id: UUID,
        email: str,
        full_name: str,
        password: str,
        role_id: UUID | None = None,
        branch_id: UUID | None = None,
        department_id: UUID | None = None,
        team_id: UUID | None = None,
        manager_id: UUID | None = None,
    ) -> User:
        problem = validate_password(password)
        if problem:
            raise ValueError(problem)
        user = User(
            organization_id=organization_id,
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            role_id=role_id,
            branch_id=branch_id,
            department_id=department_id,
            team_id=team_id,
            manager_id=manager_id,
        )
        self.db.add(user)
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=organization_id,
            event_type="user.created",
            entity_type="user",
            entity_id=user.id,
            payload={"email": email, "full_name": full_name},
        )
        return user

    async def authenticate(self, organization_id: UUID, email: str, password: str) -> User | None:
        user = await self.db.scalar(
            select(User).where(User.organization_id == organization_id, User.email == email)
        )
        if not user or not verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            # Deactivated accounts keep their row (and their history) but
            # cannot sign in again.
            return None
        return user

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.db.get(User, user_id)

    async def add_relationship(
        self,
        organization_id: UUID,
        from_user_id: UUID,
        to_user_id: UUID,
        relationship_type: RelationshipType,
        actor_id: UUID | None = None,
    ) -> OrgRelationship:
        rel = OrgRelationship(
            organization_id=organization_id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            relationship_type=relationship_type,
        )
        self.db.add(rel)
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=organization_id,
            event_type="relationship.created",
            actor_id=actor_id,
            entity_type="relationship",
            entity_id=rel.id,
            payload={
                "from_user_id": str(from_user_id),
                "to_user_id": str(to_user_id),
                "type": relationship_type.value,
            },
        )
        return rel

    async def list_relationships(self, user_id: UUID, *, organization_id: UUID) -> list[OrgRelationship]:
        result = await self.db.execute(
            select(OrgRelationship).where(
                OrgRelationship.organization_id == organization_id,
                (OrgRelationship.from_user_id == user_id) | (OrgRelationship.to_user_id == user_id),
            )
        )
        return list(result.scalars().all())

    async def who_manages(self, user_id: UUID, *, organization_id: UUID) -> list[User]:
        result = await self.db.execute(
            select(User)
            .join(OrgRelationship, OrgRelationship.from_user_id == User.id)
            .where(
                User.organization_id == organization_id,
                OrgRelationship.to_user_id == user_id,
                OrgRelationship.relationship_type == RelationshipType.MANAGES,
            )
        )
        return list(result.scalars().all())

    async def team_members(self, team_id: UUID, *, organization_id: UUID) -> list[User]:
        team = await self.db.get(Team, team_id)
        if not team or team.organization_id != organization_id:
            raise ValueError("Team not found")
        result = await self.db.execute(
            select(User).where(User.team_id == team_id, User.organization_id == organization_id)
        )
        return list(result.scalars().all())

    async def eligible_assignees(
        self,
        organization_id: UUID,
        *,
        team_id: UUID | None = None,
        branch_id: UUID | None = None,
        department_id: UUID | None = None,
    ) -> list[User]:
        q = select(User).where(User.organization_id == organization_id, User.is_active.is_(True))
        if team_id:
            q = q.where(User.team_id == team_id)
        if branch_id:
            q = q.where(User.branch_id == branch_id)
        if department_id:
            q = q.where(User.department_id == department_id)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def list_people(
        self,
        organization_id: UUID,
        *,
        q: str | None = None,
        scope: DataScopeContext | None = None,
    ) -> list[User]:
        stmt = (
            select(User)
            .options(selectinload(User.role))
            .where(User.organization_id == organization_id, User.is_active.is_(True))
            .order_by(User.full_name)
        )
        stmt = apply_scope(stmt, User, scope)
        if q:
            like = f"%{q}%"
            stmt = stmt.where((User.full_name.ilike(like)) | (User.email.ilike(like)))
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_branches(self, organization_id: UUID) -> list[Branch]:
        result = await self.db.execute(
            select(Branch)
            .where(Branch.organization_id == organization_id)
            .order_by(Branch.name)
        )
        return list(result.scalars().all())

    async def list_departments(self, organization_id: UUID) -> list[Department]:
        result = await self.db.execute(
            select(Department)
            .where(Department.organization_id == organization_id)
            .order_by(Department.name)
        )
        return list(result.scalars().all())

    async def list_teams(self, organization_id: UUID) -> list[Team]:
        result = await self.db.execute(
            select(Team).where(Team.organization_id == organization_id).order_by(Team.name)
        )
        return list(result.scalars().all())

    async def who_reports_to(self, manager_id: UUID, *, organization_id: UUID) -> list[User]:
        result = await self.db.execute(
            select(User)
            .join(OrgRelationship, OrgRelationship.to_user_id == User.id)
            .where(
                User.organization_id == organization_id,
                OrgRelationship.from_user_id == manager_id,
                OrgRelationship.relationship_type == RelationshipType.MANAGES,
            )
        )
        return list(result.scalars().all())

    async def list_org_relationships(self, organization_id: UUID) -> list[OrgRelationship]:
        result = await self.db.execute(
            select(OrgRelationship)
            .where(OrgRelationship.organization_id == organization_id)
            .order_by(OrgRelationship.created_at.desc())
        )
        return list(result.scalars().all())
