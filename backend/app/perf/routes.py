"""API پرفورمنس مارکتینگ. پیشوند /perf."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, handle_authz
from app.core.config import get_settings
from app.core.field_crypto import decrypt_secret, encrypt_secret, mask_iban
from app.core.files import UploadRejected, save_upload
from app.core.permissions import AuthorizationError, PermissionCode, require_any_permission, require_permission
from app.db.session import get_db
from app.models import User
from app.requests.models import WorkProject
from app.perf.campaign_register import LEGACY, NUMBERS, TAGS, next_code, next_number, tag_brand
from app.perf.models import (
    PmBlacklist,
    PmCampaign,
    PmCarRequest,
    PmCost,
    PmLead,
    PmPage,
    PmPagePrice,
    PmPanel,
    PmPaymentRequest,
    PmPhoneTouch,
    PmRecipient,
    PmRecipientList,
    PmSmsSend,
    PmStory,
)
from app.perf.schemas import (
    BlacklistIn,
    CampaignIn,
    CampaignPatch,
    CostPatch,
    CarRequestIn,
    CarRequestPatch,
    IsmsIn,
    PageIn,
    PagePatch,
    PanelIn,
    PanelPatch,
    PaymentAction,
    PaymentPatch,
    PaymentIn,
    PishgamSendIn,
    PishgamDeliveryIn,
    SheetSyncIn,
    MizitoRequestApprove,
    MizitoTokenIn,
    SmsCheckIn,
    SmsDraftIn,
    SmsSendIn,
    SmsSendPatch,
    StoryIn,
    StoryPatch,
    StoryPublish,
)
from app.perf.services.brief import draft_brief, parse_brief
from app.perf.services.common import PerfError, as_date, iso, next_cost_number, now, users_with
from app.perf.services.queue import next_steps
from app.perf.services.excel import (
    blank_template,
    costs_xlsx,
    parse_cost_rows,
    parse_insight_sheet,
    parse_lead_rows,
    read_table,
    reporter_xlsx,
)
from app.perf.services.integrations import (
    count_delivered,
    delivery_text,
    pick_send,
    pishgam_call,
    pishgam_delivered_count,
    push_sheet,
    read_insight_image,
    send_isms_service,
    sheet_day,
)
from app.perf.services.lists import clean_numbers, normalize_phone, phones_from_xlsx, workbook_chunks
from app.perf.services.mizito import mizito_missing, refresh_mizito, saved_mizito
from app.perf.services.mizito_finance import mizito_finance
from app.perf.services import mizito_requests as mizito_inbox
from app.perf.services.mizito_triage import mizito_triage
from app.perf.services.connections import _panel_auth, connection_status, save_mizito_token
from app.perf.services.payments import advance, notify_requested
from app.perf.services.remove import drop_campaign, drop_list, drop_page, drop_payment, drop_send, drop_story
from app.perf.services.reports import booked_cost, build_report, load_settlement, placement_live, story_rates
from app.perf.services.sheets import refresh_sheet
from app.perf.services.pishgam_targeting import AreaKeysIn, PreviewAudienceIn
from app.perf.services.sms import draft_messages
from app.perf.services.stories import parse_car_request, suggest_pages
from app.perf.sms_rules import check_sms, ensure_opt_out, estimate_cost, page_count
from app.services.notifications import notify

router = APIRouter(prefix="/perf", tags=["perf"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_CHANNELS = {"sms", "ig_story"}
_KIND_LABEL = {"story": "استوری", "post": "پست", "banner": "بنر"}
_COST_CENTERS = (
    "پرفورمنس",
    "دفتر مرکزی",
    "شعبه فروش مرزداران",
    "شعبه فروش ایرانمال",
    "شعبه فروش کاشانی",
    "کلیه شعب",
)
_OPEN_PAYMENT = ("requested", "manager_ok", "finance_ok")
_PAY_TITLE = {
    "story": "پرداخت هزینه استوری اینستاگرام",
    "post": "پرداخت هزینه پست اینستاگرام",
    "banner": "پرداخت هزینه بنر اینستاگرام",
}
_INSIGHT_FIELDS = ("views", "impressions", "reach", "likes", "replies", "shares", "link_clicks", "exited", "leads")


def _need(ctx: AuthContext, *codes: str) -> None:
    try:
        if len(codes) == 1:
            require_permission(ctx.permissions, codes[0])
        else:
            require_any_permission(ctx.permissions, *codes)
    except AuthorizationError as exc:
        raise handle_authz(exc) from exc


def _read(ctx: AuthContext) -> None:
    _need(
        ctx,
        PermissionCode.PERF_READ,
        PermissionCode.PERF_WRITE,
        PermissionCode.PERF_APPROVE,
        PermissionCode.PRICE_APPROVE,
    )


def _write(ctx: AuthContext) -> None:
    _need(ctx, PermissionCode.PERF_WRITE)


def _fail(exc: PerfError) -> None:
    raise HTTPException(status_code=exc.status, detail=exc.message)


def _fail_targeting(exc: PerfError) -> None:
    if exc.pishgam_status_code is not None:
        raise HTTPException(
            status_code=exc.status,
            detail={
                "message": exc.message,
                "pishgam_statusCode": exc.pishgam_status_code,
                "pishgam_message": exc.pishgam_message or "",
            },
        )
    raise HTTPException(status_code=exc.status, detail=exc.message)


def _xlsx(data: bytes, filename: str) -> Response:
    return Response(
        content=data,
        media_type=_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _channels(values: list[str]) -> str:
    picked = [item for item in values if item in _CHANNELS]
    if not picked:
        raise HTTPException(status_code=422, detail="حداقل یک کانال (پیامک یا سوشال) لازم است")
    return ",".join(dict.fromkeys(picked))


def _campaign_out(row: PmCampaign) -> dict:
    return {
        "id": str(row.id),
        "code": row.code,
        "title": row.title,
        "brand": row.brand,
        "goal": row.goal,
        "starts_on": iso(row.starts_on),
        "ends_on": iso(row.ends_on),
        "budget_toman": row.budget_toman,
        "status": row.status,
        "vehicle_ids": [part for part in (row.vehicle_ids or "").split(",") if part],
        "channels": [part for part in (row.channels or "").split(",") if part],
        "lead_stages": [part for part in (row.lead_stages or "").split(",") if part],
        "brief": parse_brief(row),
        "project_id": str(row.project_id) if row.project_id else None,
        "created_at": iso(row.created_at),
    }


def _panel_out(row: PmPanel) -> dict:
    return {
        "id": str(row.id),
        "code": row.code,
        "name": row.name,
        "sender_line": row.sender_line,
        "tariff_toman": row.tariff_toman,
        "balance_toman": row.balance_toman,
        "low_balance_toman": row.low_balance_toman,
        "low": (row.balance_toman or 0) <= (row.low_balance_toman or 0) and (row.low_balance_toman or 0) > 0,
        "api_base": row.api_base,
        "api_username": row.api_username,
        "has_secret": bool(row.api_secret),
        "has_token": bool(row.api_token),
        "updated_at": iso(row.updated_at),
    }


def _sees_all_campaigns(ctx: AuthContext) -> bool:
    return bool(
        {
            PermissionCode.ORG_ADMIN,
            PermissionCode.REQUEST_TRIAGE,
            PermissionCode.REQUEST_MANAGE,
            PermissionCode.PRICE_APPROVE,
        }
        & ctx.permissions
    )


async def _member_campaign_scope(db: AsyncSession, ctx: AuthContext) -> set[UUID]:
    from app.models import Task, TaskAssignee
    from app.requests.models import WorkProjectMember

    member_ids = set(
        (
            await db.scalars(
                select(WorkProjectMember.project_id).where(WorkProjectMember.user_id == ctx.user.id)
            )
        ).all()
    )
    assigned = set(
        (
            await db.scalars(
                select(Task.project_id).where(
                    Task.organization_id == ctx.organization_id,
                    Task.project_id.is_not(None),
                    Task.id.in_(select(TaskAssignee.task_id).where(TaskAssignee.user_id == ctx.user.id)),
                )
            )
        ).all()
    )
    return {item for item in member_ids | assigned if item}


async def _campaign(db: AsyncSession, ctx: AuthContext, campaign_id: UUID) -> PmCampaign:
    row = await db.get(PmCampaign, campaign_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="کمپین پیدا نشد")
    if not _sees_all_campaigns(ctx):
        scope = await _member_campaign_scope(db, ctx)
        if row.created_by != ctx.user.id and row.project_id not in scope:
            raise HTTPException(status_code=404, detail="کمپین پیدا نشد")
    return row


async def _panel(db: AsyncSession, ctx: AuthContext, panel_id: UUID) -> PmPanel:
    row = await db.get(PmPanel, panel_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پنل پیدا نشد")
    return row


@router.get("/home")
async def home(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _read(ctx)
    org = ctx.organization_id
    campaigns = list((await db.scalars(select(PmCampaign).where(PmCampaign.organization_id == org))).all())
    panels = list((await db.scalars(select(PmPanel).where(PmPanel.organization_id == org))).all())
    payments = list(
        (
            await db.scalars(
                select(PmPaymentRequest).where(
                    PmPaymentRequest.organization_id == org,
                    PmPaymentRequest.status.in_(_OPEN_PAYMENT),
                )
            )
        ).all()
    )
    sends = list((await db.scalars(select(PmSmsSend).where(PmSmsSend.organization_id == org))).all())
    recorded = list(
        (
            await db.scalars(
                select(PmPaymentRequest).where(
                    PmPaymentRequest.organization_id == org,
                    PmPaymentRequest.kind == "panel_charge",
                    PmPaymentRequest.status == "recorded",
                )
            )
        ).all()
    )
    spent: dict[UUID, int] = {}
    charged: dict[UUID, int] = {}
    for row in sends:
        if row.panel_id:
            spent[row.panel_id] = spent.get(row.panel_id, 0) + (row.cost_toman or 0)
    for row in recorded:
        if row.panel_id:
            charged[row.panel_id] = charged.get(row.panel_id, 0) + (row.amount_toman or 0)
    panel_rows = []
    for row in panels:
        item = _panel_out(row)
        item["spent_toman"] = spent.get(row.id, 0)
        item["charged_toman"] = charged.get(row.id, 0)
        panel_rows.append(item)
    active = [row for row in campaigns if row.status == "active"]
    cars = list((await db.scalars(select(PmCarRequest).where(PmCarRequest.organization_id == org))).all())
    stories = list((await db.scalars(select(PmStory).where(PmStory.organization_id == org))).all())
    return {
        "active_campaigns": [_campaign_out(row) for row in active],
        "panels": panel_rows,
        "waiting_payments": len(payments),
        "payments": [_payment_out(row) for row in payments],
        "next": next_steps(campaigns, panel_rows, len(payments), cars, stories, sends),
    }


@router.get("/campaigns")
async def list_campaigns(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _read(ctx)
    state = await refresh_sheet(db, ctx.organization_id, push=False)
    rows = state.campaigns
    if not _sees_all_campaigns(ctx):
        scope = await _member_campaign_scope(db, ctx)
        rows = [row for row in rows if row.created_by == ctx.user.id or row.project_id in scope]
    out = []
    for row in rows:
        report = state.reports[row.id]
        item = _campaign_out(row)
        item["cost_toman"] = report["cost_toman"]
        item["leads"] = report["leads"]
        item["cpl"] = report["cpl"]
        out.append(item)
    return out


def _book_row(row: dict) -> dict:
    return {**row, "brand": tag_brand(row["tag"])}


@router.get("/campaign-register")
async def campaign_register(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _read(ctx)
    codes = list(
        (
            await db.scalars(select(PmCampaign.code).where(PmCampaign.organization_id == ctx.organization_id))
        ).all()
    )
    nxt = next_number(codes)
    return {
        "next": nxt,
        "tags": TAGS,
        "rows": [_book_row(row) for row in reversed(NUMBERS)],
        "legacy": [_book_row(row) for row in reversed(LEGACY)],
    }


@router.post("/campaigns", status_code=201)
async def create_campaign(
    body: CampaignIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    code = body.code.strip()
    brand = body.brand.strip()
    tag = body.tag.strip().upper()
    if not code:
        known = {row["tag"] for row in TAGS}
        if tag and tag not in known:
            raise HTTPException(status_code=422, detail="حرف برند در دفتر شماره نیست")
        tag = tag or "S"
        from app.perf.services.campaign_codes import allocate_campaign_code

        code = await allocate_campaign_code(db, ctx.organization_id, tag)
        if not brand:
            brand = tag_brand(tag)
    if body.project_id:
        project = await db.get(WorkProject, body.project_id)
        if not project or project.organization_id != ctx.organization_id:
            raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    row = PmCampaign(
        organization_id=ctx.organization_id,
        code=code,
        title=body.title.strip(),
        brand=brand,
        goal=body.goal.strip(),
        starts_on=body.starts_on,
        ends_on=body.ends_on,
        budget_toman=body.budget_toman,
        status=body.status if body.status in ("draft", "active", "done") else "active",
        vehicle_ids=",".join(str(item) for item in body.vehicle_ids),
        channels=_channels(body.channels),
        lead_stages=",".join(part.strip() for part in body.lead_stages if part.strip()),
        project_id=body.project_id,
        created_by=ctx.user.id,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="کد کمپین تکراری است") from exc
    return _campaign_out(row)


@router.post("/campaigns/{campaign_id}/thread")
async def campaign_thread(
    campaign_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _read(ctx)
    row = await _campaign(db, ctx, campaign_id)
    from app.requests.spine import ensure_thread

    thread = await ensure_thread(
        db,
        organization_id=ctx.organization_id,
        actor_id=ctx.user.id,
        project_id=row.project_id,
        pm_campaign_id=row.id,
        topic=row.title,
    )
    return {"id": str(thread.id)}


async def _may_open_linked_project(db: AsyncSession, ctx: AuthContext, project_id: UUID | None) -> bool:
    """کسی که خود پروژه را می‌بیند، کمپین وصل‌شده به آن را هم می‌تواند باز کند."""
    if project_id is None:
        return False
    from app.models import Task, TaskAssignee
    from app.requests.models import WorkProject, WorkProjectMember, WorkRequest
    from app.requests.spine import child_team_ids

    row = await db.get(WorkProject, project_id)
    if not row or row.organization_id != ctx.organization_id:
        return False
    if PermissionCode.ORG_ADMIN in ctx.permissions:
        return True
    if PermissionCode.REQUEST_TRIAGE in ctx.permissions or PermissionCode.REQUEST_MANAGE in ctx.permissions:
        if ctx.user.team_id is None:
            return True
        visible = set(await child_team_ids(db, [ctx.user.team_id]))
        return row.team_id in visible
    if row.request_id and PermissionCode.REQUEST_CREATE in ctx.permissions:
        parent = await db.get(WorkRequest, row.request_id)
        if parent and parent.requested_by == ctx.user.id:
            return True
    member = await db.scalar(
        select(WorkProjectMember.id).where(
            WorkProjectMember.project_id == row.id,
            WorkProjectMember.user_id == ctx.user.id,
        )
    )
    if member:
        return True
    assigned = await db.scalar(
        select(Task.id).where(
            Task.organization_id == ctx.organization_id,
            Task.project_id == row.id,
            Task.id.in_(select(TaskAssignee.task_id).where(TaskAssignee.user_id == ctx.user.id)),
        )
    )
    return assigned is not None


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    perf_reader = True
    try:
        _read(ctx)
    except HTTPException:
        perf_reader = False
    row = await db.get(PmCampaign, campaign_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="کمپین پیدا نشد")
    if perf_reader:
        row = await _campaign(db, ctx, campaign_id)
    elif not await _may_open_linked_project(db, ctx, row.project_id):
        raise HTTPException(status_code=403, detail="دسترسی به این کمپین ندارید")
    try:
        state = await refresh_sheet(db, ctx.organization_id, push=False)
        report = state.reports.get(row.id) or await build_report(db, row)
    except Exception:
        report = await build_report(db, row)
    return {**_campaign_out(row), "report": report}


@router.patch("/campaigns/{campaign_id}")
async def patch_campaign(
    campaign_id: UUID,
    body: CampaignPatch,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await _campaign(db, ctx, campaign_id)
    data = body.model_dump(exclude_unset=True)
    if "code" in data and data["code"] is not None:
        code = str(data.pop("code")).strip()
        if code and code != row.code:
            taken = await db.scalar(
                select(PmCampaign.id).where(
                    PmCampaign.organization_id == ctx.organization_id,
                    PmCampaign.code == code,
                    PmCampaign.id != row.id,
                )
            )
            if taken:
                raise HTTPException(status_code=409, detail="کد کمپین تکراری است")
            old = row.code
            row.code = code
            for cost in (await db.scalars(select(PmCost).where(PmCost.organization_id == ctx.organization_id, PmCost.campaign_code == old))).all():
                cost.campaign_code = code
            for lead in (await db.scalars(select(PmLead).where(PmLead.campaign_id == row.id))).all():
                lead.campaign_code = code
    if "channels" in data and data["channels"] is not None:
        row.channels = _channels(data.pop("channels"))
    if "vehicle_ids" in data and data["vehicle_ids"] is not None:
        row.vehicle_ids = ",".join(str(item) for item in data.pop("vehicle_ids"))
    if "lead_stages" in data and data["lead_stages"] is not None:
        row.lead_stages = ",".join(part.strip() for part in data.pop("lead_stages") if part.strip())
    if "brief" in data and data["brief"] is not None:
        from app.perf.services.brief import normalize_brief

        row.brief = json.dumps(normalize_brief(data.pop("brief"), row), ensure_ascii=False)
    if data.get("project_id"):
        project = await db.get(WorkProject, data["project_id"])
        if not project or project.organization_id != ctx.organization_id:
            raise HTTPException(status_code=404, detail="پروژه پیدا نشد")
    for key, value in data.items():
        setattr(row, key, value)
    await db.flush()
    return _campaign_out(row)


@router.post("/campaigns/{campaign_id}/brief/draft")
async def draft_campaign_brief(
    campaign_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """پیش‌نویس بریف از مشخصات کمپین؛ ذخیره نمی‌شود. با LLM و در نبودش با قالب."""
    _read(ctx)
    row = await _campaign(db, ctx, campaign_id)
    brief, source = await draft_brief(row)
    return {"brief": brief, "source": source}


@router.delete("/campaigns/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await _campaign(db, ctx, campaign_id)
    await drop_campaign(db, row)
    await db.flush()
    return Response(status_code=204)


@router.get("/panels")
async def list_panels(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _read(ctx)
    rows = list((await db.scalars(select(PmPanel).where(PmPanel.organization_id == ctx.organization_id))).all())
    return [_panel_out(row) for row in rows]


@router.post("/panels", status_code=201)
async def create_panel(
    body: PanelIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = PmPanel(
        organization_id=ctx.organization_id,
        code=body.code.strip(),
        name=body.name.strip(),
        sender_line=body.sender_line,
        tariff_toman=body.tariff_toman,
        balance_toman=body.balance_toman,
        low_balance_toman=body.low_balance_toman,
        api_base=body.api_base,
        api_username=body.api_username,
        api_secret=encrypt_secret(body.api_secret),
        api_token=encrypt_secret(body.api_token),
        updated_at=now(),
    )
    db.add(row)
    await db.flush()
    return _panel_out(row)


@router.patch("/panels/{panel_id}")
async def patch_panel(
    panel_id: UUID,
    body: PanelPatch,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await _panel(db, ctx, panel_id)
    data = body.model_dump(exclude_unset=True)
    for key in ("api_secret", "api_token"):
        if key in data and not data[key]:
            data.pop(key)
        elif key in data:
            data[key] = encrypt_secret(str(data[key]))
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = now()
    await db.flush()
    return _panel_out(row)


@router.post("/sms/check")
async def sms_check(
    body: SmsCheckIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _read(ctx)
    result = check_sms(body.text, brand=body.brand)
    tariff = 0
    if body.panel_id:
        panel = await _panel(db, ctx, body.panel_id)
        tariff = panel.tariff_toman or 0
    result["estimated_cost_toman"] = estimate_cost(result["pages"], body.recipients, tariff)
    return result


@router.post("/sms/drafts")
async def sms_drafts(body: SmsDraftIn, ctx: AuthContext = Depends(get_current_user)):
    _write(ctx)
    return await draft_messages(
        brand=body.brand,
        cars=body.cars,
        offer=body.offer,
        phone=body.phone,
        link=body.link,
        campaign_code=body.campaign_code,
    )


@router.post("/sms/pull")
async def pull_sms_from_panels(ctx: AuthContext = Depends(get_current_user)):
    """پیش‌نویس از پنل. تا وقتی فهرست ارسال در API پیشگام نباشد، چیزی ساخته نمی‌شود و پیامک فرستاده نمی‌شود."""
    _read(ctx)
    return {
        "imported": 0,
        "drafts": [],
        "note": "فهرست ارسال در API پیشگام ثبت نشده است. ارسال را با گزارش تحویل و شیت تطبیق دهید و فقط تأیید کنید.",
    }


@router.get("/sms/sends")
async def list_sends(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _read(ctx)
    rows = list(
        (
            await db.scalars(
                select(PmSmsSend)
                .where(PmSmsSend.organization_id == ctx.organization_id)
                .order_by(PmSmsSend.created_at.desc())
            )
        ).all()
    )
    campaigns = {
        row.id: row.code
        for row in (await db.scalars(select(PmCampaign).where(PmCampaign.organization_id == ctx.organization_id))).all()
    }
    panels = {
        row.id: row.name
        for row in (await db.scalars(select(PmPanel).where(PmPanel.organization_id == ctx.organization_id))).all()
    }
    return [_send_out(row, campaigns.get(row.campaign_id, ""), panels.get(row.panel_id, "")) for row in rows]


@router.post("/sms/sends", status_code=201)
async def create_send(
    body: SmsSendIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    campaign = await _campaign(db, ctx, body.campaign_id) if body.campaign_id else None
    panel = await _panel(db, ctx, body.panel_id) if body.panel_id else None
    text = ensure_opt_out(body.body)
    pages = page_count(text)
    if pages > 10:
        raise HTTPException(status_code=422, detail="متن بیش از ۱۰ صفحه است")
    recipients = body.recipient_count
    if body.list_id:
        rec_list = await db.get(PmRecipientList, body.list_id)
        if not rec_list or rec_list.organization_id != ctx.organization_id:
            raise HTTPException(status_code=404, detail="لیست پیدا نشد")
        if recipients <= 0:
            recipients = rec_list.final_count
    cost = body.cost_toman
    if cost is None:
        cost = estimate_cost(pages, recipients, panel.tariff_toman if panel else 0)
    if panel and cost and cost > (panel.balance_toman or 0):
        shortfall = cost - (panel.balance_toman or 0)
        open_charge = await db.scalar(
            select(PmPaymentRequest).where(
                PmPaymentRequest.organization_id == ctx.organization_id,
                PmPaymentRequest.panel_id == panel.id,
                PmPaymentRequest.kind == "panel_charge",
                PmPaymentRequest.status.in_(_OPEN_PAYMENT),
            )
        )
        if open_charge is None:
            open_charge = PmPaymentRequest(
                organization_id=ctx.organization_id,
                kind="panel_charge",
                amount_toman=shortfall,
                beneficiary=panel.name,
                campaign_id=campaign.id if campaign else None,
                panel_id=panel.id,
                cost_center="پرفورمنس",
                note="برای این ارسال؛ مبلغ را قبل از تأیید مالی می‌توان عوض کرد",
                requester_id=ctx.user.id,
                status="requested",
            )
            db.add(open_charge)
            await db.flush()
            await notify_requested(db, open_charge)
        await db.commit()
        raise HTTPException(
            status_code=409,
            detail=(
                f"موجودی {panel.name} برای این ارسال کافی نیست. "
                f"درخواست شارژ {open_charge.amount_toman:,} تومان ثبت شده و از صفحهٔ پول قابل ویرایش است."
            ),
        )
    row = PmSmsSend(
        organization_id=ctx.organization_id,
        campaign_id=campaign.id if campaign else None,
        panel_id=panel.id if panel else None,
        list_id=body.list_id,
        sender_line=body.sender_line or (panel.sender_line if panel else ""),
        body=text,
        pages=pages,
        recipient_count=recipients,
        sent_at=body.sent_at or now(),
        cost_toman=cost or 0,
        delivered_count=body.delivered_count,
        calls=body.calls,
        leads=body.leads,
        pishgam_message_id=body.pishgam_message_id,
        created_by=ctx.user.id,
    )
    db.add(row)
    await db.flush()
    if cost:
        db.add(
            PmCost(
                organization_id=ctx.organization_id,
                cost_number=await next_cost_number(db, ctx.organization_id),
                spent_on=(row.sent_at.date() if row.sent_at else now().date()),
                amount_toman=cost,
                kind="پیامک",
                detail=panel.name if panel else "",
                brand=campaign.brand if campaign else "",
                campaign_code=campaign.code if campaign else "",
                cost_center="پرفورمنس",
                description=text[:180],
                counts_for_cpl=True,
                sms_send_id=row.id,
            )
        )
    if panel and cost:
        panel.balance_toman = (panel.balance_toman or 0) - cost
        panel.updated_at = now()
        if panel.low_balance_toman and panel.balance_toman <= panel.low_balance_toman:
            for user in await users_with(db, ctx.organization_id, PermissionCode.PERF_WRITE):
                await notify(
                    db,
                    organization_id=ctx.organization_id,
                    user_id=user.id,
                    title="موجودی پنل کم است",
                    body=f"موجودی {panel.name} به {panel.balance_toman:,} تومان رسیده است.",
                    entity_type="pm_panel",
                    entity_id=panel.id,
                )
    if body.list_id:
        phones = list(
            (
                await db.scalars(select(PmRecipient.phone).where(PmRecipient.list_id == body.list_id))
            ).all()
        )
        sent_at = row.sent_at or now()
        for phone in phones:
            touch = await db.scalar(
                select(PmPhoneTouch).where(
                    PmPhoneTouch.organization_id == ctx.organization_id,
                    PmPhoneTouch.phone == phone,
                )
            )
            if touch:
                touch.last_sent_at = sent_at
            else:
                db.add(
                    PmPhoneTouch(
                        organization_id=ctx.organization_id,
                        phone=phone,
                        last_sent_at=sent_at,
                    )
                )
    await db.flush()
    return _send_out(row, campaign.code if campaign else "")


@router.patch("/sms/sends/{send_id}")
async def patch_send(
    send_id: UUID,
    body: SmsSendPatch,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await db.get(PmSmsSend, send_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="ارسال پیدا نشد")
    data = body.model_dump(exclude_unset=True)
    old_cost = row.cost_toman or 0
    for key, value in data.items():
        setattr(row, key, value if key != "body" else (value or "").strip())
    linked = list((await db.scalars(select(PmCost).where(PmCost.sms_send_id == row.id))).all())
    if "cost_toman" in data or "sent_at" in data:
        for cost in linked:
            if "cost_toman" in data:
                cost.amount_toman = row.cost_toman or 0
            if row.sent_at:
                cost.spent_on = row.sent_at.date()
    if row.panel_id and "cost_toman" in data:
        panel = await db.get(PmPanel, row.panel_id)
        if panel and panel.organization_id == row.organization_id:
            panel.balance_toman = (panel.balance_toman or 0) + old_cost - (row.cost_toman or 0)
    campaign = await db.get(PmCampaign, row.campaign_id) if row.campaign_id else None
    await db.flush()
    return _send_out(row, campaign.code if campaign else "")


@router.delete("/sms/sends/{send_id}", status_code=204)
async def delete_send(
    send_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await db.get(PmSmsSend, send_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="ارسال پیدا نشد")
    await drop_send(db, row)
    await db.flush()
    return Response(status_code=204)


@router.post("/sms/sends/{send_id}/delivery")
async def import_delivery(
    send_id: UUID,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await db.get(PmSmsSend, send_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="ارسال پیدا نشد")
    from app.perf.services.excel import read_table

    header, table = read_table(await file.read())
    index = 0
    for i, name in enumerate(header):
        if "وضعیت" in name or "status" in name.lower():
            index = i
            break
    cells = [line[index] if index < len(line) else None for line in table]
    row.delivered_count = count_delivered(cells)
    await db.flush()
    return {"delivered_count": row.delivered_count, "send_id": str(row.id)}


@router.post("/sms/sends/{send_id}/pishgam-delivery")
async def pishgam_send_delivery(
    send_id: UUID,
    body: PishgamDeliveryIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """دلیوری ارسال پیشگام با شناسهٔ ذخیره‌شده خوانده و روی همان رکورد ارسال می‌نشیند."""
    _write(ctx)
    row = await db.get(PmSmsSend, send_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="ارسال پیدا نشد")
    message_id = body.message_id or row.pishgam_message_id
    if not message_id:
        raise HTTPException(status_code=422, detail="شناسهٔ ارسال پیشگام روی این رکورد ذخیره نشده است")
    recipients = [str(number).strip() for number in body.recipients if str(number).strip()]
    if not recipients:
        raise HTTPException(status_code=422, detail="شمارهٔ گیرنده‌ای وارد نشده است")
    if len(recipients) > 100:
        raise HTTPException(status_code=422, detail="حداکثر ۱۰۰ گیرنده در هر درخواست پذیرفته می‌شود")
    if not row.panel_id:
        raise HTTPException(status_code=422, detail="این ارسال به پنلی وصل نیست")
    panel = await _panel(db, ctx, row.panel_id)
    if panel.code != "pishgam":
        raise HTTPException(status_code=422, detail="دلیوری API فقط برای پنل پیشگام است")
    from app.core.config import get_settings

    try:
        api_base, api_token = _panel_auth(panel)
        result = await pishgam_call(
            api_base=api_base,
            token=api_token,
            path=get_settings().pishgam_report_path,
            method="POST",
            payload={"messageId": int(message_id), "recipientNumbers": recipients},
        )
    except PerfError as exc:
        _fail(exc)
    try:
        data = json.loads(result["body"]) if result["status_code"] == 200 else {}
    except ValueError:
        data = {}
    if int(data.get("statusCode") or 0) != 0:
        from app.perf.services.connections import pishgam_reason

        return {"ok": False, "reason": pishgam_reason(int(data.get("statusCode") or 0)), "rows": [], "delivered_count": 0}
    rows = [
        {
            "to_number": str(item.get("toNumber") or ""),
            "status": item.get("deliveryStatus"),
            "text": delivery_text(item.get("deliveryStatus")),
        }
        for item in data.get("numberDeliveryStatus") or []
    ]
    delivered = pishgam_delivered_count([item["status"] for item in rows])
    row.pishgam_message_id = int(message_id)
    row.delivered_count = delivered
    await db.flush()
    return {"ok": True, "reason": "", "rows": rows, "delivered_count": delivered, "send_id": str(row.id)}


@router.post("/sms/delivery")
async def match_delivery(
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """فایل گزارش پنل را بدون انتخاب ردیف به ارسال همان روز یا همان تعداد می‌چسباند."""
    _write(ctx)
    header, table = read_table(await file.read())
    index = 0
    for i, name in enumerate(header):
        if "وضعیت" in name or "status" in name.lower():
            index = i
            break
    cells = [line[index] if index < len(line) else None for line in table if any(line)]
    filled = [line for line in table if any(line)]
    sends = list(
        (
            await db.scalars(
                select(PmSmsSend).where(PmSmsSend.organization_id == ctx.organization_id)
            )
        ).all()
    )
    row = pick_send(sends, len(filled), sheet_day(header, filled))
    if row is None:
        raise HTTPException(
            status_code=422,
            detail="این فایل به یک ارسال مشخص نخورد. از دکمهٔ همان ردیف بارگذاری کنید.",
        )
    row.delivered_count = count_delivered(cells)
    await db.flush()
    campaign = await db.get(PmCampaign, row.campaign_id) if row.campaign_id else None
    return {
        "send_id": str(row.id),
        "delivered_count": row.delivered_count,
        "campaign_code": campaign.code if campaign else "",
    }


@router.post("/lists/prepare", status_code=201)
async def prepare_list(
    file: UploadFile = File(...),
    recent_days: int = Form(14),
    chunk_size: int = Form(15000),
    name: str = Form(""),
    campaign_id: UUID | None = Form(None),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    if campaign_id:
        await _campaign(db, ctx, campaign_id)
    raw = phones_from_xlsx(await file.read())
    blocked = set(
        (
            await db.scalars(
                select(PmBlacklist.phone).where(PmBlacklist.organization_id == ctx.organization_id)
            )
        ).all()
    )
    cutoff = datetime.now(UTC) - timedelta(days=max(0, recent_days))
    recent = set(
        (
            await db.scalars(
                select(PmPhoneTouch.phone).where(
                    PmPhoneTouch.organization_id == ctx.organization_id,
                    PmPhoneTouch.last_sent_at >= cutoff,
                )
            )
        ).all()
    )
    cleaned = clean_numbers(raw, blacklist=blocked, recent=recent)
    row = PmRecipientList(
        organization_id=ctx.organization_id,
        campaign_id=campaign_id,
        name=name or (file.filename or "دیدار"),
        source_filename=file.filename or "",
        raw_count=cleaned["raw_count"],
        duplicate_count=cleaned["duplicate_count"],
        blacklist_count=cleaned["blacklist_count"],
        recent_count=cleaned["recent_count"],
        invalid_count=cleaned["invalid_count"],
        final_count=cleaned["final_count"],
        recent_days=recent_days,
        chunk_size=chunk_size,
        created_by=ctx.user.id,
    )
    db.add(row)
    await db.flush()
    for phone in cleaned["phones"]:
        db.add(PmRecipient(organization_id=ctx.organization_id, list_id=row.id, phone=phone))
    await db.flush()
    return _list_out(row)


@router.get("/lists")
async def list_lists(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _read(ctx)
    rows = list(
        (
            await db.scalars(
                select(PmRecipientList)
                .where(PmRecipientList.organization_id == ctx.organization_id)
                .order_by(PmRecipientList.created_at.desc())
            )
        ).all()
    )
    return [_list_out(row) for row in rows]


@router.get("/lists/{list_id}/export")
async def export_list(
    list_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _read(ctx)
    row = await db.get(PmRecipientList, list_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="لیست پیدا نشد")
    phones = list(
        (await db.scalars(select(PmRecipient.phone).where(PmRecipient.list_id == row.id))).all()
    )
    return _xlsx(workbook_chunks(phones, row.chunk_size or 15000), "recipients.xlsx")


@router.delete("/lists/{list_id}", status_code=204)
async def delete_list(
    list_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await db.get(PmRecipientList, list_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="لیست پیدا نشد")
    await drop_list(db, row)
    await db.flush()
    return Response(status_code=204)


@router.get("/blacklist")
async def list_blacklist(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _read(ctx)
    rows = list(
        (await db.scalars(select(PmBlacklist).where(PmBlacklist.organization_id == ctx.organization_id))).all()
    )
    return [{"id": str(row.id), "phone": row.phone, "note": row.note} for row in rows]


@router.post("/blacklist", status_code=201)
async def add_blacklist(
    body: BlacklistIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    phone = normalize_phone(body.phone)
    if not phone:
        raise HTTPException(status_code=422, detail="شماره معتبر نیست")
    row = PmBlacklist(organization_id=ctx.organization_id, phone=phone, note=body.note)
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="این شماره در لیست سیاه هست") from exc
    return {"id": str(row.id), "phone": row.phone, "note": row.note}


@router.delete("/blacklist/{item_id}", status_code=204)
async def delete_blacklist(
    item_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await db.get(PmBlacklist, item_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="شماره پیدا نشد")
    await db.delete(row)
    await db.flush()
    return Response(status_code=204)


@router.get("/payments")
async def list_payments(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _read(ctx)
    rows = list(
        (
            await db.scalars(
                select(PmPaymentRequest)
                .where(PmPaymentRequest.organization_id == ctx.organization_id)
                .order_by(PmPaymentRequest.created_at.desc())
            )
        ).all()
    )
    ids = {row.requester_id for row in rows if row.requester_id}
    names = {}
    if ids:
        people = (await db.scalars(select(User).where(User.id.in_(ids)))).all()
        names = {person.id: person.full_name for person in people}
    return [_payment_out(row, names.get(row.requester_id, "")) for row in rows]


@router.post("/payments", status_code=201)
async def create_payment(
    body: PaymentIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    if body.kind not in ("panel_charge", "story", "other"):
        raise HTTPException(status_code=422, detail="نوع درخواست نامعتبر است")
    if body.amount_toman <= 0:
        raise HTTPException(status_code=422, detail="مبلغ باید بیشتر از صفر باشد")
    if body.campaign_id:
        await _campaign(db, ctx, body.campaign_id)
    if body.panel_id:
        await _panel(db, ctx, body.panel_id)
    row = PmPaymentRequest(
        organization_id=ctx.organization_id,
        kind=body.kind,
        amount_toman=body.amount_toman,
        beneficiary=body.beneficiary,
        iban=encrypt_secret(body.iban),
        campaign_id=body.campaign_id,
        panel_id=body.panel_id if body.kind == "panel_charge" else None,
        story_id=body.story_id,
        cost_center=body.cost_center,
        mizito_url=body.mizito_url,
        note=body.note,
        requester_id=ctx.user.id,
        project_id=body.project_id,
        request_id=body.request_id,
        team_id=body.team_id,
        status="requested",
    )
    db.add(row)
    await db.flush()
    await notify_requested(db, row)
    return _payment_out(row)


@router.patch("/payments/{payment_id}")
async def patch_payment(
    payment_id: UUID,
    body: PaymentPatch,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await db.get(PmPaymentRequest, payment_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="درخواست پیدا نشد")
    if row.status != "requested":
        raise HTTPException(status_code=409, detail="فقط درخواستِ باز را می‌توان عوض کرد")
    if row.requester_id != ctx.user.id:
        raise HTTPException(status_code=403, detail="مبلغ را خود درخواست‌دهنده عوض می‌کند")
    if body.amount_toman is not None:
        if body.amount_toman <= 0:
            raise HTTPException(status_code=422, detail="مبلغ باید بیشتر از صفر باشد")
        row.amount_toman = body.amount_toman
    if body.cost_center is not None:
        row.cost_center = body.cost_center
    if body.note is not None:
        row.note = body.note
    if body.beneficiary is not None:
        row.beneficiary = body.beneficiary
    await db.flush()
    return _payment_out(row)


@router.delete("/payments/{payment_id}", status_code=204)
async def delete_payment(
    payment_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await db.get(PmPaymentRequest, payment_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="درخواست پیدا نشد")
    if row.status == "recorded":
        raise HTTPException(status_code=409, detail="پرداخت ثبت‌شده حذف نمی‌شود. ردیف هزینه را از شیت بردارید.")
    await drop_payment(db, row)
    await db.flush()
    return Response(status_code=204)


@router.post("/payments/{payment_id}/advance")
async def advance_payment(
    payment_id: UUID,
    body: PaymentAction,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _read(ctx)
    row = await db.get(PmPaymentRequest, payment_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="درخواست پیدا نشد")
    try:
        await advance(db, row, body.action, ctx.permissions, ctx.user.id, body.seen_amount_toman)
    except PerfError as exc:
        _fail(exc)
    return _payment_out(row)


@router.get("/pages")
async def list_pages(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _read(ctx)
    rows = list((await db.scalars(select(PmPage).where(PmPage.organization_id == ctx.organization_id))).all())
    stories = list(
        (await db.scalars(select(PmStory).where(PmStory.organization_id == ctx.organization_id))).all()
    )
    paid_ids, linked_ids = await load_settlement(db, ctx.organization_id)
    history = []
    if rows:
        history = list(
            (
                await db.scalars(select(PmPagePrice).where(PmPagePrice.page_id.in_([row.id for row in rows])))
            ).all()
        )
    by_page: dict[UUID, list] = {}
    for item in history:
        by_page.setdefault(item.page_id, []).append(item)
    out = []
    for row in rows:
        mine = [story for story in stories if story.page_id == row.id and placement_live(story)]
        cost = sum(booked_cost(story, paid_ids, linked_ids) for story in mine)
        views = sum(story.views or 0 for story in mine)
        leads = sum(story.leads or 0 for story in mine)
        prices = sorted(by_page.get(row.id, []), key=lambda item: item.created_at or now(), reverse=True)[:5]
        out.append(
            _page_out(
                row,
                cpl=round(cost / leads, 1) if leads else None,
                cpv=round(cost / views, 1) if views else None,
                prices=[
                    {"price_toman": item.price_toman, "note": item.note, "created_at": iso(item.created_at)}
                    for item in prices
                ],
            )
        )
    return out


@router.post("/pages", status_code=201)
async def create_page(
    body: PageIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = PmPage(
        organization_id=ctx.organization_id,
        name=body.name.strip(),
        followers=body.followers,
        topic=body.topic,
        contact=body.contact,
        price_toman=body.price_toman,
    )
    db.add(row)
    await db.flush()
    if body.price_toman:
        db.add(PmPagePrice(page_id=row.id, price_toman=body.price_toman, note="قیمت اولیه", created_at=now()))
    return _page_out(row)


@router.patch("/pages/{page_id}")
async def patch_page(
    page_id: UUID,
    body: PagePatch,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await db.get(PmPage, page_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پیج پیدا نشد")
    data = body.model_dump(exclude_unset=True)
    previous = row.price_toman
    for key, value in data.items():
        setattr(row, key, value)
    if "price_toman" in data and data["price_toman"] != previous:
        db.add(PmPagePrice(page_id=row.id, price_toman=data["price_toman"], note="تغییر قیمت", created_at=now()))
    await db.flush()
    return _page_out(row)


@router.delete("/pages/{page_id}", status_code=204)
async def delete_page(
    page_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await db.get(PmPage, page_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="پیج پیدا نشد")
    try:
        await drop_page(db, row)
    except PerfError as exc:
        _fail(exc)
    await db.flush()
    return Response(status_code=204)


@router.get("/pages/suggest")
async def suggest(
    budget: int = Query(..., ge=0),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _read(ctx)
    pages = list((await db.scalars(select(PmPage).where(PmPage.organization_id == ctx.organization_id))).all())
    stories = list((await db.scalars(select(PmStory).where(PmStory.organization_id == ctx.organization_id))).all())
    paid_ids, linked_ids = await load_settlement(db, ctx.organization_id)
    packed = []
    for page in pages:
        mine = [row for row in stories if row.page_id == page.id and placement_live(row)]
        cost = sum(booked_cost(row, paid_ids, linked_ids) for row in mine)
        views = sum(row.views or 0 for row in mine)
        leads = sum(row.leads or 0 for row in mine)
        packed.append(
            {
                "id": str(page.id),
                "name": page.name,
                "price_toman": page.price_toman,
                "cpl": round(cost / leads, 1) if leads else None,
                "cpv": round(cost / views, 1) if views else None,
            }
        )
    return suggest_pages(packed, budget)


@router.get("/car-requests")
async def list_requests(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _read(ctx)
    rows = list(
        (
            await db.scalars(
                select(PmCarRequest)
                .where(PmCarRequest.organization_id == ctx.organization_id)
                .order_by(PmCarRequest.created_at.desc())
            )
        ).all()
    )
    return [_request_out(row) for row in rows]


@router.post("/car-requests", status_code=201)
async def create_request(
    body: CarRequestIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    parsed = parse_car_request(body.raw_text)
    if body.campaign_id:
        await _campaign(db, ctx, body.campaign_id)
    row = PmCarRequest(
        organization_id=ctx.organization_id,
        raw_text=body.raw_text,
        brand=parsed["brand"],
        summary=parsed["summary"],
        source="panel",
        campaign_id=body.campaign_id,
        created_by=ctx.user.id,
    )
    db.add(row)
    await db.flush()
    return _request_out(row)


@router.patch("/car-requests/{request_id}")
async def patch_request(
    request_id: UUID,
    body: CarRequestPatch,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await db.get(PmCarRequest, request_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="درخواست پیدا نشد")
    if body.status:
        row.status = body.status
    if body.campaign_id:
        await _campaign(db, ctx, body.campaign_id)
        row.campaign_id = body.campaign_id
    await db.flush()
    return _request_out(row)


@router.delete("/car-requests/{request_id}", status_code=204)
async def delete_request(
    request_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await db.get(PmCarRequest, request_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="درخواست پیدا نشد")
    await db.delete(row)
    await db.flush()
    return Response(status_code=204)


@router.get("/stories")
async def list_stories(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _read(ctx)
    rows = list(
        (await db.scalars(select(PmStory).where(PmStory.organization_id == ctx.organization_id))).all()
    )
    pages = {
        row.id: row.name
        for row in (await db.scalars(select(PmPage).where(PmPage.organization_id == ctx.organization_id))).all()
    }
    codes = {
        row.id: row.code
        for row in (await db.scalars(select(PmCampaign).where(PmCampaign.organization_id == ctx.organization_id))).all()
    }
    payments = _payments_by_story(
        list(
            (
                await db.scalars(
                    select(PmPaymentRequest).where(PmPaymentRequest.organization_id == ctx.organization_id)
                )
            ).all()
        )
    )
    out = []
    for row in rows:
        item = _story_out(row, pages.get(row.page_id, ""), payments.get(row.id))
        item["campaign_code"] = codes.get(row.campaign_id, "")
        out.append(item)
    return out


@router.post("/stories", status_code=201)
async def create_story(
    body: StoryIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    if body.campaign_id:
        await _campaign(db, ctx, body.campaign_id)
    page = None
    if body.page_id:
        page = await db.get(PmPage, body.page_id)
        if not page or page.organization_id != ctx.organization_id:
            raise HTTPException(status_code=404, detail="پیج پیدا نشد")
    kind = body.kind if body.kind in _KIND_LABEL else "story"
    cost = body.cost_toman or (page.price_toman if page else 0)
    row = PmStory(
        organization_id=ctx.organization_id,
        campaign_id=body.campaign_id,
        page_id=body.page_id,
        kind=kind,
        status="planned",
        cost_toman=cost,
        created_by=ctx.user.id,
    )
    db.add(row)
    await db.flush()
    payment = None
    if cost > 0:
        payment = PmPaymentRequest(
            organization_id=ctx.organization_id,
            kind="story",
            amount_toman=cost,
            beneficiary=page.name if page else _KIND_LABEL[kind],
            campaign_id=body.campaign_id,
            story_id=row.id,
            cost_center="پرفورمنس",
            note=_PAY_TITLE[kind],
            requester_id=ctx.user.id,
            status="requested",
        )
        db.add(payment)
        await db.flush()
        await notify_requested(db, payment)
    return _story_out(row, page.name if page else "", payment)


@router.patch("/stories/{story_id}")
async def patch_story(
    story_id: UUID,
    body: StoryPatch,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await db.get(PmStory, story_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="قرار پیدا نشد")
    data = body.model_dump(exclude_unset=True)
    if "kind" in data and data["kind"] not in ("story", "post", "banner", None):
        raise HTTPException(status_code=422, detail="نوع قرار نامعتبر است")
    for key, value in data.items():
        setattr(row, key, value)
    if "cost_toman" in data:
        for cost in (await db.scalars(select(PmCost).where(PmCost.story_id == row.id))).all():
            cost.amount_toman = row.cost_toman or 0
        for payment in (await db.scalars(select(PmPaymentRequest).where(PmPaymentRequest.story_id == row.id, PmPaymentRequest.status == "requested"))).all():
            payment.amount_toman = row.cost_toman or 0
    page = await db.get(PmPage, row.page_id) if row.page_id else None
    await db.flush()
    return _story_out(row, page.name if page else "")


@router.delete("/stories/{story_id}", status_code=204)
async def delete_story(
    story_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await db.get(PmStory, story_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="قرار پیدا نشد")
    await drop_story(db, row)
    await db.flush()
    return Response(status_code=204)


@router.post("/stories/{story_id}/publish")
async def publish_story(
    story_id: UUID,
    body: StoryPublish,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await db.get(PmStory, story_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="استوری پیدا نشد")
    row.status = "published"
    row.published_on = body.published_on or row.published_on or now().date()
    if body.views is not None:
        row.views = body.views
    if body.leads is not None:
        row.leads = body.leads
    await db.flush()
    page_name = ""
    if row.page_id:
        page = await db.get(PmPage, row.page_id)
        page_name = page.name if page else ""
    payment = await db.scalar(
        select(PmPaymentRequest)
        .where(PmPaymentRequest.story_id == row.id)
        .order_by(PmPaymentRequest.created_at.desc())
    )
    return _story_out(row, page_name, payment)


@router.post("/stories/{story_id}/insight")
async def read_story_insight(
    story_id: UUID,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await db.get(PmStory, story_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="استوری پیدا نشد")
    data = await file.read()
    try:
        path = save_upload(file.filename or "insight.png", file.content_type, data)
    except UploadRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row.attachment_name = file.filename or ""
    row.attachment_path = str(path)
    name = (file.filename or "").lower()
    if name.endswith(".xlsx"):
        fields = parse_insight_sheet(data)
        if not fields:
            return {"ok": False, "source": "file", "reason": "ستونی برای نمایش یا ورودی پیدا نشد"}
        _apply_insight(row, fields)
        await db.flush()
        return {"ok": True, "source": "file", "fields": fields}
    result = await read_insight_image(data, file.content_type or "image/png")
    if result.get("ok"):
        _apply_insight(row, result.get("fields") or {})
    await db.flush()
    return result


@router.get("/sheet")
async def sheet(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """شیت داخلی: همان ردیف‌هایی که اکسل گزارش و هزینه از آن ساخته می‌شود."""
    _read(ctx)
    state = await refresh_sheet(db, ctx.organization_id)
    codes = {row.id: row.code for row in state.campaigns}
    pages = {key: row.name for key, row in state.pages.items()}
    return {
        "google_connected": state.google_connected,
        "spreadsheet_url": state.spreadsheet_url,
        "reason": state.reason,
        "sources": state.sources,
        "campaigns": [
            {
                "id": str(row.id),
                "code": row.code,
                "title": row.title,
                "brand": row.brand,
                "cost_toman": state.reports[row.id]["cost_toman"],
                "leads": state.reports[row.id]["leads"],
                "views": state.reports[row.id]["views"],
                "cpl": state.reports[row.id]["cpl"],
            }
            for row in state.campaigns
        ],
        "sms": [_send_out(row, codes.get(row.campaign_id, "")) for row in state.sends],
        "stories": [
            {
                **_story_out(row, pages.get(row.page_id, "")),
                "campaign_code": codes.get(row.campaign_id, ""),
            }
            for row in state.stories
        ],
        "costs": [_cost_dict(row) for row in state.costs],
    }


@router.get("/excel/costs")
async def export_costs(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _read(ctx)
    rows = list((await db.scalars(select(PmCost).where(PmCost.organization_id == ctx.organization_id))).all())
    return _xlsx(costs_xlsx([_cost_dict(row) for row in rows]), "cost-tracking.xlsx")


@router.get("/excel/reporter")
async def export_reporter(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _read(ctx)
    campaigns = list(
        (await db.scalars(select(PmCampaign).where(PmCampaign.organization_id == ctx.organization_id))).all()
    )
    reports = [await build_report(db, row) for row in campaigns]
    sends = list((await db.scalars(select(PmSmsSend).where(PmSmsSend.organization_id == ctx.organization_id))).all())
    stories = list((await db.scalars(select(PmStory).where(PmStory.organization_id == ctx.organization_id))).all())
    codes = {row.id: row.code for row in campaigns}
    pages = {
        row.id: row.name
        for row in (await db.scalars(select(PmPage).where(PmPage.organization_id == ctx.organization_id))).all()
    }
    paid_ids, linked_ids = await load_settlement(db, ctx.organization_id)
    sms_rows = [_send_out(row, codes.get(row.campaign_id, "")) for row in sends]
    story_rows = []
    for row in stories:
        if not placement_live(row):
            continue
        rates = story_rates(row)
        story_rows.append(
            {
                "campaign_code": codes.get(row.campaign_id, ""),
                "page": pages.get(row.page_id, ""),
                "published_on": row.published_on,
                "cost_toman": booked_cost(row, paid_ids, linked_ids),
                "views": row.views,
                "reach": row.reach,
                "link_clicks": row.link_clicks,
                "shares": row.shares,
                "replies": row.replies,
                "exited": row.exited,
                "leads": row.leads,
                **rates,
            }
        )
    return _xlsx(reporter_xlsx(reports, sms_rows, story_rows), "reporter.xlsx")


@router.get("/excel/template")
async def excel_template(
    kind: str = Query("costs"),
    ctx: AuthContext = Depends(get_current_user),
):
    _read(ctx)
    name = "leads-template.xlsx" if kind == "leads" else "cost-template.xlsx"
    return _xlsx(blank_template("leads" if kind == "leads" else "costs"), name)


@router.post("/excel/costs")
async def import_costs(
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    parsed = parse_cost_rows(await file.read())
    existing = set(
        (
            await db.scalars(
                select(PmCost.cost_number).where(PmCost.organization_id == ctx.organization_id)
            )
        ).all()
    )
    added = 0
    for item in parsed:
        number = item["cost_number"]
        if number and number in existing:
            continue
        if not number:
            number = await next_cost_number(db, ctx.organization_id)
            existing.add(number)
        elif number:
            existing.add(number)
        db.add(
            PmCost(
                organization_id=ctx.organization_id,
                cost_number=number,
                spent_on=as_date(item["spent_on"]),
                amount_toman=item["amount_toman"],
                kind=item["kind"],
                detail=item["detail"],
                brand=item["brand"],
                campaign_code=item["campaign_code"],
                cost_center=item["cost_center"],
                description=item["description"],
                counts_for_cpl=item["kind"] != "ابزار/پلتفرم",
            )
        )
        added += 1
    await db.flush()
    return {"added": added}


@router.post("/leads/import")
async def import_leads(
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    campaigns = list(
        (await db.scalars(select(PmCampaign).where(PmCampaign.organization_id == ctx.organization_id))).all()
    )
    by_code = {row.code: row for row in campaigns}
    added = 0
    for item in parse_lead_rows(await file.read()):
        code = item["campaign_code"].strip()
        campaign = by_code.get(code)
        phone = normalize_phone(item["phone"]) or ""
        db.add(
            PmLead(
                organization_id=ctx.organization_id,
                campaign_id=campaign.id if campaign else None,
                phone=phone,
                occurred_on=as_date(item["occurred_on"]),
                campaign_code=code,
                channel=item["channel"],
                stage=item["stage"],
            )
        )
        added += 1
    await db.flush()
    return {"added": added}


@router.post("/integrations/isms")
async def isms_send(
    body: IsmsIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    panel = await _panel(db, ctx, body.panel_id)
    if panel.code != "isms":
        raise HTTPException(status_code=422, detail="این وب‌سرویس فقط برای پنل آی‌اس‌ام‌اس است")
    mobiles = []
    for raw in body.mobiles:
        phone = normalize_phone(raw)
        if phone:
            mobiles.append(phone[2:])
    try:
        return await send_isms_service(
            username=panel.api_username,
            password=decrypt_secret(panel.api_secret),
            sender=panel.sender_line,
            mobiles=mobiles,
            body=body.body,
        )
    except PerfError as exc:
        _fail(exc)


@router.post("/integrations/pishgam/send")
async def pishgam_send(
    body: PishgamSendIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    panel = await _panel(db, ctx, body.panel_id)
    from app.core.config import get_settings

    try:
        api_base, api_token = _panel_auth(panel)
        return await pishgam_call(
            api_base=api_base,
            token=api_token,
            path=get_settings().pishgam_send_path,
            method="POST",
            payload={"sender": panel.sender_line, "body": body.body, "mobiles": body.mobiles},
        )
    except PerfError as exc:
        _fail(exc)


@router.get("/integrations/pishgam/balance")
async def pishgam_balance(
    panel_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _read(ctx)
    panel = await _panel(db, ctx, panel_id)
    from app.core.config import get_settings

    try:
        api_base, api_token = _panel_auth(panel)
        return await pishgam_call(
            api_base=api_base,
            token=api_token,
            path=get_settings().pishgam_balance_path,
        )
    except PerfError as exc:
        _fail(exc)


@router.post("/integrations/pishgam/delivery")
async def pishgam_delivery(
    body: PishgamDeliveryIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """وضعیت دلیوری پیامک پیشگام با شناسهٔ ارسال در پنل خوانده می‌شود؛ فقط خواندن."""
    _read(ctx)
    panel = await _panel(db, ctx, body.panel_id) if body.panel_id else None
    if panel is None:
        raise HTTPException(status_code=422, detail="پنل انتخاب نشده است")
    from app.core.config import get_settings

    recipients = [str(number).strip() for number in body.recipients if str(number).strip()]
    if not body.message_id:
        raise HTTPException(status_code=422, detail="شناسهٔ ارسال را وارد کنید")
    if not recipients:
        raise HTTPException(status_code=422, detail="شمارهٔ گیرنده‌ای وارد نشده است")
    if len(recipients) > 100:
        raise HTTPException(status_code=422, detail="حداکثر ۱۰۰ گیرنده در هر درخواست پذیرفته می‌شود")
    try:
        api_base, api_token = _panel_auth(panel)
        result = await pishgam_call(
            api_base=api_base,
            token=api_token,
            path=get_settings().pishgam_report_path,
            method="POST",
            payload={"messageId": body.message_id, "recipientNumbers": recipients},
        )
    except PerfError as exc:
        _fail(exc)
    try:
        data = json.loads(result["body"]) if result["status_code"] == 200 else {}
    except ValueError:
        data = {}
    if int(data.get("statusCode") or 0) != 0:
        from app.perf.services.connections import pishgam_reason

        return {"ok": False, "reason": pishgam_reason(int(data.get("statusCode") or 0)), "rows": [], "delivered_count": 0}
    rows = [
        {
            "to_number": str(item.get("toNumber") or ""),
            "status": item.get("deliveryStatus"),
            "text": delivery_text(item.get("deliveryStatus")),
        }
        for item in data.get("numberDeliveryStatus") or []
    ]
    return {
        "ok": True,
        "reason": "",
        "rows": rows,
        "delivered_count": pishgam_delivered_count([row["status"] for row in rows]),
    }


@router.get("/connections")
async def connections(
    live: bool = False,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _read(ctx)
    return await connection_status(db, ctx.organization_id, live=live)


@router.put("/connections/mizito")
async def save_mizito(
    body: MizitoTokenIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    hint = await save_mizito_token(db, ctx.organization_id, body.token)
    return {"saved": bool(body.token.strip()), "hint": hint}


@router.get("/integrations/mizito")
async def read_mizito(
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """آخرین لیست ذخیره‌شده. با باز شدن صفحه به میزیتو وصل نمی‌شود."""
    _read(ctx)
    return await saved_mizito(db, ctx.organization_id)


@router.get("/integrations/mizito/missing")
async def read_mizito_missing(
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """کدهای کمپینِ کارت‌های میزیتو که در پنل نیستند. فقط از لیست ذخیره‌شده؛ به میزیتو وصل نمی‌شود."""
    _read(ctx)
    return await mizito_missing(db, ctx.organization_id)


@router.get("/integrations/mizito/finance")
async def read_mizito_finance(
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """پرداخت‌های پروژهٔ مالی میزیتو کنار Cost Tracking پنل. فقط خواندنی؛ تطبیق پیشنهادی است و هزینه‌ای ساخته نمی‌شود."""
    _read(ctx)
    return await mizito_finance(db, ctx.organization_id)


@router.get("/integrations/mizito/triage")
async def read_mizito_triage(
    days: int | None = Query(default=None),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """کارت‌های فعالی که رسیدگی می‌خواهند. فقط از لیست ذخیره‌شده؛ days بین ۱ و ۳۶۵ محدود می‌شود."""
    _read(ctx)
    return await mizito_triage(db, ctx.organization_id, days)


@router.get("/integrations/mizito/requests")
async def read_mizito_requests(
    status: str = Query(default="new"),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """پیش‌نویس‌های کمپین از درخواست‌های میزیتو (فقط از پایگاه دادهٔ پنل)."""
    _read(ctx)
    return await mizito_inbox.list_requests(db, ctx.organization_id, status)


@router.post("/integrations/mizito/requests/check")
async def check_mizito_requests(
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """«بررسی دوباره»: فقط خواندن از میزیتو (همان دسترسی «به‌روز از میزیتو»)؛ چیزی در میزیتو نوشته نمی‌شود."""
    _read(ctx)
    return await mizito_inbox.check_requests(db, ctx.organization_id)


async def _open_mizito_request(db: AsyncSession, ctx: AuthContext, request_id: UUID):
    row = await mizito_inbox.get_request(db, ctx.organization_id, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="درخواست پیدا نشد")
    if row.status not in ("new", "duplicate"):
        raise HTTPException(status_code=409, detail="این درخواست قبلاً بررسی شده است")
    return row


@router.post("/integrations/mizito/requests/{request_id}/approve")
async def approve_mizito_request(
    request_id: UUID,
    body: MizitoRequestApprove,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """کمپین واقعی با کد بعدی دفتر، از همان مسیر «کمپین تازه». فقط با تایید کاربر."""
    _write(ctx)
    row = await _open_mizito_request(db, ctx, request_id)
    if row.kind == "stop":
        raise HTTPException(status_code=422, detail="درخواست توقف کمپین تازه نمی‌سازد")
    draft = await mizito_inbox.one_out(db, row)
    hint = mizito_inbox.suggest(draft["fields"], row.kind)
    if hint["tag"] not in {item["tag"] for item in TAGS}:
        hint["tag"] = ""
    campaign = await create_campaign(
        CampaignIn(
            title=body.title.strip() or hint["title"] or "کمپین از درخواست میزیتو",
            tag=body.tag.strip() or hint["tag"],
            brand=body.brand.strip() or hint["brand"],
            goal=mizito_inbox.offer_summary(draft["fields"]),
            channels=body.channels or hint["channels"],
            status="active",
        ),
        ctx,
        db,
    )
    row.status = "approved"
    row.campaign_id = UUID(campaign["id"])
    row.decided_by = ctx.user.id
    row.decided_at = now()
    await db.flush()
    return {"request": await mizito_inbox.one_out(db, row), "campaign": campaign}


@router.post("/integrations/mizito/requests/{request_id}/reject")
async def reject_mizito_request(
    request_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await _open_mizito_request(db, ctx, request_id)
    row.status = "rejected"
    row.decided_by = ctx.user.id
    row.decided_at = now()
    await db.flush()
    return await mizito_inbox.one_out(db, row)


@router.post("/integrations/mizito/refresh")
async def refresh_mizito_cards(
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """کارت‌های باز را می‌خواند و لیست صفحهٔ پول را عوض می‌کند. چیزی در میزیتو نوشته نمی‌شود."""
    _read(ctx)
    return await refresh_mizito(db, ctx.organization_id)


@router.post("/integrations/sheets")
async def sync_sheets(
    body: SheetSyncIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    from app.perf.services.sync_lock import SyncBusy, begin_sync, finish_sync

    try:
        await begin_sync(db, ctx.organization_id, ctx.user.id, ctx.user.full_name)
    except SyncBusy as exc:
        raise HTTPException(status_code=409, detail=f"{exc.name} در حال به‌روزرسانی است") from exc
    try:
        state = await refresh_sheet(db, ctx.organization_id)
    except Exception:
        await finish_sync(db, ctx.organization_id, ok=False, error="خطا")
        raise
    err = state.reason or (state.sources.get("note") if isinstance(state.sources, dict) else "") or ""
    await finish_sync(db, ctx.organization_id, ok=bool(state.google_connected), error=err if not state.google_connected else "")
    if state.google_connected:
        return {
            "pushed": True,
            "spreadsheet_url": state.spreadsheet_url,
            "reason": state.reason,
            "sources": state.sources,
        }
    rows = list((await db.scalars(select(PmCost).where(PmCost.organization_id == ctx.organization_id))).all())
    payload = [_cost_dict(row) for row in rows]
    for item in payload:
        item["spent_on"] = iso(item["spent_on"])
    webhook = await push_sheet(body.kind, payload)
    if webhook.get("pushed"):
        return webhook
    return {"pushed": False, "reason": state.reason or webhook.get("reason", ""), "spreadsheet_url": state.spreadsheet_url}


def _send_out(row: PmSmsSend, code: str, panel_name: str = "") -> dict:
    return {
        "id": str(row.id),
        "campaign_id": str(row.campaign_id) if row.campaign_id else None,
        "campaign_code": code,
        "panel_id": str(row.panel_id) if row.panel_id else None,
        "panel_name": panel_name,
        "list_id": str(row.list_id) if row.list_id else None,
        "sender_line": row.sender_line,
        "body": row.body,
        "pages": row.pages,
        "recipient_count": row.recipient_count,
        "sent_at": iso(row.sent_at),
        "cost_toman": row.cost_toman,
        "delivered_count": row.delivered_count,
        "calls": row.calls,
        "leads": row.leads,
        "pishgam_message_id": row.pishgam_message_id,
    }


def _list_out(row: PmRecipientList) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "campaign_id": str(row.campaign_id) if row.campaign_id else None,
        "source_filename": row.source_filename,
        "raw_count": row.raw_count,
        "duplicate_count": row.duplicate_count,
        "blacklist_count": row.blacklist_count,
        "recent_count": row.recent_count,
        "invalid_count": row.invalid_count,
        "final_count": row.final_count,
        "recent_days": row.recent_days,
        "chunk_size": row.chunk_size,
        "created_at": iso(row.created_at),
    }


def _payment_out(row: PmPaymentRequest, requester_name: str = "") -> dict:
    return {
        "id": str(row.id),
        "kind": row.kind,
        "amount_toman": row.amount_toman,
        "beneficiary": row.beneficiary,
        "iban": mask_iban(decrypt_secret(row.iban)),
        "campaign_id": str(row.campaign_id) if row.campaign_id else None,
        "panel_id": str(row.panel_id) if row.panel_id else None,
        "story_id": str(row.story_id) if row.story_id else None,
        "cost_center": row.cost_center,
        "status": row.status,
        "mizito_url": row.mizito_url,
        "note": row.note,
        "requester_id": str(row.requester_id) if row.requester_id else None,
        "requester_name": requester_name,
        "project_id": str(row.project_id) if row.project_id else None,
        "request_id": str(row.request_id) if row.request_id else None,
        "team_id": str(row.team_id) if row.team_id else None,
        "created_at": iso(row.created_at),
    }


def _page_out(row: PmPage, cpl: float | None = None, cpv: float | None = None, prices: list | None = None) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "followers": row.followers,
        "topic": row.topic,
        "contact": row.contact,
        "price_toman": row.price_toman,
        "cpl": cpl,
        "cpv": cpv,
        "prices": prices or [],
    }


def _payments_by_story(rows: list[PmPaymentRequest]) -> dict[UUID, PmPaymentRequest]:
    found: dict[UUID, PmPaymentRequest] = {}
    ordered = sorted(rows, key=lambda item: item.created_at or now(), reverse=True)
    for row in ordered:
        if row.story_id and row.story_id not in found:
            found[row.story_id] = row
    return found


def _apply_insight(row: PmStory, fields: dict) -> None:
    for key in _INSIGHT_FIELDS:
        value = fields.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        setattr(row, key, int(value))


def _request_out(row: PmCarRequest) -> dict:
    return {
        "id": str(row.id),
        "raw_text": row.raw_text,
        "brand": row.brand,
        "summary": row.summary,
        "source": row.source,
        "status": row.status,
        "campaign_id": str(row.campaign_id) if row.campaign_id else None,
        "created_at": iso(row.created_at),
    }


def _story_out(row: PmStory, page: str, payment: PmPaymentRequest | None = None) -> dict:
    return {
        "id": str(row.id),
        "campaign_id": str(row.campaign_id) if row.campaign_id else None,
        "page_id": str(row.page_id) if row.page_id else None,
        "page": page,
        "kind": row.kind or "story",
        "status": row.status or "published",
        "payment_id": str(payment.id) if payment else None,
        "payment_status": payment.status if payment else "",
        "published_on": iso(row.published_on),
        "cost_toman": row.cost_toman,
        "views": row.views,
        "impressions": row.impressions,
        "reach": row.reach,
        "likes": row.likes,
        "replies": row.replies,
        "shares": row.shares,
        "link_clicks": row.link_clicks,
        "exited": row.exited,
        "leads": row.leads,
        "attachment_name": row.attachment_name,
        **story_rates(row),
    }


@router.patch("/costs/{cost_id}")
async def patch_cost(
    cost_id: UUID,
    body: CostPatch,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await db.get(PmCost, cost_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="هزینه پیدا نشد")
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value.strip() if isinstance(value, str) else value)
    await db.flush()
    return _cost_dict(row)


@router.delete("/costs/{cost_id}", status_code=204)
async def delete_cost(
    cost_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _write(ctx)
    row = await db.get(PmCost, cost_id)
    if not row or row.organization_id != ctx.organization_id:
        raise HTTPException(status_code=404, detail="هزینه پیدا نشد")
    await db.delete(row)
    await db.flush()
    return Response(status_code=204)


def _cost_dict(row: PmCost) -> dict:
    return {
        "id": str(row.id),
        "cost_number": row.cost_number,
        "spent_on": row.spent_on,
        "amount_toman": row.amount_toman,
        "kind": row.kind,
        "detail": row.detail,
        "brand": row.brand,
        "campaign_code": row.campaign_code,
        "cost_center": row.cost_center,
        "description": row.description,
    }


@router.get("/pishgam/targeting")
async def pishgam_targeting(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """محله‌ها، شمار مسیرها و مرجع ذخیره‌شده. به پیشگام کال نمی‌زند."""
    _read(ctx)
    from app.perf.services.pishgam_targeting import snapshot

    return await snapshot(db, ctx.organization_id)


@router.post("/pishgam/targeting/sync")
async def pishgam_targeting_sync(ctx: AuthContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """فقط استان، شهر، برند و نوع دستگاه را می‌خواند. ارسال و ساخت درخواست اینجا نیست."""
    _write(ctx)
    from app.perf.services.pishgam_targeting import sync_reference

    try:
        saved = await sync_reference(db, organization_id=ctx.organization_id, actor_id=ctx.user.id)
    except PerfError as exc:
        _fail_targeting(exc)
    return saved


@router.post("/pishgam/targeting/check-polygons")
async def pishgam_check_polygons(
    body: AreaKeysIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """پلیگان محله‌های تیک‌خورده را با CheckPolygonCells می‌سنجد. ساخت و ارسال نمی‌کند."""
    _write(ctx)
    from app.perf.services.pishgam_targeting import check_polygons

    try:
        return await check_polygons(
            db,
            organization_id=ctx.organization_id,
            actor_id=ctx.user.id,
            keys=body.keys,
            operators=body.operators,
        )
    except PerfError as exc:
        _fail_targeting(exc)


@router.post("/pishgam/targeting/preview")
async def pishgam_preview_audience(
    body: PreviewAudienceIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """شمارش مخاطب را در پس‌زمینه شروع می‌کند یا کش را برمی‌گرداند. SendSimpleSmartSms اینجا نیست."""
    _write(ctx)
    from app.perf.services.pishgam_targeting import preview_audience

    try:
        return await preview_audience(
            db,
            organization_id=ctx.organization_id,
            actor_id=ctx.user.id,
            body=body,
        )
    except PerfError as exc:
        _fail_targeting(exc)



