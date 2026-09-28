"""Divar listing linkage — Divar service is never the source of truth."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class DivarListing(Base):
    """Tracks assisted Divar listing prep for a vehicle (human submits final ad)."""

    __tablename__ = "divar_listings"
    __table_args__ = (UniqueConstraint("organization_id", "vehicle_id", "divar_product_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    divar_product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    divar_task_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), default="synced")  # synced | task_created | cancelled
    last_error: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    prefill_json: Mapped[str | None] = mapped_column(Text)

    work_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("work_items.id"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
