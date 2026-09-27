from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class AiActionLog(Base):
    """Audit trail for agent/tool actions. Append-oriented."""

    __tablename__ = "ai_action_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    acting_for: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    agent: Mapped[str] = mapped_column(String(100), nullable=False)
    tool: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_entity: Mapped[str | None] = mapped_column(String(100))
    input_json: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text)
    approval: Mapped[str] = mapped_column(String(50), default="auto")  # auto | required | denied
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
