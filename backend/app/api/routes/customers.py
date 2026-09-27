from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, handle_authz
from app.core.permissions import AuthorizationError, PermissionCode, require_permission
from app.db.session import get_db
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


class CustomerOut(BaseModel):
    id: UUID
    organization_id: UUID
    full_name: str
    phone: str | None
    email: str | None
    notes: str | None

    model_config = {"from_attributes": True}


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
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_permission(ctx.permissions, PermissionCode.CUSTOMER_READ)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return await CustomerService(db).search(ctx.organization_id, q=q)


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
        return await CustomerService(db).update(
            customer_id=customer_id,
            actor_permissions=ctx.permissions,
            full_name=body.full_name,
            phone=body.phone,
            email=body.email,
            notes=body.notes,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
