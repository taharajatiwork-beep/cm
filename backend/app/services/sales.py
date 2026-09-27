"""Sales pipeline helpers — buyer/interest cases matched to inventory."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CommunicationCase
from app.models.enums import CaseStatus, CaseType, VehicleStatus
from app.services.inventory import InventoryService

SALES_CASE_TYPES = (
    CaseType.BUYER_REQUEST,
    CaseType.CUSTOMER_INTEREST,
    CaseType.FOLLOW_UP,
)

OPEN_STATUSES = (
    CaseStatus.OPEN,
    CaseStatus.ASSIGNED,
    CaseStatus.IN_PROGRESS,
    CaseStatus.WAITING_FOR_RESPONSE,
    CaseStatus.WAITING_FOR_USER,
)

# Lightweight model/brand hints for deterministic matching (no LLM).
_MODEL_HINTS: list[tuple[str, str, str]] = [
    ("کمری", "Toyota", "Camry"),
    ("camry", "Toyota", "Camry"),
    ("کرولا", "Toyota", "Corolla"),
    ("corolla", "Toyota", "Corolla"),
    ("پرادو", "Toyota", "Prado"),
    ("prado", "Toyota", "Prado"),
    ("آکورد", "Honda", "Accord"),
    ("accord", "Honda", "Accord"),
    ("سیویک", "Honda", "Civic"),
    ("civic", "Honda", "Civic"),
]


def extract_vehicle_hints(text: str) -> dict[str, str | None]:
    lower = text.lower()
    for token, brand, model in _MODEL_HINTS:
        if token in lower or token in text:
            return {"brand": brand, "model": model, "matched_token": token}
    # stock number e.g. #124 or stock 124
    m = re.search(r"(?:#|stock\s*|شماره\s*)(\d{2,6})", text, re.I)
    if m:
        return {"brand": None, "model": None, "stock_number": m.group(1), "matched_token": m.group(0)}
    return {"brand": None, "model": None, "matched_token": None}


class SalesService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.inventory = InventoryService(db)

    async def list_pipeline(
        self,
        organization_id: UUID,
        *,
        case_types: tuple[CaseType, ...] | None = None,
    ) -> list[dict[str, Any]]:
        types = case_types or SALES_CASE_TYPES
        rows = list(
            (
                await self.db.execute(
                    select(CommunicationCase)
                    .where(
                        CommunicationCase.organization_id == organization_id,
                        CommunicationCase.type.in_(types),
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
                }
            )
        return out

    async def match_case_to_inventory(
        self, organization_id: UUID, case_id: UUID
    ) -> dict[str, Any]:
        case = await self.db.get(CommunicationCase, case_id)
        if not case or case.organization_id != organization_id:
            raise ValueError("Case not found")

        hints = extract_vehicle_hints(case.subject)
        vehicles: list[dict[str, Any]] = []
        if hints.get("stock_number"):
            found = await self.inventory.search_vehicles(
                organization_id,
                stock_number=str(hints["stock_number"]),
                status=VehicleStatus.IN_STOCK,
            )
        elif hints.get("model"):
            found = await self.inventory.search_vehicles(
                organization_id,
                brand=hints.get("brand"),
                model=hints.get("model"),
                status=VehicleStatus.IN_STOCK,
            )
        else:
            found = []

        for v in found:
            vehicles.append(
                {
                    "id": str(v.id),
                    "vin": v.vin,
                    "brand": v.brand,
                    "model": v.model,
                    "stock_number": v.stock_number,
                    "status": v.status.value,
                    "branch_id": str(v.branch_id) if v.branch_id else None,
                    "sale_price": v.sale_price,
                }
            )

        return {
            "case_id": str(case.id),
            "case_number": case.case_number,
            "subject": case.subject,
            "hints": hints,
            "matches": vehicles,
            "match_count": len(vehicles),
        }

    async def detect_follow_ups(
        self,
        organization_id: UUID,
        *,
        stale_days: int = 3,
    ) -> list[dict[str, Any]]:
        """Open buyer/interest cases older than stale_days needing follow-up.

        Skips cases that already have an open FOLLOW_UP case on the same vehicle
        (or same case_number referenced in subject).
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
        pipeline = await self.list_pipeline(
            organization_id,
            case_types=(CaseType.BUYER_REQUEST, CaseType.CUSTOMER_INTEREST),
        )

        existing_followups = list(
            (
                await self.db.execute(
                    select(CommunicationCase).where(
                        CommunicationCase.organization_id == organization_id,
                        CommunicationCase.type == CaseType.FOLLOW_UP,
                        CommunicationCase.status.in_(OPEN_STATUSES),
                    )
                )
            )
            .scalars()
            .all()
        )
        covered_vehicles = {str(c.vehicle_id) for c in existing_followups if c.vehicle_id}
        covered_subjects = {c.subject for c in existing_followups}

        needs: list[dict[str, Any]] = []
        for item in pipeline:
            created = item.get("created_at")
            if not created:
                continue
            created_dt = datetime.fromisoformat(created)
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            if created_dt > cutoff:
                continue
            if item.get("vehicle_id") and item["vehicle_id"] in covered_vehicles:
                continue
            marker = f"Sales follow-up: {item['case_number']}"
            if any(marker in s for s in covered_subjects):
                continue

            match = await self.match_case_to_inventory(organization_id, UUID(item["id"]))
            reasons = [f"stale_{item['days_open']}_days"]
            if not item.get("owner_id"):
                reasons.append("unassigned")
            if match["match_count"]:
                reasons.append(f"inventory_matches_{match['match_count']}")
            else:
                reasons.append("no_inventory_match")

            needs.append(
                {
                    **item,
                    "reasons": reasons,
                    "inventory_matches": match["matches"],
                    "hints": match["hints"],
                    "score": item["days_open"] * 2
                    + (0 if item.get("owner_id") else 10)
                    + match["match_count"] * 5,
                }
            )

        needs.sort(key=lambda x: x["score"], reverse=True)
        return needs
