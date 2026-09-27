"""Telegram / Bale account mapping and edge tables.

Telegram is never the source of truth — these tables only map identities,
dedupe updates, queue outbound messages, and hold short-lived confirmations.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class TelegramAccount(Base):
    """Maps a Telegram/Bale user to an internal User."""

    __tablename__ = "telegram_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_telegram_user_provider"),
        UniqueConstraint("provider", "telegram_user_id", name="uq_telegram_provider_tg_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), default="telegram", nullable=False)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    telegram_username: Mapped[str | None] = mapped_column(String(100))
    link_code: Mapped[str | None] = mapped_column(String(32), unique=True)
    link_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # JSON: {"task_assigned": true, "message": true, "sla": true, "task_done": true, "branch": true}
    notify_prefs: Mapped[str | None] = mapped_column(Text)
    quiet_start_hour: Mapped[int | None] = mapped_column(Integer)  # 0-23, inclusive
    quiet_end_hour: Mapped[int | None] = mapped_column(Integer)
    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TelegramProcessedUpdate(Base):
    """Deduplicates webhook/poll updates by (provider, update_id)."""

    __tablename__ = "telegram_processed_updates"
    __table_args__ = (UniqueConstraint("provider", "update_id", name="uq_tg_processed_update"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(20), default="telegram", nullable=False)
    update_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TelegramOutbox(Base):
    """Outbound notification queue — written in the same transaction as business events."""

    __tablename__ = "telegram_outbox"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), default="telegram", nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON list of {text, callback_data} or {text, url}
    buttons_json: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # conversation_id when the outbox message is a chat notification (for reply routing)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TelegramPendingConfirm(Base):
    """Short-lived draft for "create project?" confirmation buttons."""

    __tablename__ = "telegram_pending_confirms"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), default="telegram", nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # create_work
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
