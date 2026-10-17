"""جدول‌های pm_ برای پرفورمنس مارکتینگ. مبلغ‌ها تومان هستند."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
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


class PmCampaign(Base):
    __tablename__ = "pm_campaign"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_pm_campaign_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    brand: Mapped[str] = mapped_column(String(80), default="")
    goal: Mapped[str] = mapped_column(String(255), default="")
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    budget_toman: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default="active")  # draft | active | done
    vehicle_ids: Mapped[str] = mapped_column(Text, default="")
    channels: Mapped[str] = mapped_column(String(80), default="sms")  # sms,ig_story
    lead_stages: Mapped[str] = mapped_column(Text, default="")
    brief: Mapped[str] = mapped_column(Text, default="")  # بریف کمپین (JSON)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("work_project.id", ondelete="SET NULL"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source_sheet_exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PmCampaignSequence(Base):
    """شمارندهٔ سراسری کد کمپین per-org — منبع حقیقت قبل از شیت دفتر شماره."""

    __tablename__ = "pm_campaign_sequence"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    next_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PmPanel(Base):
    __tablename__ = "pm_panel"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_pm_panel_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)  # isms | pishgam | custom
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sender_line: Mapped[str] = mapped_column(String(40), default="")
    tariff_toman: Mapped[int] = mapped_column(BigInteger, default=0)  # per page
    balance_toman: Mapped[int] = mapped_column(BigInteger, default=0)
    low_balance_toman: Mapped[int] = mapped_column(BigInteger, default=0)
    api_base: Mapped[str] = mapped_column(String(255), default="")
    api_username: Mapped[str] = mapped_column(String(120), default="")
    api_secret: Mapped[str] = mapped_column(String(255), default="")
    api_token: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PmRecipientList(Base):
    __tablename__ = "pm_recipient_list"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_campaign.id"))
    name: Mapped[str] = mapped_column(String(160), default="")
    source_filename: Mapped[str] = mapped_column(String(255), default="")
    raw_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    blacklist_count: Mapped[int] = mapped_column(Integer, default=0)
    recent_count: Mapped[int] = mapped_column(Integer, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, default=0)
    final_count: Mapped[int] = mapped_column(Integer, default=0)
    recent_days: Mapped[int] = mapped_column(Integer, default=14)
    chunk_size: Mapped[int] = mapped_column(Integer, default=15000)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PmRecipient(Base):
    __tablename__ = "pm_recipient"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    list_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pm_recipient_list.id"), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)


class PmBlacklist(Base):
    __tablename__ = "pm_blacklist"
    __table_args__ = (UniqueConstraint("organization_id", "phone", name="uq_pm_blacklist_phone"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PmPhoneTouch(Base):
    """آخرین باری که این شماره در یک ارسال ثبت‌شده بوده."""

    __tablename__ = "pm_phone_touch"
    __table_args__ = (UniqueConstraint("organization_id", "phone", name="uq_pm_phone_touch"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PmSmsSend(Base):
    __tablename__ = "pm_sms_send"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_campaign.id"))
    panel_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_panel.id"))
    list_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_recipient_list.id"))
    sender_line: Mapped[str] = mapped_column(String(40), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    pages: Mapped[int] = mapped_column(Integer, default=1)
    recipient_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cost_toman: Mapped[int] = mapped_column(BigInteger, default=0)
    delivered_count: Mapped[int] = mapped_column(Integer, default=0)
    # شناسهٔ ارسال در پنل پیشگام؛ برای خواندن دلیوری با Messages/GetDelivery.
    pishgam_message_id: Mapped[int | None] = mapped_column(BigInteger)
    calls: Mapped[int] = mapped_column(Integer, default=0)
    leads: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source_sheet_exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PmCarRequest(Base):
    __tablename__ = "pm_car_request"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    brand: Mapped[str] = mapped_column(String(80), default="")
    summary: Mapped[str] = mapped_column(String(400), default="")
    source: Mapped[str] = mapped_column(String(20), default="panel")  # panel
    status: Mapped[str] = mapped_column(String(20), default="new")  # new | planned | done
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_campaign.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PmPage(Base):
    __tablename__ = "pm_page"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    followers: Mapped[int] = mapped_column(Integer, default=0)
    topic: Mapped[str] = mapped_column(String(160), default="")
    contact: Mapped[str] = mapped_column(String(160), default="")
    price_toman: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PmPagePrice(Base):
    __tablename__ = "pm_page_price"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pm_page.id"), nullable=False)
    price_toman: Mapped[int] = mapped_column(BigInteger, nullable=False)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PmStory(Base):
    __tablename__ = "pm_story"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_campaign.id"))
    page_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_page.id"))
    kind: Mapped[str] = mapped_column(String(20), default="story")  # story | post | banner
    status: Mapped[str] = mapped_column(String(20), default="planned")  # planned | published
    published_on: Mapped[date | None] = mapped_column(Date)
    cost_toman: Mapped[int] = mapped_column(BigInteger, default=0)
    views: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    reach: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    replies: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    link_clicks: Mapped[int] = mapped_column(Integer, default=0)
    sticker_taps: Mapped[int] = mapped_column(Integer, default=0)
    navigation: Mapped[int] = mapped_column(Integer, default=0)
    forward: Mapped[int] = mapped_column(Integer, default=0)
    next_story: Mapped[int] = mapped_column(Integer, default=0)
    back: Mapped[int] = mapped_column(Integer, default=0)
    exited: Mapped[int] = mapped_column(Integer, default=0)
    leads: Mapped[int] = mapped_column(Integer, default=0)
    attachment_name: Mapped[str] = mapped_column(String(255), default="")
    attachment_path: Mapped[str] = mapped_column(String(400), default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source_sheet_exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PmPaymentRequest(Base):
    __tablename__ = "pm_payment_request"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)  # panel_charge | story | other
    amount_toman: Mapped[int] = mapped_column(BigInteger, nullable=False)
    beneficiary: Mapped[str] = mapped_column(String(160), default="")
    iban: Mapped[str] = mapped_column(String(40), default="")
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_campaign.id"))
    panel_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_panel.id"))
    story_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_story.id"))
    cost_center: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(20), default="requested")
    mizito_url: Mapped[str] = mapped_column(String(400), default="")
    note: Mapped[str] = mapped_column(String(400), default="")
    requester_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    team_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    manager_ok_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PmCost(Base):
    __tablename__ = "pm_cost"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    cost_number: Mapped[int] = mapped_column(Integer, default=0)
    spent_on: Mapped[date | None] = mapped_column(Date)
    amount_toman: Mapped[int] = mapped_column(BigInteger, default=0)
    kind: Mapped[str] = mapped_column(String(80), default="")
    detail: Mapped[str] = mapped_column(String(160), default="")
    brand: Mapped[str] = mapped_column(String(80), default="")
    campaign_code: Mapped[str] = mapped_column(String(40), default="")
    cost_center: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(String(400), default="")
    counts_for_cpl: Mapped[bool] = mapped_column(Boolean, default=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_payment_request.id"))
    sms_send_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_sms_send.id"))
    story_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_story.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source_sheet_exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PmLead(Base):
    __tablename__ = "pm_lead"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_campaign.id"))
    phone: Mapped[str] = mapped_column(String(20), default="")
    occurred_on: Mapped[date | None] = mapped_column(Date)
    campaign_code: Mapped[str] = mapped_column(String(40), default="")
    channel: Mapped[str] = mapped_column(String(40), default="")
    stage: Mapped[str] = mapped_column(String(80), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PmIntegration(Base):
    """توکن‌هایی که از خود پنل ذخیره می‌شوند. رمز عبور اینجا نیست."""

    __tablename__ = "pm_integration"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_pm_integration_org"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    mizito_token: Mapped[str] = mapped_column(Text, default="")
    mizito_snapshot: Mapped[str] = mapped_column(Text, default="")
    mizito_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    novinhub_token: Mapped[str] = mapped_column(Text, default="")
    novinhub_snapshot: Mapped[str] = mapped_column(Text, default="")
    vardast_token: Mapped[str] = mapped_column(Text, default="")
    vardast_snapshot: Mapped[str] = mapped_column(Text, default="")
    social_rollup_json: Mapped[str] = mapped_column(Text, default="")
    social_rollup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PmSocialSyncRun(Base):
    __tablename__ = "pm_social_sync_run"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str] = mapped_column(Text, default="")


class PmSocialDaily(Base):
    __tablename__ = "pm_social_daily"
    __table_args__ = (UniqueConstraint("organization_id", "day", name="uq_pm_social_daily_org_day"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    comments_open_est: Mapped[int] = mapped_column(Integer, default=0)
    conversations_open_est: Mapped[int] = mapped_column(Integer, default=0)
    comments_sampled: Mapped[int] = mapped_column(Integer, default=0)
    conversations_sampled: Mapped[int] = mapped_column(Integer, default=0)
    accounts_needing_login: Mapped[int] = mapped_column(Integer, default=0)
    vardast_chat_credit: Mapped[int | None] = mapped_column(Integer)
    vardast_channel_count: Mapped[int] = mapped_column(Integer, default=0)
    metrics_json: Mapped[str] = mapped_column(Text, default="")


class PmSocialAccountLink(Base):
    __tablename__ = "pm_social_account_link"
    __table_args__ = (UniqueConstraint("organization_id", "novinhub_account_id", name="uq_pm_social_account_link"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    novinhub_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    page_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_page.id", ondelete="SET NULL"))


class PmVardastChannelLink(Base):
    __tablename__ = "pm_vardast_channel_link"
    __table_args__ = (UniqueConstraint("organization_id", "vardast_channel_id", name="uq_pm_vardast_channel_link"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    vardast_channel_id: Mapped[str] = mapped_column(String(64), nullable=False)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_campaign.id", ondelete="SET NULL"))


class PmMizitoCursor(Base):
    """تا کجای هر گفتگو (msg_index) یا لیست کارت (زمان) میزیتو خوانده شده. متنی اینجا نیست."""

    __tablename__ = "pm_mizito_cursor"
    __table_args__ = (UniqueConstraint("organization_id", "source_key", name="uq_pm_mizito_cursor_source"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    source_key: Mapped[str] = mapped_column(String(120), nullable=False)  # dialog:<id> | tasks
    position: Mapped[int | None] = mapped_column(Integer)
    stamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PmMizitoRequest(Base):
    """پیش‌نویس کمپین از یک درخواست تبلیغ در میزیتو. خودکار کمپین نمی‌شود؛ فقط با تایید کاربر.

    از پیام فقط فیلدهای استخراج‌شده و خلاصهٔ کوتاه (حداکثر ۳۰۰ نویسه) نگه داشته می‌شود.
    """

    __tablename__ = "pm_mizito_request"
    __table_args__ = (UniqueConstraint("organization_id", "source_key", name="uq_pm_mizito_request_source"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    source_key: Mapped[str] = mapped_column(String(160), nullable=False)  # dialog:<id>:<msg_index> | task:<id>:<time>
    source_kind: Mapped[str] = mapped_column(String(20), default="dialog")  # dialog | task
    source_id: Mapped[str] = mapped_column(String(64), default="")
    source_title: Mapped[str] = mapped_column(String(120), default="")
    msg_index: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20), default="start")  # start | stop | sms | circular
    status: Mapped[str] = mapped_column(String(20), default="new")  # new | approved | rejected | duplicate
    fields: Mapped[str] = mapped_column(Text, default="{}")
    excerpt: Mapped[str] = mapped_column(String(400), default="")
    digest: Mapped[str] = mapped_column(String(40), default="")
    author_id: Mapped[str] = mapped_column(String(64), default="")
    happened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pm_campaign.id", ondelete="SET NULL"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PerfSyncState(Base):
    """یک ردیف برای هر سازمان تا دو نفر هم‌زمان شیت را به‌روز نکنند."""

    __tablename__ = "perf_sync_state"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    running: Mapped[bool] = mapped_column(Boolean, default=False)
    started_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(120), default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[str] = mapped_column(String(40), default="")
    error: Mapped[str] = mapped_column(Text, default="")


class PmPishgamAudit(Base):
    """هر کال به API پیشگام. توکن و بدنهٔ درخواست ذخیره نمی‌شود."""

    __tablename__ = "pm_pishgam_audit"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(160), nullable=False)
    is_mutating: Mapped[bool] = mapped_column(Boolean, default=False)
    request_hash: Mapped[str] = mapped_column(String(64), default="")
    # -1 یعنی قبل از شبکه رد شد. بقیه کد HTTP است.
    status_code: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PmRefProvince(Base):
    __tablename__ = "pm_ref_province"
    __table_args__ = (UniqueConstraint("organization_id", "remote_id", name="uq_pm_ref_province"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    remote_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), default="")


class PmRefCity(Base):
    __tablename__ = "pm_ref_city"
    __table_args__ = (UniqueConstraint("organization_id", "remote_id", name="uq_pm_ref_city"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    remote_id: Mapped[int] = mapped_column(Integer, nullable=False)
    province_remote_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), default="")


class PmRefDeviceBrand(Base):
    __tablename__ = "pm_ref_device_brand"
    __table_args__ = (UniqueConstraint("organization_id", "remote_id", name="uq_pm_ref_device_brand"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    remote_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), default="")


class PmRefDeviceType(Base):
    __tablename__ = "pm_ref_device_type"
    __table_args__ = (UniqueConstraint("organization_id", "remote_id", name="uq_pm_ref_device_type"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    remote_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), default="")


class PmPishgamPreview(Base):
    """آخرین پیش‌نمایش مخاطب هوشمند. مختصات و توکن ذخیره نمی‌شود."""

    __tablename__ = "pm_pishgam_preview"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_pm_pishgam_preview_org"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    payload: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
