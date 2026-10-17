"""همگام‌سازی GET-only سوشال → rollup + ردیف روزانه."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.perf.models import PmIntegration, PmSocialDaily, PmSocialSyncRun
from app.perf.services.common import iso, now
from app.perf.services.connections import novinhub_token_for, vardast_token_for
from app.perf.services.social_analytics import social_overview


def _rollup_to_daily_fields(rollup: dict) -> dict:
    nh = rollup.get("novinhub") if isinstance(rollup.get("novinhub"), dict) else {}
    vd = rollup.get("vardast") if isinstance(rollup.get("vardast"), dict) else {}
    usage = vd.get("usage") if isinstance(vd.get("usage"), dict) else {}
    chat_credit = usage.get("chat_credit")
    if isinstance(chat_credit, bool) or chat_credit is None:
        credit_val = None
    else:
        try:
            credit_val = int(chat_credit)
        except (TypeError, ValueError):
            credit_val = None
    metrics = {
        "comments_by_status": nh.get("comments_by_status"),
        "conversations_by_status": nh.get("conversations_by_status"),
        "fetched_at": rollup.get("fetched_at"),
    }
    return {
        "comments_open_est": int(nh.get("comments_open_est") or 0),
        "conversations_open_est": int(nh.get("conversations_open_est") or 0),
        "comments_sampled": int(nh.get("comments_sampled") or 0),
        "conversations_sampled": int(nh.get("conversations_sampled") or 0),
        "accounts_needing_login": int(nh.get("accounts_needing_login") or 0),
        "vardast_chat_credit": credit_val,
        "vardast_channel_count": int(vd.get("channel_count") or 0),
        "metrics_json": json.dumps(metrics, ensure_ascii=False),
    }


async def org_has_social_tokens(db: AsyncSession, organization_id: UUID) -> bool:
    nh = (await novinhub_token_for(db, organization_id)).strip()
    vd = (await vardast_token_for(db, organization_id)).strip()
    return bool(nh or vd)


async def run_org_social_sync(db: AsyncSession, organization_id: UUID) -> dict:
    """یک بار GET + rollup + upsert امروز. بدون POST به نوین‌هاب/وردست."""
    run = PmSocialSyncRun(organization_id=organization_id, started_at=now())
    db.add(run)
    await db.flush()
    if not await org_has_social_tokens(db, organization_id):
        run.ok = False
        run.error_message = "توکن نوین‌هاب یا وردست ذخیره نشده است."
        run.finished_at = now()
        return {"ok": False, "reason": run.error_message}
    try:
        overview = await social_overview(db, organization_id, refresh=True)
        fields = _rollup_to_daily_fields(overview)
        day = now().date()
        row = await db.scalar(
            select(PmSocialDaily).where(
                PmSocialDaily.organization_id == organization_id,
                PmSocialDaily.day == day,
            )
        )
        if row is None:
            row = PmSocialDaily(organization_id=organization_id, day=day, **fields)
            db.add(row)
        else:
            for key, val in fields.items():
                setattr(row, key, val)
        run.ok = True
        run.finished_at = now()
        await db.flush()
        return {"ok": True, "day": day.isoformat(), "rollup_at": overview.get("rollup_at")}
    except Exception as exc:  # noqa: BLE001 — logged on run row
        run.ok = False
        run.error_message = str(exc)[:500]
        run.finished_at = now()
        return {"ok": False, "reason": run.error_message}


async def run_all_social_sync(db: AsyncSession) -> dict:
    org_ids = list(await db.scalars(select(PmIntegration.organization_id)))
    synced = 0
    for organization_id in org_ids:
        if not await org_has_social_tokens(db, organization_id):
            continue
        result = await run_org_social_sync(db, organization_id)
        if result.get("ok"):
            synced += 1
    return {"orgs": synced}


async def last_sync_at(db: AsyncSession, organization_id: UUID) -> str | None:
    row = await db.scalar(
        select(PmIntegration).where(PmIntegration.organization_id == organization_id)
    )
    if row and row.social_rollup_at:
        return iso(row.social_rollup_at)
    run = await db.scalar(
        select(PmSocialSyncRun)
        .where(PmSocialSyncRun.organization_id == organization_id, PmSocialSyncRun.ok.is_(True))
        .order_by(PmSocialSyncRun.finished_at.desc())
        .limit(1)
    )
    if run and run.finished_at:
        return iso(run.finished_at)
    return None
