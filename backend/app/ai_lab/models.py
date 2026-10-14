"""AI Lab task queue — no writes to core CM or Mizito tables."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class AiTask(Base):
    __tablename__ = "ai_tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    result_json: Mapped[str | None] = mapped_column(Text)
    raw_result: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    rating: Mapped[int | None] = mapped_column(Integer)
    useful: Mapped[bool | None] = mapped_column(Boolean)
    eval_note: Mapped[str | None] = mapped_column(Text)
    decisions_json: Mapped[str] = mapped_column(Text, default="{}")
