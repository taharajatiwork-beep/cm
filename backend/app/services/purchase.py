"""Purchase helpers — seller offers + unmet demand → purchase opportunities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CommunicationCase
from app.models.enums import CaseType, InventoryRequestStatus, VehicleStatus
from app.models.inventory import InventoryRequest
from app.services.inventory import InventoryService
from app.services.sales import OPEN_STATUSES, extract_vehicle_hints

PURCHASE_CASE_TYPES = (CaseType.SELLER_REQUEST,)


class PurchaseService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.inventory = InventoryService(db)

    async def list_pipeline(self, organization_id: UUID) -> list[dict[str, Any]]:
        rows = list(
            (
                await self.db.execute(
                    select(CommunicationCase)
                    .where(
                        CommunicationCase.organization_id == organization_id,
                        CommunicationCase.type.in_(PURCHASE_CASE_TYPES),
                        CommunicationCase.status.in_(OPEN_STATUSES),
                    )
                    .order_by(CommunicationCase.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        now = datetime.now(timezone.utc)
        out: list[dict[str, Any]] = []
        for c in rows:
            created = c.created_at
            if created and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            days = (now - created).days if created else 0
            out.append(
                {
                    "id": str(c.id),
                    "case_number": c.case_number,
                    "type": c.type.value,
                    "subject": c.subject,
                    "status": c.status.value,
                    "priority": c.priority.value,
                    "owner_id": str(c.owner_id) if c.owner_id else None,
                    "vehicle_id": str(c.vehicle_id) if c.vehicle_id else None,
                    "branch_id": str(c.branch_id) if c.branch_id else None,
                    "days_open": days,
                    "created_at": created.isoformat() if created else None,
                    "hints": extract_vehicle_hints(c.subject),
                }
            )
        return out

    async def _in_stock_count(
        self, organization_id: UUID, *, brand: str | None, model: str | None
    ) -> int:
        if not model and not brand:
            return 0
        found = await self.inventory.search_vehicles(
            organization_id,
            brand=brand,
            model=model,
            status=VehicleStatus.IN_STOCK,
        )
        return len(found)

    async def detect_unmet_demand(self, organization_id: UUID) -> list[dict[str, Any]]:
        """Buyer/interest cases + open inventory requests whose model has zero in-stock."""
        demand_sources: list[tuple[str, str, dict[str, str | None]]] = []

        cases = list(
            (
                await self.db.execute(
                    select(CommunicationCase).where(
                        CommunicationCase.organization_id == organization_id,
                        CommunicationCase.type.in_(
                            [CaseType.BUYER_REQUEST, CaseType.CUSTOMER_INTEREST]
                        ),
                        CommunicationCase.status.in_(OPEN_STATUSES),
                    )
                )
            )
            .scalars()
            .all()
        )
        for c in cases:
            hints = extract_vehicle_hints(c.subject)
            if hints.get("model") or hints.get("brand"):
                demand_sources.append(("case", str(c.id), hints))

        reqs = list(
            (
                await self.db.execute(
                    select(InventoryRequest).where(
                        InventoryRequest.organization_id == organization_id,
                        InventoryRequest.status == InventoryRequestStatus.OPEN,
                    )
                )
            )
            .scalars()
            .all()
        )
        for r in reqs:
            hints = extract_vehicle_hints(r.subject)
            if hints.get("model") or hints.get("brand"):
                demand_sources.append(("inventory_request", str(r.id), hints))

        # Aggregate by brand|model
        buckets: dict[str, dict[str, Any]] = {}
        for source_type, source_id, hints in demand_sources:
            brand = hints.get("brand")
            model = hints.get("model")
            key = f"{brand or ''}|{model or ''}".lower()
            if key == "|":
                continue
            if key not in buckets:
                buckets[key] = {
                    "brand": brand,
                    "model": model,
                    "matched_token": hints.get("matched_token"),
                    "source_ids": [],
                    "source_types": set(),
                    "demand_count": 0,
                }
            buckets[key]["demand_count"] += 1
            buckets[key]["source_ids"].append(source_id)
            buckets[key]["source_types"].add(source_type)

        existing = await self._open_purchase_subjects(organization_id)
        opportunities: list[dict[str, Any]] = []
        for bucket in buckets.values():
            stock = await self._in_stock_count(
                organization_id, brand=bucket["brand"], model=bucket["model"]
            )
            if stock > 0:
                continue
            label = f"{bucket['brand'] or ''} {bucket['model'] or ''}".strip()
            marker = f"Purchase opportunity: {label}"
            if any(marker.lower() in s.lower() for s in existing):
                continue
            reasons = ["unmet_demand", f"demand_{bucket['demand_count']}", "zero_stock"]
            opportunities.append(
                {
                    "kind": "unmet_demand",
                    "brand": bucket["brand"],
                    "model": bucket["model"],
                    "label": label,
                    "demand_count": bucket["demand_count"],
                    "in_stock": stock,
                    "source_ids": bucket["source_ids"],
                    "source_types": sorted(bucket["source_types"]),
                    "reasons": reasons,
                    "score": bucket["demand_count"] * 10,
                }
            )

        opportunities.sort(key=lambda x: x["score"], reverse=True)
        return opportunities

    async def detect_stale_seller_offers(
        self, organization_id: UUID, *, stale_days: int = 3
    ) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
        pipeline = await self.list_pipeline(organization_id)
        existing = await self._open_purchase_subjects(organization_id)
        out: list[dict[str, Any]] = []
        for item in pipeline:
            created = item.get("created_at")
            if not created:
                continue
            created_dt = datetime.fromisoformat(created)
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            if created_dt > cutoff:
                continue
            marker = f"Purchase follow-up: {item['case_number']}"
            if any(marker in s for s in existing):
                continue
            reasons = [f"stale_{item['days_open']}_days"]
            if not item.get("owner_id"):
                reasons.append("unassigned")
            out.append(
                {
                    "kind": "stale_seller_offer",
                    **item,
                    "label": item["subject"],
                    "reasons": reasons,
                    "score": item["days_open"] * 2 + (0 if item.get("owner_id") else 8),
                }
            )
        out.sort(key=lambda x: x["score"], reverse=True)
        return out

    async def detect_opportunities(
        self, organization_id: UUID, *, stale_days: int = 3
    ) -> list[dict[str, Any]]:
        unmet = await self.detect_unmet_demand(organization_id)
        stale = await self.detect_stale_seller_offers(organization_id, stale_days=stale_days)
        combined = unmet + stale
        combined.sort(key=lambda x: x.get("score", 0), reverse=True)
        return combined

    async def _open_purchase_subjects(self, organization_id: UUID) -> set[str]:
        rows = list(
            (
                await self.db.execute(
                    select(CommunicationCase.subject).where(
                        CommunicationCase.organization_id == organization_id,
                        CommunicationCase.status.in_(OPEN_STATUSES),
                        CommunicationCase.subject.ilike("%Purchase %"),
                    )
                )
            )
            .scalars()
            .all()
        )
        return set(rows)
