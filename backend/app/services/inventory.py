from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.permissions import PermissionCode, require_permission
from app.models import CommunicationCase, Event, WorkItem
from app.models.enums import (
    CaseStatus,
    CaseType,
    InventoryRequestStatus,
    InventoryRequestType,
    VehicleStatus,
)
from app.models.inventory import InventoryRequest, Vehicle, VehicleBranch, VehicleHistory


async def _emit(
    db: AsyncSession,
    *,
    organization_id: UUID,
    event_type: str,
    entity_type: str,
    entity_id: UUID,
    actor_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> Event:
    event = Event(
        organization_id=organization_id,
        event_type=event_type,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=json.dumps(payload) if payload else None,
    )
    db.add(event)
    await db.flush()
    return event


class InventoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_vehicle(
        self,
        *,
        organization_id: UUID,
        vin: str,
        brand: str,
        model: str,
        year: int,
        actor_id: UUID,
        actor_permissions: set[str] | None = None,
        stock_number: str | None = None,
        color: str | None = None,
        trim: str | None = None,
        mileage: int | None = None,
        purchase_price: int | None = None,
        sale_price: int | None = None,
        currency: str = "IRR",
        description: str | None = None,
        notes: str | None = None,
        body_type: str | None = None,
        transmission: str | None = None,
        fuel_type: str | None = None,
        engine: str | None = None,
        plate_number: str | None = None,
        doors: int | None = None,
        seats: int | None = None,
        options: str | None = None,
        exterior_condition: str | None = None,
        interior_condition: str | None = None,
        import_source: str | None = None,
        branch_id: UUID | None = None,
        owner_id: UUID | None = None,
        status: VehicleStatus = VehicleStatus.IN_STOCK,
    ) -> Vehicle:
        if actor_permissions is not None:
            require_permission(actor_permissions, PermissionCode.INVENTORY_WRITE)
        vehicle = Vehicle(
            organization_id=organization_id,
            vin=vin.upper(),
            brand=brand,
            model=model,
            year=year,
            stock_number=stock_number,
            color=color,
            trim=trim,
            mileage=mileage,
            purchase_price=purchase_price,
            sale_price=sale_price,
            currency=currency,
            description=description,
            notes=notes,
            body_type=body_type,
            transmission=transmission,
            fuel_type=fuel_type,
            engine=engine,
            plate_number=plate_number,
            doors=doors,
            seats=seats,
            options=options,
            exterior_condition=exterior_condition,
            interior_condition=interior_condition,
            import_source=import_source,
            branch_id=branch_id,
            owner_id=owner_id or actor_id,
            status=status,
        )
        self.db.add(vehicle)
        await self.db.flush()
        self.db.add(
            VehicleHistory(
                vehicle_id=vehicle.id,
                organization_id=organization_id,
                actor_id=actor_id,
                from_status=None,
                to_status=status,
                note="Vehicle created",
            )
        )
        if branch_id:
            self.db.add(
                VehicleBranch(
                    vehicle_id=vehicle.id,
                    branch_id=branch_id,
                    is_primary=True,
                )
            )
        await self.db.flush()
        await _emit(
            self.db,
            organization_id=organization_id,
            event_type="vehicle.created",
            actor_id=actor_id,
            entity_type="vehicle",
            entity_id=vehicle.id,
            payload={"vin": vehicle.vin, "brand": brand, "model": model, "stock_number": stock_number},
        )
        return vehicle

    async def get_vehicle(self, vehicle_id: UUID) -> Vehicle | None:
        return await self.db.scalar(
            select(Vehicle)
            .options(
                selectinload(Vehicle.history),
                selectinload(Vehicle.branch_links),
            )
            .where(Vehicle.id == vehicle_id)
        )

    async def search_vehicles(
        self,
        organization_id: UUID,
        *,
        brand: str | None = None,
        model: str | None = None,
        branch_id: UUID | None = None,
        status: VehicleStatus | None = None,
        vin: str | None = None,
        stock_number: str | None = None,
        q: str | None = None,
        scope=None,
    ) -> list[Vehicle]:
        from app.core.scope import apply_scope

        query = select(Vehicle).where(Vehicle.organization_id == organization_id)
        query = apply_scope(query, Vehicle, scope)
        if brand:
            query = query.where(Vehicle.brand.ilike(f"%{brand}%"))
        if model:
            query = query.where(Vehicle.model.ilike(f"%{model}%"))
        if branch_id:
            query = query.where(Vehicle.branch_id == branch_id)
        if status:
            query = query.where(Vehicle.status == status)
        if vin:
            query = query.where(Vehicle.vin == vin.upper())
        if stock_number:
            query = query.where(Vehicle.stock_number == stock_number)
        if q:
            like = f"%{q}%"
            query = query.where(
                or_(
                    Vehicle.brand.ilike(like),
                    Vehicle.model.ilike(like),
                    Vehicle.vin.ilike(like),
                    Vehicle.stock_number.ilike(like),
                    Vehicle.color.ilike(like),
                    Vehicle.trim.ilike(like),
                    Vehicle.plate_number.ilike(like),
                    Vehicle.description.ilike(like),
                    Vehicle.options.ilike(like),
                )
            )
        result = await self.db.execute(query.order_by(Vehicle.created_at.desc()))
        return list(result.scalars().all())

    async def change_status(
        self,
        *,
        vehicle_id: UUID,
        to_status: VehicleStatus,
        actor_id: UUID,
        actor_permissions: set[str],
        note: str | None = None,
    ) -> Vehicle:
        require_permission(actor_permissions, PermissionCode.INVENTORY_WRITE)
        vehicle = await self.db.get(Vehicle, vehicle_id)
        if not vehicle:
            raise ValueError("Vehicle not found")
        from_status = vehicle.status
        vehicle.status = to_status
        self.db.add(
            VehicleHistory(
                vehicle_id=vehicle.id,
                organization_id=vehicle.organization_id,
                actor_id=actor_id,
                from_status=from_status,
                to_status=to_status,
                note=note,
            )
        )
        await self.db.flush()
        await _emit(
            self.db,
            organization_id=vehicle.organization_id,
            event_type="vehicle.status_changed",
            actor_id=actor_id,
            entity_type="vehicle",
            entity_id=vehicle.id,
            payload={
                "from_status": from_status.value,
                "to_status": to_status.value,
                "note": note,
            },
        )
        return vehicle

    async def link_branch(
        self,
        *,
        vehicle_id: UUID,
        branch_id: UUID,
        actor_id: UUID,
        is_primary: bool = False,
        note: str | None = None,
    ) -> VehicleBranch:
        vehicle = await self.db.get(Vehicle, vehicle_id)
        if not vehicle:
            raise ValueError("Vehicle not found")
        link = VehicleBranch(
            vehicle_id=vehicle_id,
            branch_id=branch_id,
            is_primary=is_primary,
            note=note,
        )
        self.db.add(link)
        if is_primary:
            vehicle.branch_id = branch_id
        await self.db.flush()
        await _emit(
            self.db,
            organization_id=vehicle.organization_id,
            event_type="vehicle.branch_linked",
            actor_id=actor_id,
            entity_type="vehicle",
            entity_id=vehicle.id,
            payload={"branch_id": str(branch_id), "is_primary": is_primary},
        )
        return link

    async def create_inventory_request(
        self,
        *,
        organization_id: UUID,
        requesting_branch_id: UUID,
        requested_by: UUID,
        subject: str,
        vehicle_id: UUID | None = None,
        target_branch_id: UUID | None = None,
        request_type: InventoryRequestType = InventoryRequestType.GENERAL,
        notes: str | None = None,
        work_item_id: UUID | None = None,
        case_id: UUID | None = None,
        actor_permissions: set[str] | None = None,
    ) -> InventoryRequest:
        if actor_permissions is not None:
            require_permission(actor_permissions, PermissionCode.INVENTORY_WRITE)
        req = InventoryRequest(
            organization_id=organization_id,
            vehicle_id=vehicle_id,
            requesting_branch_id=requesting_branch_id,
            target_branch_id=target_branch_id,
            requested_by=requested_by,
            request_type=request_type,
            subject=subject,
            notes=notes,
            work_item_id=work_item_id,
            case_id=case_id,
            status=InventoryRequestStatus.OPEN,
        )
        self.db.add(req)
        await self.db.flush()
        await _emit(
            self.db,
            organization_id=organization_id,
            event_type="inventory_request.created",
            actor_id=requested_by,
            entity_type="inventory_request",
            entity_id=req.id,
            payload={"subject": subject, "vehicle_id": str(vehicle_id) if vehicle_id else None},
        )
        return req

    async def vehicle_context(self, vehicle_id: UUID) -> dict[str, Any]:
        """Open work items, cases, and history for a vehicle page."""
        vehicle = await self.get_vehicle(vehicle_id)
        if not vehicle:
            raise ValueError("Vehicle not found")
        work_items = list(
            (
                await self.db.execute(
                    select(WorkItem).where(WorkItem.vehicle_id == vehicle_id)
                )
            ).scalars().all()
        )
        cases = list(
            (
                await self.db.execute(
                    select(CommunicationCase).where(CommunicationCase.vehicle_id == vehicle_id)
                )
            ).scalars().all()
        )
        requests = list(
            (
                await self.db.execute(
                    select(InventoryRequest).where(InventoryRequest.vehicle_id == vehicle_id)
                )
            ).scalars().all()
        )
        return {
            "vehicle": vehicle,
            "work_items": work_items,
            "cases": cases,
            "inventory_requests": requests,
            "history": vehicle.history,
        }

    async def list_aging_vehicles(
        self,
        organization_id: UUID,
        *,
        min_days: int = 30,
        status: VehicleStatus = VehicleStatus.IN_STOCK,
    ) -> list[dict[str, Any]]:
        """Vehicles in stock longer than min_days (aging signal)."""
        cutoff = datetime.now(UTC) - timedelta(days=min_days)
        rows = list(
            (
                await self.db.execute(
                    select(Vehicle)
                    .where(
                        Vehicle.organization_id == organization_id,
                        Vehicle.status == status,
                        Vehicle.created_at <= cutoff,
                    )
                    .order_by(Vehicle.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        now = datetime.now(UTC)
        out: list[dict[str, Any]] = []
        for v in rows:
            created = v.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            days = max(0, (now - created).days)
            out.append(
                {
                    "id": str(v.id),
                    "vin": v.vin,
                    "brand": v.brand,
                    "model": v.model,
                    "stock_number": v.stock_number,
                    "status": v.status.value,
                    "branch_id": str(v.branch_id) if v.branch_id else None,
                    "days_in_stock": days,
                    "created_at": created.isoformat(),
                }
            )
        return out

    async def list_open_requests(
        self,
        organization_id: UUID,
        *,
        vehicle_id: UUID | None = None,
    ) -> list[InventoryRequest]:
        q = select(InventoryRequest).where(
            InventoryRequest.organization_id == organization_id,
            InventoryRequest.status == InventoryRequestStatus.OPEN,
        )
        if vehicle_id:
            q = q.where(InventoryRequest.vehicle_id == vehicle_id)
        return list((await self.db.execute(q.order_by(InventoryRequest.created_at.desc()))).scalars().all())

    async def detect_opportunities(
        self,
        organization_id: UUID,
        *,
        min_days: int = 30,
        min_branch_requests: int = 2,
    ) -> list[dict[str, Any]]:
        """Aged stock + branch demand and/or customer interest → opportunity candidates.

        Opportunity when days_in_stock >= min_days AND (
          distinct requesting branches >= min_branch_requests
          OR open CUSTOMER_INTEREST cases exist
        ). Skips vehicles that already have an open INVENTORY_OPPORTUNITY case.
        """
        aging = await self.list_aging_vehicles(organization_id, min_days=min_days)
        if not aging:
            return []

        open_opp_vehicle_ids = set(
            (
                await self.db.execute(
                    select(CommunicationCase.vehicle_id).where(
                        CommunicationCase.organization_id == organization_id,
                        CommunicationCase.type == CaseType.INVENTORY_OPPORTUNITY,
                        CommunicationCase.status.in_(
                            [
                                CaseStatus.OPEN,
                                CaseStatus.ASSIGNED,
                                CaseStatus.IN_PROGRESS,
                                CaseStatus.WAITING_FOR_RESPONSE,
                                CaseStatus.WAITING_FOR_USER,
                            ]
                        ),
                        CommunicationCase.vehicle_id.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )

        opportunities: list[dict[str, Any]] = []
        for item in aging:
            vid = UUID(item["id"])
            if vid in open_opp_vehicle_ids:
                continue

            req_rows = list(
                (
                    await self.db.execute(
                        select(
                            InventoryRequest.requesting_branch_id,
                            func.count(InventoryRequest.id),
                        )
                        .where(
                            InventoryRequest.organization_id == organization_id,
                            InventoryRequest.vehicle_id == vid,
                            InventoryRequest.status == InventoryRequestStatus.OPEN,
                        )
                        .group_by(InventoryRequest.requesting_branch_id)
                    )
                ).all()
            )
            branch_ids = [str(r[0]) for r in req_rows]
            request_count = sum(int(r[1]) for r in req_rows)

            interest_count = int(
                (
                    await self.db.scalar(
                        select(func.count())
                        .select_from(CommunicationCase)
                        .where(
                            CommunicationCase.organization_id == organization_id,
                            CommunicationCase.vehicle_id == vid,
                            CommunicationCase.type == CaseType.CUSTOMER_INTEREST,
                            CommunicationCase.status.in_(
                                [
                                    CaseStatus.OPEN,
                                    CaseStatus.ASSIGNED,
                                    CaseStatus.IN_PROGRESS,
                                    CaseStatus.WAITING_FOR_RESPONSE,
                                    CaseStatus.WAITING_FOR_USER,
                                ]
                            ),
                        )
                    )
                )
                or 0
            )

            has_branch_demand = len(branch_ids) >= min_branch_requests
            has_customer_interest = interest_count > 0
            if not (has_branch_demand or has_customer_interest):
                continue

            reasons: list[str] = [f"aged_{item['days_in_stock']}_days"]
            if has_branch_demand:
                reasons.append(f"branch_requests_{len(branch_ids)}")
            if has_customer_interest:
                reasons.append(f"customer_interest_{interest_count}")

            score = item["days_in_stock"] + (len(branch_ids) * 10) + (interest_count * 15)
            opportunities.append(
                {
                    **item,
                    "open_request_count": request_count,
                    "requesting_branch_ids": branch_ids,
                    "customer_interest_count": interest_count,
                    "reasons": reasons,
                    "score": score,
                }
            )

        opportunities.sort(key=lambda x: x["score"], reverse=True)
        return opportunities
