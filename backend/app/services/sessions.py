"""Refresh sessions, login lockout, and a small in-process rate limit."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ratelimit import allow_hit
from app.core.security import create_access_token, hash_refresh_token, new_refresh_token
from app.models import User
from app.models.enterprise import RefreshToken
from app.services import write_audit


def login_allowed(host: str, email: str, limit: int = 1000, window: int = 60) -> bool:
    """آیا این تلاش ورود مجاز است؟

    شمارنده در Redis نگه داشته می‌شود تا بین replicaهای API مشترک باشد؛
    اگر Redis نباشد به شمارندهٔ حافظه‌ای برمی‌گردد.
    """
    key = f"{host}:{email.lower()}"
    return allow_hit(key, limit=limit, window=window)


async def record_login_failure(db: AsyncSession, organization_id: UUID, email: str) -> None:
    settings = get_settings()
    user = await db.scalar(select(User).where(User.organization_id == organization_id, User.email == email))
    if not user:
        return
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= settings.login_max_failures:
        user.locked_until = datetime.now(UTC) + timedelta(minutes=settings.login_lock_minutes)
    await write_audit(
        db,
        organization_id=organization_id,
        actor_id=user.id,
        action="auth.login_failed",
        entity_type="user",
        entity_id=user.id,
    )
    await db.flush()


async def record_login_success(db: AsyncSession, user: User) -> None:
    user.failed_login_count = 0
    user.locked_until = None
    await write_audit(
        db,
        organization_id=user.organization_id,
        actor_id=user.id,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
    )
    await db.flush()


async def issue_session(db: AsyncSession, user: User) -> tuple[str, str]:
    settings = get_settings()
    access = create_access_token(user.id, extra={"org_id": str(user.organization_id)})
    raw = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            organization_id=user.organization_id,
            token_hash=hash_refresh_token(raw),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await db.flush()
    return access, raw


async def rotate_refresh(
    db: AsyncSession, raw: str, *, revoke_only: bool = False
) -> tuple[str, str] | None:
    now = datetime.now(UTC)
    row = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw)))
    if not row or row.revoked_at is not None:
        return None
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if expires < now:
        return None
    row.revoked_at = now
    user = await db.get(User, row.user_id)
    if not user or not user.is_active:
        return None
    await write_audit(
        db,
        organization_id=user.organization_id,
        actor_id=user.id,
        action="auth.logout" if revoke_only else "auth.refresh",
        entity_type="user",
        entity_id=user.id,
    )
    if revoke_only:
        await db.flush()
        return None
    return await issue_session(db, user)


async def revoke_all(db: AsyncSession, user_id: UUID) -> None:
    now = datetime.now(UTC)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    user = await db.get(User, user_id)
    if user:
        await write_audit(
            db,
            organization_id=user.organization_id,
            actor_id=user.id,
            action="auth.logout_all",
            entity_type="user",
            entity_id=user.id,
        )
    await db.flush()
