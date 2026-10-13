"""کمک‌های مشترک پرفورمنس."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import PermissionCode
from app.models import User
from app.services.org import get_user_permissions
from app.perf.models import PmCost
from app.services.notifications import notify


class PerfError(Exception):
    def __init__(
        self,
        message: str,
        status: int = 400,
        *,
        pishgam_status_code: int | None = None,
        pishgam_message: str | None = None,
    ):
        self.message = message
        self.status = status
        self.pishgam_status_code = pishgam_status_code
        self.pishgam_message = pishgam_message
        super().__init__(message)


def as_date(value: str | date | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def iso(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


async def users_with(db: AsyncSession, organization_id: UUID, code: str) -> list[User]:
    users = list(
        (
            await db.scalars(
                select(User).where(User.organization_id == organization_id, User.is_active.is_(True))
            )
        ).all()
    )
    found: list[User] = []
    for user in users:
        perms = await get_user_permissions(db, user)
        if code in perms or PermissionCode.ORG_ADMIN in perms:
            found.append(user)
    return found


async def tell(
    db: AsyncSession,
    *,
    organization_id: UUID,
    users: list[User],
    title: str,
    body: str,
    entity_id: UUID | None = None,
) -> None:
    for user in users:
        await notify(
            db,
            organization_id=organization_id,
            user_id=user.id,
            title=title,
            body=body,
            entity_type="pm_payment",
            entity_id=entity_id,
        )


async def next_cost_number(db: AsyncSession, organization_id: UUID) -> int:
    rows = list(
        (
            await db.scalars(select(PmCost.cost_number).where(PmCost.organization_id == organization_id))
        ).all()
    )
    return (max(rows) if rows else 0) + 1


def now() -> datetime:
    return datetime.now(UTC)
