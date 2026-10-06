"""بدنه‌های درخواست بخش پرفورمنس."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CampaignIn(BaseModel):
    code: str = ""
    tag: str = ""
    title: str
    brand: str = ""
    goal: str = ""
    starts_on: date | None = None
    ends_on: date | None = None
    budget_toman: int | None = None
    status: str = "active"
    vehicle_ids: list[UUID] = []
    channels: list[str] = Field(default_factory=lambda: ["sms"])
    lead_stages: list[str] = []


class CampaignPatch(BaseModel):
    code: str | None = None
    title: str | None = None
    brand: str | None = None
    goal: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    budget_toman: int | None = None
    status: str | None = None
    vehicle_ids: list[UUID] | None = None
    channels: list[str] | None = None
    lead_stages: list[str] | None = None


class PanelIn(BaseModel):
    code: str
    name: str
    sender_line: str = ""
    tariff_toman: int = 0
    balance_toman: int = 0
    low_balance_toman: int = 0
    api_base: str = ""
    api_username: str = ""
    api_secret: str = ""
    api_token: str = ""


class PanelPatch(BaseModel):
    name: str | None = None
    sender_line: str | None = None
    tariff_toman: int | None = None
    balance_toman: int | None = None
    low_balance_toman: int | None = None
    api_base: str | None = None
    api_username: str | None = None
    api_secret: str | None = None
    api_token: str | None = None


class SmsCheckIn(BaseModel):
    text: str
    brand: str = ""
    panel_id: UUID | None = None
    recipients: int = 0


class SmsDraftIn(BaseModel):
    brand: str = ""
    cars: str = ""
    offer: str = ""
    phone: str = ""
    link: str = ""
    campaign_code: str = ""


class SmsSendPatch(BaseModel):
    body: str | None = None
    recipient_count: int | None = None
    cost_toman: int | None = None
    delivered_count: int | None = None
    calls: int | None = None
    leads: int | None = None
    sent_at: datetime | None = None


class SmsSendIn(BaseModel):
    campaign_id: UUID | None = None
    panel_id: UUID | None = None
    list_id: UUID | None = None
    sender_line: str = ""
    body: str
    recipient_count: int = 0
    sent_at: datetime | None = None
    cost_toman: int | None = None
    delivered_count: int = 0
    calls: int = 0
    leads: int = 0


class BlacklistIn(BaseModel):
    phone: str
    note: str = ""


class PaymentIn(BaseModel):
    kind: str
    amount_toman: int
    beneficiary: str = ""
    iban: str = ""
    campaign_id: UUID | None = None
    panel_id: UUID | None = None
    story_id: UUID | None = None
    cost_center: str = ""
    mizito_url: str = ""
    note: str = ""


class PaymentPatch(BaseModel):
    amount_toman: int | None = None
    cost_center: str | None = None
    note: str | None = None
    beneficiary: str | None = None


class PaymentAction(BaseModel):
    action: str  # approve | finance | pay | reject


class CarRequestIn(BaseModel):
    raw_text: str
    source: str = "panel"
    campaign_id: UUID | None = None


class CarRequestPatch(BaseModel):
    status: str | None = None
    campaign_id: UUID | None = None


class PageIn(BaseModel):
    name: str
    followers: int = 0
    topic: str = ""
    contact: str = ""
    price_toman: int = 0


class PagePatch(BaseModel):
    name: str | None = None
    followers: int | None = None
    topic: str | None = None
    contact: str | None = None
    price_toman: int | None = None


class StoryPatch(BaseModel):
    kind: str | None = None
    published_on: date | None = None
    cost_toman: int | None = None
    views: int | None = None
    leads: int | None = None


class CostPatch(BaseModel):
    spent_on: date | None = None
    amount_toman: int | None = None
    kind: str | None = None
    detail: str | None = None
    brand: str | None = None
    campaign_code: str | None = None
    description: str | None = None


class StoryPublish(BaseModel):
    published_on: date | None = None
    views: int | None = None
    leads: int | None = None


class StoryIn(BaseModel):
    campaign_id: UUID | None = None
    page_id: UUID | None = None
    kind: str = "story"
    published_on: date | None = None
    cost_toman: int = 0
    views: int = 0
    impressions: int = 0
    reach: int = 0
    likes: int = 0
    replies: int = 0
    shares: int = 0
    link_clicks: int = 0
    sticker_taps: int = 0
    navigation: int = 0
    forward: int = 0
    next_story: int = 0
    back: int = 0
    exited: int = 0
    leads: int = 0


class IsmsIn(BaseModel):
    panel_id: UUID
    mobiles: list[str]
    body: str


class PishgamSendIn(BaseModel):
    panel_id: UUID
    mobiles: list[str]
    body: str


class SheetSyncIn(BaseModel):
    kind: str = "costs"


class MizitoTokenIn(BaseModel):
    token: str = ""
