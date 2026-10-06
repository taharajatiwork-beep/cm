"""حذف رکوردهای پرفورمنس همراه با هزینه و موجودی وابسته."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.perf.models import (
    PmCampaign,
    PmCarRequest,
    PmCost,
    PmLead,
    PmPage,
    PmPagePrice,
    PmPanel,
    PmPaymentRequest,
    PmRecipient,
    PmRecipientList,
    PmSmsSend,
    PmStory,
)
from app.perf.services.common import PerfError


async def _all(db: AsyncSession, model, *where):
    return list((await db.scalars(select(model).where(*where))).all())


async def drop_payment(db: AsyncSession, row: PmPaymentRequest) -> None:
    if row.status == "recorded" and row.kind == "panel_charge" and row.panel_id:
        panel = await db.get(PmPanel, row.panel_id)
        if panel and panel.organization_id == row.organization_id:
            panel.balance_toman = (panel.balance_toman or 0) - (row.amount_toman or 0)
    for cost in await _all(db, PmCost, PmCost.payment_id == row.id):
        await db.delete(cost)
    await db.delete(row)


async def drop_send(db: AsyncSession, row: PmSmsSend) -> None:
    for cost in await _all(db, PmCost, PmCost.sms_send_id == row.id):
        await db.delete(cost)
    await db.delete(row)


async def drop_story(db: AsyncSession, row: PmStory) -> None:
    for cost in await _all(db, PmCost, PmCost.story_id == row.id):
        await db.delete(cost)
    for payment in await _all(db, PmPaymentRequest, PmPaymentRequest.story_id == row.id):
        await drop_payment(db, payment)
    await db.delete(row)


async def drop_campaign(db: AsyncSession, row: PmCampaign) -> None:
    for send in await _all(db, PmSmsSend, PmSmsSend.campaign_id == row.id):
        await drop_send(db, send)
    for story in await _all(db, PmStory, PmStory.campaign_id == row.id):
        await drop_story(db, story)
    for payment in await _all(db, PmPaymentRequest, PmPaymentRequest.campaign_id == row.id):
        await drop_payment(db, payment)
    for cost in await _all(
        db,
        PmCost,
        PmCost.organization_id == row.organization_id,
        PmCost.campaign_code == row.code,
    ):
        await db.delete(cost)
    for lead in await _all(db, PmLead, PmLead.campaign_id == row.id):
        await db.delete(lead)
    for request in await _all(db, PmCarRequest, PmCarRequest.campaign_id == row.id):
        await db.delete(request)
    for item in await _all(db, PmRecipientList, PmRecipientList.campaign_id == row.id):
        item.campaign_id = None
    await db.delete(row)


async def drop_page(db: AsyncSession, row: PmPage) -> None:
    used = await db.scalar(select(PmStory.id).where(PmStory.page_id == row.id).limit(1))
    if used:
        raise PerfError("این پیج در قرارها استفاده شده و حذف نمی‌شود")
    for price in await _all(db, PmPagePrice, PmPagePrice.page_id == row.id):
        await db.delete(price)
    await db.delete(row)


async def drop_list(db: AsyncSession, row: PmRecipientList) -> None:
    for send in await _all(db, PmSmsSend, PmSmsSend.list_id == row.id):
        send.list_id = None
    for phone in await _all(db, PmRecipient, PmRecipient.list_id == row.id):
        await db.delete(phone)
    await db.delete(row)
