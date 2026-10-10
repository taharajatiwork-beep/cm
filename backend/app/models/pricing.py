"""قیمت تأییدشده برای یک ساعت پست. جدا از تأییدهای عمومی سازمان."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class PostSlot(Base):
    __tablename__ = "post_slots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    post_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    slot_type: Mapped[str] = mapped_column(String(40), default="video")  # video | post | story | price_change
    channel: Mapped[str | None] = mapped_column(String(40))
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    # requested | confirmed | needs_recheck | posted | cancelled
    status: Mapped[str] = mapped_column(String(30), default="requested", nullable=False)
    confirmed_price: Mapped[int | None] = mapped_column(BigInteger)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
