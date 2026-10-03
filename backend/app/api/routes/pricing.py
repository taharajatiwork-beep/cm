"""تأیید قیمت پست و تابلوی امروز."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, handle_authz
from app.core.permissions import AuthorizationError, PermissionCode, require_any_permission, require_permission
from app.db.session import get_db
from app.models.inventory import Vehicle
from app.services.pricing import PricingService

router = APIRouter(prefix="/pricing", tags=["pricing"])


class SlotIn(BaseModel):
    vehicle_id: UUID
    post_at: datetime
    slot_type: str = "video"
    channel: str | None = None


class ConfirmIn(BaseModel):
    amount: int | None = None


def _slot_out(slot, vehicle: Vehicle | None) -> dict:
    return {
        "id": str(slot.id),
        "vehicle_id": str(slot.vehicle_id),
        "brand": vehicle.brand if vehicle else None,
        "model": vehicle.model if vehicle else None,
        "color": vehicle.color if vehicle else None,
        "post_at": slot.post_at.isoformat() if slot.post_at else None,
        "slot_type": slot.slot_type,
        "channel": slot.channel,
        "status": slot.status,
        "confirmed_price": slot.confirmed_price,
        "sale_price": vehicle.sale_price if vehicle else None,
        "requester_id": str(slot.requester_id),
        "confirmed_at": slot.confirmed_at.isoformat() if slot.confirmed_at else None,
    }


@router.get("/board")
async def board(
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_any_permission(ctx.permissions, PermissionCode.PRICE_WRITE, PermissionCode.CAMPAIGN_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    now = datetime.now(UTC)
    svc = PricingService(db)
    slots = await svc.list_slots(ctx.organization_id, day=now)
    vehicles = list(
        (await db.scalars(select(Vehicle).where(Vehicle.organization_id == ctx.organization_id))).all()
    )
    by_id = {v.id: v for v in vehicles}
    waiting = [s for s in slots if s.status in ("requested", "needs_recheck")]
    return {
        "slots": [_slot_out(s, by_id.get(s.vehicle_id)) for s in slots],
        "waiting": len(waiting),
        "today_total": len(slots),
        "missing_price": len([s for s in slots if s.status in ("requested", "needs_recheck")]),
        "all_priced": len(slots) > 0 and len([s for s in slots if s.status in ("requested", "needs_recheck")]) == 0,
        "vehicles": [
            {
                "id": str(v.id),
                "brand": v.brand,
                "model": v.model,
                "color": v.color,
                "year": v.year,
                "status": v.status.value if hasattr(v.status, "value") else v.status,
                "sale_price": v.sale_price,
                "mileage": v.mileage,
                "delivery_note": v.delivery_note,
                "branch_id": str(v.branch_id) if v.branch_id else None,
                "price_updated_at": v.price_updated_at.isoformat() if v.price_updated_at else None,
                "price_updated_by": str(v.price_updated_by) if v.price_updated_by else None,
                "stock_updated_at": v.stock_updated_at.isoformat() if v.stock_updated_at else None,
                "stock_updated_by": str(v.stock_updated_by) if v.stock_updated_by else None,
            }
            for v in vehicles
        ],
    }


@router.get("/slots")
async def list_slots(
    day: datetime | None = Query(default=None),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_any_permission(ctx.permissions, PermissionCode.PRICE_WRITE, PermissionCode.CAMPAIGN_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    slots = await PricingService(db).list_slots(ctx.organization_id, day=day)
    vehicles = {
        v.id: v
        for v in (await db.scalars(select(Vehicle).where(Vehicle.organization_id == ctx.organization_id))).all()
    }
    return [_slot_out(s, vehicles.get(s.vehicle_id)) for s in slots]


@router.post("/slots")
async def request_slot(
    body: SlotIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        slot = await PricingService(db).request_slot(
            organization_id=ctx.organization_id,
            vehicle_id=body.vehicle_id,
            post_at=body.post_at,
            requester_id=ctx.user.id,
            actor_permissions=ctx.permissions,
            slot_type=body.slot_type,
            channel=body.channel,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    vehicle = await db.get(Vehicle, slot.vehicle_id)
    return _slot_out(slot, vehicle)


@router.post("/slots/{slot_id}/confirm")
async def confirm_slot(
    slot_id: UUID,
    body: ConfirmIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        slot = await PricingService(db).confirm_slot(
            organization_id=ctx.organization_id,
            slot_id=slot_id,
            actor_id=ctx.user.id,
            actor_permissions=ctx.permissions,
            amount=body.amount,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    vehicle = await db.get(Vehicle, slot.vehicle_id)
    return _slot_out(slot, vehicle)


@router.post("/slots/{slot_id}/posted")
async def mark_posted(
    slot_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        slot = await PricingService(db).mark_posted(
            organization_id=ctx.organization_id,
            slot_id=slot_id,
            actor_permissions=ctx.permissions,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    vehicle = await db.get(Vehicle, slot.vehicle_id)
    return _slot_out(slot, vehicle)
