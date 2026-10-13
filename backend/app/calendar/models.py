"""تقویم محتوا: سربرگ ماه و یک ردیف برای هر روز."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class CalendarMonth(Base):
    """سربرگ یک ماه شمسی: هدف، هفته‌ها، ترکیب محتوا، شاخص‌ها و قواعد."""

    __tablename__ = "calendar_month"
    __table_args__ = (UniqueConstraint("organization_id", "jalali_year", "jalali_month", name="uq_calendar_month"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    jalali_year: Mapped[int] = mapped_column(Integer, nullable=False)
    jalali_month: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="")
    payload: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CalendarEntry(Base):
    """یک ردیف از جدول اجرایی: کمپین، فرمت، کانال، موضوع، CTA، شاخص، وضعیت."""

    __tablename__ = "calendar_entry"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    on_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(20), default="long")  # long | mid | short | reactive
    format: Mapped[str] = mapped_column(String(80), default="")
    channel: Mapped[str] = mapped_column(String(120), default="")
    topic: Mapped[str] = mapped_column(String(400), nullable=False)
    cta: Mapped[str] = mapped_column(String(200), default="")
    kpi: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(20), default="todo")  # todo | doing | done
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_campaign.id", ondelete="SET NULL"))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("work_project.id", ondelete="SET NULL"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
