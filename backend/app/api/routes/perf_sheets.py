"""Button-triggered sync of performance-marketing Google Sheets."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, handle_authz
from app.core.permissions import AuthorizationError, PermissionCode, require_any_permission
from app.db.session import get_db
from app.perf.services.sheets_sync import SheetsError, failure_text, sync_performance_sheets
from app.services import write_audit

router = APIRouter(prefix="/perf/sheets", tags=["perf-sheets"])


def _may_see_sheets(ctx: AuthContext) -> None:
    try:
        require_any_permission(
            ctx.permissions,
            PermissionCode.CAMPAIGN_READ,
            PermissionCode.CAMPAIGN_WRITE,
            PermissionCode.PRICE_APPROVE,
            PermissionCode.PRICE_WRITE,
            PermissionCode.PERF_READ,
            PermissionCode.PERF_WRITE,
            PermissionCode.ORG_ADMIN,
        )
    except AuthorizationError as exc:
        raise handle_authz(exc) from exc


@router.get("/status")
async def sheets_status(
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _may_see_sheets(ctx)
    from app.perf.services.sync_lock import sync_status

    return await sync_status(db, ctx.organization_id)


@router.post("/sync")
async def sync_sheets(
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_any_permission(
            ctx.permissions,
            PermissionCode.CAMPAIGN_WRITE,
            PermissionCode.PRICE_APPROVE,
            PermissionCode.PRICE_WRITE,
            PermissionCode.ORG_ADMIN,
        )
    except AuthorizationError as exc:
        raise handle_authz(exc) from exc
    from app.perf.services.sync_lock import SyncBusy, begin_sync, finish_sync

    try:
        await begin_sync(db, ctx.organization_id, ctx.user.id, ctx.user.full_name)
    except SyncBusy as exc:
        raise HTTPException(status_code=409, detail=f"{exc.name} در حال به‌روزرسانی است") from exc
    try:
        result = await sync_performance_sheets(db, ctx.organization_id)
    except SheetsError as exc:
        await finish_sync(db, ctx.organization_id, ok=False, error=exc.message)
        raise HTTPException(exc.status, exc.message) from exc
    except Exception:
        await finish_sync(db, ctx.organization_id, ok=False, error="خطا")
        raise
    await finish_sync(db, ctx.organization_id, ok=bool(result.get("ok")))
    updated = [item for item in result["targets"] if item["updated"]]
    if not result["ok"] and not updated:
        raise HTTPException(status_code=502, detail=failure_text(result))
    await write_audit(
        db,
        organization_id=ctx.organization_id,
        actor_id=ctx.user.id,
        action="perf.sheets.sync",
        entity_type="organization",
        entity_id=ctx.organization_id,
        details={
            "ok": result["ok"],
            "updated": [item["key"] for item in updated],
            "skipped": [item["env"] for item in result["skipped"]],
            "errors": [item["error"] for item in result["targets"] if item["error"]],
        },
    )
    return result
