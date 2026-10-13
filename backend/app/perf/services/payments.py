"""درخواست پرداخت و ثبت هزینه، داخل خود سامانه."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.finance_perms import can_team_expense_approve, has_expense_pay, has_price_approve
from app.core.permissions import PermissionCode
from app.services.audit import write_audit
from app.perf.models import PmCampaign, PmCost, PmPanel, PmPaymentRequest
from app.perf.services.common import PerfError, next_cost_number, now, tell, users_with
from app.services.org import get_user_permissions

_OPEN = {"requested", "manager_ok", "finance_ok"}


async def advance(
    db: AsyncSession,
    req: PmPaymentRequest,
    action: str,
    perms: set[str],
    actor_id: UUID,
    seen_amount_toman: int | None = None,
) -> PmPaymentRequest:
    if req.requester_id and actor_id == req.requester_id and action != "reject":
        raise PerfError("درخواست‌دهنده نمی‌تواند درخواست خودش را تأیید کند", 403)
    if action == "approve":
        raise PerfError("تأیید با مالی است، نه با مارکتینگ", 403)
    if action in ("finance", "pay") and seen_amount_toman is not None and seen_amount_toman != req.amount_toman:
        raise PerfError("مبلغ درخواست از وقتی دیدید عوض شده است؛ صفحه را تازه کنید و دوباره تصمیم بگیرید", 409)
    if action == "reject":
        if req.status in ("paid", "recorded", "rejected"):
            raise PerfError("این درخواست دیگر قابل رد نیست")
        if not has_expense_pay(perms):
            raise PerfError("رد درخواست با مالی است", 403)
        req.status = "rejected"
        req.updated_at = now()
        await db.flush()
        return req
    linked = bool(req.project_id or req.request_id)
    if action == "manager":
        if not linked:
            raise PerfError("این درخواست گام مدیر ندارد")
        if req.status != "requested":
            raise PerfError("وضعیت درخواست با این اقدام جور نیست")
        if not can_team_expense_approve(perms):
            raise PerfError("تأیید سرپرست تیم لازم است", 403)
        if req.manager_ok_by and req.manager_ok_by == actor_id:
            raise PerfError("همان شخص نمی‌تواند هر دو گام سرپرست و مالی را بزند", 403)
        req.status = "manager_ok"
        req.manager_ok_by = actor_id
        req.updated_at = now()
        await db.flush()
        await write_audit(
            db,
            organization_id=req.organization_id,
            action="payment.manager_ok",
            entity_type="pm_payment_request",
            entity_id=req.id,
            actor_id=actor_id,
            details={"amount_toman": req.amount_toman, "project_id": str(req.project_id) if req.project_id else None},
        )
        await _spine_note(db, req, "سرپرست تیم هزینه را تأیید کرد")
        return req
    if action not in ("finance", "pay"):
        raise PerfError("اقدام ناشناخته است")
    if req.status not in _OPEN:
        raise PerfError("وضعیت درخواست با این اقدام جور نیست")
    if linked and req.status == "requested":
        raise PerfError("اول سرپرست تیم باید تأیید کند", 403)
    if req.manager_ok_by and req.manager_ok_by == actor_id:
        raise PerfError("همان شخص نمی‌تواند هر دو گام سرپرست و مالی را بزند", 403)
    if not has_expense_pay(perms):
        raise PerfError("تأیید با مالی است", 403)
    req.status = "paid"
    req.updated_at = now()
    await _record_paid(db, req)
    req.status = "recorded"
    await db.flush()
    await write_audit(
        db,
        organization_id=req.organization_id,
        action="payment.recorded",
        entity_type="pm_payment_request",
        entity_id=req.id,
        actor_id=actor_id,
        details={"amount_toman": req.amount_toman, "manager_ok_by": str(req.manager_ok_by) if req.manager_ok_by else None},
    )
    await _notify_step(db, req)
    await _spine_note(db, req, "هزینه ثبت شد")
    return req


async def _record_paid(db: AsyncSession, req: PmPaymentRequest) -> None:
    campaign = await db.get(PmCampaign, req.campaign_id) if req.campaign_id else None
    existing = None
    if req.story_id:
        existing = await db.scalar(
            select(PmCost).where(PmCost.organization_id == req.organization_id, PmCost.story_id == req.story_id)
        )
    if existing is None:
        kind = "ابزار/پلتفرم" if req.kind == "panel_charge" else "تبلیغ - Digital Banner"
        db.add(
            PmCost(
                organization_id=req.organization_id,
                cost_number=await next_cost_number(db, req.organization_id),
                spent_on=now().date(),
                amount_toman=req.amount_toman,
                kind=kind,
                detail=req.beneficiary,
                brand=campaign.brand if campaign else "",
                campaign_code=campaign.code if campaign else "",
                cost_center=req.cost_center,
                description=req.note or req.kind,
                counts_for_cpl=req.kind != "panel_charge",
                payment_id=req.id,
                story_id=req.story_id,
            )
        )
    if req.kind == "panel_charge" and req.panel_id:
        panel = await db.get(PmPanel, req.panel_id)
        if panel and panel.organization_id == req.organization_id:
            panel.balance_toman = (panel.balance_toman or 0) + req.amount_toman
            panel.updated_at = now()
    await db.flush()


async def _finance_users(db: AsyncSession, organization_id: UUID, skip: UUID | None = None) -> list:
    people = []
    for user in await users_with(db, organization_id, PermissionCode.EXPENSE_PAY):
        if user.id == skip:
            continue
        perms = await get_user_permissions(db, user)
        if has_expense_pay(perms):
            people.append(user)
    if people:
        return people
    for user in await users_with(db, organization_id, PermissionCode.PRICE_WRITE):
        if user.id == skip:
            continue
        perms = await get_user_permissions(db, user)
        if has_expense_pay(perms):
            people.append(user)
    return people


async def _notify_step(db: AsyncSession, req: PmPaymentRequest) -> None:
    if req.status != "recorded":
        return
    from app.models import User

    org = req.organization_id
    panel = await db.get(PmPanel, req.panel_id) if req.panel_id else None
    if req.kind == "panel_charge":
        name = panel.name if panel else "پنل"
        title = "شارژ پنل انجام شد"
        body = f"{name} به مبلغ {req.amount_toman:,} تومان شارژ شد."
    else:
        title = "پرداخت انجام شد"
        body = f"مبلغ {req.amount_toman:,} تومان پرداخت و ثبت شد."
    people = await users_with(db, org, PermissionCode.PERF_WRITE)
    if req.requester_id:
        requester = await db.get(User, req.requester_id)
        if requester and all(user.id != requester.id for user in people):
            people.append(requester)
    await tell(db, organization_id=org, users=people, title=title, body=body, entity_id=req.id)


async def notify_requested(db: AsyncSession, req: PmPaymentRequest) -> None:
    people = await _finance_users(db, req.organization_id, req.requester_id)
    title = "درخواست شارژ پنل" if req.kind == "panel_charge" else "درخواست پرداخت"
    await tell(
        db,
        organization_id=req.organization_id,
        users=people,
        title=title,
        body=f"مبلغ {req.amount_toman:,} تومان منتظر تأیید مالی است.",
        entity_id=req.id,
    )


async def _spine_note(db: AsyncSession, req: PmPaymentRequest, text: str) -> None:
    if not req.requester_id or (not req.project_id and not req.request_id):
        return
    from app.requests.spine import ensure_thread, system_message

    thread = await ensure_thread(
        db,
        organization_id=req.organization_id,
        actor_id=req.requester_id,
        project_id=req.project_id,
        request_id=req.request_id,
        topic="هزینه",
    )
    await system_message(db, thread, text)
