import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
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


class WorkRequest(Base):
    """درخواست مدیر به یک تیم. تیم می‌تواند از هر درخواست یک یا چند پروژه بسازد.

    وضعیت‌ها: new | in_review | converted | rejected | done
    """

    __tablename__ = "work_request"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_work_request_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(40), default="عمومی")
    priority: Mapped[str] = mapped_column(String(20), default="normal")  # low | normal | high
    due_date: Mapped[date | None] = mapped_column(Date)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))
    status: Mapped[str] = mapped_column(String(20), default="new")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkProject(Base):
    """پروژه‌ای که تیم از یک درخواست می‌سازد. هر پروژه کمپین‌های خودش را می‌گیرد.

    وضعیت‌ها: new | in_progress | done
    """

    __tablename__ = "work_project"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_work_project_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(40), default="عمومی")
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("work_request.id", ondelete="SET NULL"))
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))
    status: Mapped[str] = mapped_column(String(20), default="new")
    due_date: Mapped[date | None] = mapped_column(Date)
    planned_budget: Mapped[int | None] = mapped_column(BigInteger)
    lead_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    requester_acceptance: Mapped[str | None] = mapped_column(String(20))
    requester_acceptance_note: Mapped[str | None] = mapped_column(Text)
    mizito_lane: Mapped[str | None] = mapped_column(String(40))
    mizito_card_id: Mapped[str | None] = mapped_column(String(64))
    mizito_project_id: Mapped[str | None] = mapped_column(String(64))
    mizito_board: Mapped[str | None] = mapped_column(String(200))
    mizito_board_id: Mapped[str | None] = mapped_column(String(64))
    mizito_board_position: Mapped[int | None] = mapped_column()
    mizito_status: Mapped[str | None] = mapped_column(String(40))
    mizito_hash: Mapped[str | None] = mapped_column(String(64))
    mizito_weight: Mapped[float | None] = mapped_column(Float)
    mizito_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mizito_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mizito_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mizito_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mizito_code: Mapped[str | None] = mapped_column(String(40))
    mizito_progress: Mapped[int | None] = mapped_column(Integer)
    mizito_checklist_done: Mapped[int | None] = mapped_column(Integer)
    mizito_checklist_total: Mapped[int | None] = mapped_column(Integer)
    mizito_attachments: Mapped[int | None] = mapped_column(Integer)
    mizito_has_comments: Mapped[bool | None] = mapped_column(Boolean)
    mizito_assignee_ids: Mapped[str | None] = mapped_column(Text)
    mizito_missing_runs: Mapped[int] = mapped_column(Integer, default=0)
    mizito_removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hidden_in_cm: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkMizitoLaneBoard(Base):
    """ستون‌های کانبان یک دستهٔ مارکتینگ (بردهای پروژهٔ میزیتو)."""

    __tablename__ = "work_mizito_lane_board"
    __table_args__ = (UniqueConstraint("organization_id", "lane_slug", "board_id", name="uq_work_mizito_lane_board"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    lane_slug: Mapped[str] = mapped_column(String(40), nullable=False)
    board_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(default=0)
    removed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkMizitoChange(Base):
    """تغییر میزیتو: اعمال‌شده یا منتظر تأیید (حذف/خروج از پروژه‌های مارکتینگ)."""

    __tablename__ = "work_mizito_change"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    field: Mapped[str] = mapped_column(String(40), default="")
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="applied")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkMizitoSyncRun(Base):
    """یک اجرای همگام‌سازی میزیتو برای یک سازمان."""

    __tablename__ = "work_mizito_sync_run"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str] = mapped_column(Text, default="")
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0)
    pending_count: Mapped[int] = mapped_column(Integer, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    truncated_projects: Mapped[str] = mapped_column(Text, default="")


class WorkProjectMember(Base):
    """چند عضو با هم روی یک پروژه."""

    __tablename__ = "work_project_member"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_work_project_member"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_project.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkAttachment(Base):
    """لینک روی پروژه یا درخواست عملیاتی."""

    __tablename__ = "work_attachment"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(500), default="")
    kind: Mapped[str] = mapped_column(String(40), default="link")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DesignDeliverable(Base):
    """تحویل طراحی. تأیید فقط با انسان."""

    __tablename__ = "design_deliverable"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(default=1)
    url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Shoot(Base):
    """برنامهٔ فیلم‌برداری."""

    __tablename__ = "shoot"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    shoot_date: Mapped[date | None] = mapped_column(Date)
    location: Mapped[str] = mapped_column(String(200), default="")
    people: Mapped[str] = mapped_column(String(400), default="")
    status: Mapped[str] = mapped_column(String(20), default="planned")
    delivery_url: Mapped[str] = mapped_column(String(500), default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())