from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import AuthorizationError, PermissionCode
from app.core.scope import DataScopeContext
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import DataScope, Organization, User
from app.services import get_user_permissions

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


@dataclass
class AuthContext:
    user: User
    permissions: set[str]
    organization_id: UUID
    scope: DataScopeContext


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_access_token(token)
        user_id = UUID(payload["sub"])
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    perms = await get_user_permissions(db, user)
    scope = await load_data_scope(db, user, perms)
    return AuthContext(
        user=user, permissions=perms, organization_id=user.organization_id, scope=scope
    )


_SCOPE_RANK = {"organization": 0, "branch": 1, "department": 2, "team": 3, "self": 4}


async def load_data_scope(db: AsyncSession, user: User, permissions: set[str]) -> DataScopeContext:
    level = "organization"
    if PermissionCode.ORG_ADMIN not in permissions and user.role_id:
        rows = list(
            (
                await db.execute(select(DataScope).where(DataScope.role_id == user.role_id))
            ).scalars()
        )
        if rows:
            level = min(rows, key=lambda r: _SCOPE_RANK.get(r.level, 9)).level
    return DataScopeContext(
        level=level,
        user_id=user.id,
        branch_id=user.branch_id,
        department_id=user.department_id,
        team_id=user.team_id,
        is_org_wide=level == "organization" or PermissionCode.ORG_ADMIN in permissions,
    )


def handle_authz(exc: AuthorizationError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.message)


async def get_org_by_slug(db: AsyncSession, slug: str) -> Organization:
    org = await db.scalar(select(Organization).where(Organization.slug == slug))
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org
