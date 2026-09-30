import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, handle_authz
from app.api.pagination import page
from app.core.permissions import AuthorizationError, PermissionCode, require_permission
from app.db.session import get_db
from app.models import CommunicationCase, Event, WorkItem
from app.services import write_audit
from app.services.customer import CustomerService

router = APIRouter(prefix="/customers", tags=["customers"])


class CustomerCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    phone: str | None = None
    email: str | None = None
    notes: str | None = None


class CustomerUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = None
    email: str | None = None
    notes: str | None = None
    stage: str | None = None


class CustomerOut(BaseModel):
    id: UUID
    organization_id: UUID
    full_name: str
    phone: str | None
    email: str | None
    notes: str | None
    stage: str = "lead"

    model_config = {"from_attributes": True}


def _status_value(status: Any) -> str | None:
    """مقدار خوانای enum وضعیت؛ اگر None یا بدون value بود، None برمی‌گرداند."""
    if status is None:
        return None
    value = getattr(status, "value", status)
    return value if isinstance(value, str) else None


@router.post("", response_model=CustomerOut)
async def create_customer(
    body: CustomerCreate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await CustomerService(db).create(
            organization_id=ctx.organization_id,
            full_name=body.full_name,
            actor_id=ctx.user.id,
            actor_permissions=ctx.permissions,
            phone=body.phone,
            email=body.email,
            notes=body.notes,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e


@router.get("", response_model=list[CustomerOut])
async def list_customers(
    q: str | None = None,
    envelope: bool = False,
    cursor: str | None = None,
    limit: int = 20,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.CUSTOMER_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    rows = await CustomerService(db).search(ctx.organization_id, q=q, scope=ctx.scope)
    if envelope:
        dumped = [CustomerOut.model_validate(row).model_dump(mode="json") for row in rows]
        return JSONResponse(page(dumped, cursor=cursor, limit=limit))
    return rows


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(
    customer_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.CUSTOMER_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    customer = await CustomerService(db).get(customer_id)
    if not customer or customer.organization_id != ctx.organization_id:
        raise HTTPException(404, "Customer not found")
    return customer


@router.patch("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: UUID,
    body: CustomerUpdate,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        customer = await CustomerService(db).get(customer_id)
        if not customer or customer.organization_id != ctx.organization_id:
            raise HTTPException(404, "Customer not found")
        previous_stage = customer.stage
        updated = await CustomerService(db).update(
            customer_id=customer_id,
            actor_permissions=ctx.permissions,
            full_name=body.full_name,
            phone=body.phone,
            email=body.email,
            notes=body.notes,
            stage=body.stage,
        )
        if body.stage is not None and updated.stage != previous_stage:
            db.add(
                Event(
                    organization_id=ctx.organization_id,
                    event_type="customer.stage",
                    actor_id=ctx.user.id,
                    entity_type="customer",
                    entity_id=updated.id,
                    payload=json.dumps(
                        {"from": previous_stage, "to": updated.stage},
                        ensure_ascii=False,
                    ),
                )
            )
        return updated
    except AuthorizationError as e:
        raise handle_authz(e) from e
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


async def _get_owned_customer(
    customer_id: UUID, ctx: AuthContext, db: AsyncSession
):
    customer = await CustomerService(db).get(customer_id)
    if not customer or customer.organization_id != ctx.organization_id:
        raise HTTPException(404, "Customer not found")
    return customer


@router.get("/{customer_id}/export")
async def export_customer(
    customer_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """خروجی کامل مشتری: پروفایل + caseها + کارهای مرتبط (مرحله ۶)."""
    try:
        require_permission(ctx.permissions, PermissionCode.CUSTOMER_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    customer = await _get_owned_customer(customer_id, ctx, db)
    cases = list(
        (
            await db.execute(
                select(CommunicationCase).where(
                    CommunicationCase.organization_id == ctx.organization_id,
                    CommunicationCase.customer_id == customer.id,
                )
            )
        ).scalars()
    )
    work_items = list(
        (
            await db.execute(
                select(WorkItem).where(
                    WorkItem.organization_id == ctx.organization_id,
                    WorkItem.customer_id == customer.id,
                )
            )
        ).scalars()
    )
    await write_audit(
        db,
        organization_id=ctx.organization_id,
        actor_id=ctx.user.id,
        action="customer.export",
        entity_type="customer",
        entity_id=customer.id,
        details={"cases": len(cases), "work_items": len(work_items)},
    )
    return {
        "customer": {
            "id": str(customer.id),
            "full_name": customer.full_name,
            "phone": customer.phone,
            "email": customer.email,
            "notes": customer.notes,
        },
        "cases": [
            {
                "id": str(c.id),
                "subject": c.subject,
                "status": _status_value(getattr(c, "status", None)),
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in cases
        ],
        "work_items": [
            {
                "id": str(w.id),
                "title": w.title,
                "status": w.status.value if w.status else None,
                "created_at": w.created_at.isoformat() if w.created_at else None,
            }
            for w in work_items
        ],
    }


@router.post("/{customer_id}/erase")
async def erase_customer(
    customer_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """پاک‌سازی حریم خصوصی فقط برای org.admin؛ رکورد حذف نمی‌شود (مرحله ۶)."""
    try:
        require_permission(ctx.permissions, PermissionCode.ORG_ADMIN)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    customer = await _get_owned_customer(customer_id, ctx, db)
    customer.full_name = "حذف‌شده"
    customer.phone = None
    customer.email = None
    customer.notes = None
    await write_audit(
        db,
        organization_id=ctx.organization_id,
        actor_id=ctx.user.id,
        action="customer.erased",
        entity_type="customer",
        entity_id=customer.id,
        details={"kept_row": True},
    )
    return {"id": str(customer.id), "erased": True}
