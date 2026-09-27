"""Customer CRM service."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import PermissionCode, require_permission
from app.models.customer import Customer


class CustomerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        organization_id: UUID,
        full_name: str,
        actor_id: UUID,
        actor_permissions: set[str],
        phone: str | None = None,
        email: str | None = None,
        notes: str | None = None,
    ) -> Customer:
        require_permission(actor_permissions, PermissionCode.CUSTOMER_WRITE)
        customer = Customer(
            organization_id=organization_id,
            full_name=full_name.strip(),
            phone=phone.strip() if phone else None,
            email=email.strip().lower() if email else None,
            notes=notes,
            created_by=actor_id,
        )
        self.db.add(customer)
        await self.db.flush()
        return customer

    async def get(self, customer_id: UUID) -> Customer | None:
        return await self.db.get(Customer, customer_id)

    async def search(
        self,
        organization_id: UUID,
        *,
        q: str | None = None,
        limit: int = 50,
    ) -> list[Customer]:
        query = select(Customer).where(Customer.organization_id == organization_id)
        if q:
            like = f"%{q}%"
            query = query.where(
                or_(
                    Customer.full_name.ilike(like),
                    Customer.phone.ilike(like),
                    Customer.email.ilike(like),
                )
            )
        result = await self.db.execute(query.order_by(Customer.created_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def update(
        self,
        *,
        customer_id: UUID,
        actor_permissions: set[str],
        full_name: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        notes: str | None = None,
    ) -> Customer:
        require_permission(actor_permissions, PermissionCode.CUSTOMER_WRITE)
        customer = await self.get(customer_id)
        if not customer:
            raise ValueError("Customer not found")
        if full_name is not None:
            customer.full_name = full_name.strip()
        if phone is not None:
            customer.phone = phone.strip() or None
        if email is not None:
            customer.email = email.strip().lower() or None
        if notes is not None:
            customer.notes = notes
        await self.db.flush()
        return customer

    def to_dict(self, c: Customer) -> dict[str, Any]:
        return {
            "id": str(c.id),
            "full_name": c.full_name,
            "phone": c.phone,
            "email": c.email,
            "notes": c.notes,
        }
