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


@router.post("/sync")
async def sync_sheets(
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_any_permission(
            ctx.permissions,
            PermissionCode.CAMPAIGN_WRITE,
            PermissionCode.PRICE_WRITE,
            PermissionCode.ORG_ADMIN,
        )
    except AuthorizationError as exc:
        raise handle_authz(exc) from exc
    try:
        result = await sync_performance_sheets(db, ctx.organization_id)
    except SheetsError as exc:
        raise HTTPException(exc.status, exc.message) from exc
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
