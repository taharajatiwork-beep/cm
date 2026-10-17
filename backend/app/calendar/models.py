"""تقویم: سربرگ ماه، ردیف محتوا/رویداد، مناسبت‌ها."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, Time, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class CalendarMonth(Base):
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
    __tablename__ = "calendar_entry"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    on_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    entry_type: Mapped[str] = mapped_column(String(20), default="content")
    title: Mapped[str] = mapped_column(String(400), default="")
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    all_day: Mapped[bool] = mapped_column(Boolean, default=True)
    location: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    tier: Mapped[str] = mapped_column(String(20), default="long")
    format: Mapped[str] = mapped_column(String(80), default="")
    channel: Mapped[str] = mapped_column(String(120), default="")
    topic: Mapped[str] = mapped_column(String(400), nullable=False)
    cta: Mapped[str] = mapped_column(String(200), default="")
    kpi: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(20), default="todo")
    production_status: Mapped[str] = mapped_column(String(20), default="idea")
    published_url: Mapped[str] = mapped_column(String(400), default="")
    recurrence: Mapped[str] = mapped_column(String(20), default="none")
    recur_until: Mapped[date | None] = mapped_column(Date)
    recurrence_parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("calendar_entry.id", ondelete="SET NULL"))
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_campaign.id", ondelete="SET NULL"))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("work_project.id", ondelete="SET NULL"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CalendarEntryAttendee(Base):
    __tablename__ = "calendar_entry_attendee"

    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calendar_entry.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)


class CalendarOccasion(Base):
    __tablename__ = "calendar_occasion"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    on_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="marketing")
    is_off: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
