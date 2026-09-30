"""DivarService — sync inventory vehicles to Divar pilot (assisted listing only)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.divar.client import DivarClient, get_divar_client
from app.integrations.divar.mapper import vehicle_to_divar_product
from app.models.divar import DivarListing
from app.models.enums import CaseType, Priority, VehicleStatus
from app.services import WorkService
from app.services.inventory import InventoryService


class DivarService:
    def __init__(self, db: AsyncSession, client: DivarClient | None = None):
        self.db = db
        self.client = client or get_divar_client()
        self.inventory = InventoryService(db)
        self.work = WorkService(db)

    async def list_candidates(
        self, organization_id: UUID, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        """IN_STOCK vehicles without an active Divar listing."""
        listed_ids = set(
            (
                await self.db.execute(
                    select(DivarListing.vehicle_id).where(
                        DivarListing.organization_id == organization_id,
                        DivarListing.status.in_(["synced", "task_created"]),
                    )
                )
            )
            .scalars()
            .all()
        )
        vehicles = await self.inventory.search_vehicles(
            organization_id, status=VehicleStatus.IN_STOCK
        )
        out: list[dict[str, Any]] = []
        for v in vehicles:
            if v.id in listed_ids:
                continue
            out.append(
                {
                    "id": str(v.id),
                    "brand": v.brand,
                    "model": v.model,
                    "year": v.year,
                    "stock_number": v.stock_number,
                    "sale_price": v.sale_price,
                    "vin": v.vin,
                }
            )
            if len(out) >= limit:
                break
        return out

    async def list_listings(self, organization_id: UUID) -> list[dict[str, Any]]:
        rows = list(
            (
                await self.db.execute(
                    select(DivarListing)
                    .where(DivarListing.organization_id == organization_id)
                    .order_by(DivarListing.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": str(r.id),
                "vehicle_id": str(r.vehicle_id),
                "divar_product_id": r.divar_product_id,
                "divar_task_id": r.divar_task_id,
                "status": r.status,
                "title": r.title,
                "work_item_id": str(r.work_item_id) if r.work_item_id else None,
                "case_id": str(r.case_id) if r.case_id else None,
            }
            for r in rows
        ]

    async def prepare_listing(
        self,
        *,
        organization_id: UUID,
        vehicle_id: UUID,
        actor_id: UUID,
        city: str = "تهران",
        create_task: bool = True,
        create_work_item: bool = True,
    ) -> dict[str, Any]:
        """Push vehicle as Divar product (+ optional pilot task). Never submits the ad."""
        existing = await self.db.scalar(
            select(DivarListing).where(
                DivarListing.organization_id == organization_id,
                DivarListing.vehicle_id == vehicle_id,
                DivarListing.status.in_(["synced", "task_created"]),
            )
        )
        if existing:
            return {
                "already_exists": True,
                "listing_id": str(existing.id),
                "divar_product_id": existing.divar_product_id,
                "divar_task_id": existing.divar_task_id,
                "status": existing.status,
                "work_item_id": str(existing.work_item_id) if existing.work_item_id else None,
                "case_id": str(existing.case_id) if existing.case_id else None,
                "title": existing.title,
            }

        vehicle = await self.inventory.get_vehicle(vehicle_id)
        if not vehicle or vehicle.organization_id != organization_id:
            raise ValueError("Vehicle not found")

        product_payload = vehicle_to_divar_product(vehicle, city=city)
        created = await self.client.create_product(product_payload)
        product = created.get("product") or created
        product_id = product["id"]

        task_id: str | None = None
        validation_errors: list[Any] = []
        task_status: str | None = None
        last_error: str | None = None
        if create_task:
            try:
                task_resp = await self.client.create_task(product_id)
                task = task_resp.get("task") or task_resp
                task_id = task.get("id")
                validation_errors = task.get("validationErrors") or []
                task_status = task.get("status")
            except Exception as exc:
                last_error = (getattr(self.client, "last_error", None) or str(exc))[:500]

        work_item_id = None
        case_id = None
        if create_work_item:
            subject = f"Divar listing: {product_payload['title']}"
            wi = await self.work.create_work_item(
                organization_id=organization_id,
                title=subject,
                owner_id=actor_id,
                description=(
                    "Assisted Divar listing prepared from inventory. "
                    "Human operator must review and submit on Divar — never auto-submit."
                ),
                priority=Priority.HIGH,
                vehicle_id=vehicle_id,
                branch_id=vehicle.branch_id,
            )
            work_item_id = wi.id
            case = await self.work.create_case(
                organization_id=organization_id,
                subject=subject,
                case_type=CaseType.GENERAL_OPERATIONAL_REQUEST,
                created_by=actor_id,
                work_item_id=wi.id,
                vehicle_id=vehicle_id,
                branch_id=vehicle.branch_id,
                priority=Priority.HIGH,
            )
            case_id = case.id
            await self.work.create_task(
                organization_id=organization_id,
                title=f"Review & submit Divar ad — {product_payload['title']}",
                owner_id=actor_id,
                work_item_id=wi.id,
                case_id=case.id,
                description=(
                    f"Product {product_id}"
                    + (f" / Task {task_id}" if task_id else "")
                    + ". Use Divar pilot (prefill only). Do not automate final submit."
                ),
                assignee_ids=[actor_id],
                priority=Priority.HIGH,
            )

        listing = DivarListing(
            organization_id=organization_id,
            vehicle_id=vehicle_id,
            created_by=actor_id,
            divar_product_id=product_id,
            divar_task_id=task_id,
            status="task_created" if task_id else "synced",
            title=product_payload["title"],
            last_error=last_error,
            prefill_json=json.dumps(product_payload, ensure_ascii=False),
            work_item_id=work_item_id,
            case_id=case_id,
        )
        self.db.add(listing)
        await self.db.flush()

        return {
            "already_exists": False,
            "listing_id": str(listing.id),
            "divar_product_id": product_id,
            "divar_task_id": task_id,
            "divar_task_status": task_status,
            "validation_errors": validation_errors,
            "status": listing.status,
            "title": listing.title,
            "work_item_id": str(work_item_id) if work_item_id else None,
            "case_id": str(case_id) if case_id else None,
            "safety": "human_submit_required",
        }
