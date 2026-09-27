"""Deterministic entity resolution for Telegram messages.

No LLM — ambiguity must return clarification options, never invent entities.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.models.enums import VehicleStatus
from app.models.inventory import Vehicle

# Simple bilingual aliases for Phase 3 (expand later / move to KB)
BRAND_MODEL_ALIASES: dict[str, tuple[str, str]] = {
    "کمری": ("Toyota", "Camry"),
    "camry": ("Toyota", "Camry"),
    "النترا": ("Hyundai", "Elantra"),
    "elantra": ("Hyundai", "Elantra"),
}


@dataclass
class ResolvedUser:
    user: User
    matched_token: str


@dataclass
class ResolutionResult:
    vehicles: list[Vehicle] = field(default_factory=list)
    users: list[ResolvedUser] = field(default_factory=list)
    stock_number: str | None = None
    ambiguous: bool = False
    clarification: str | None = None
    intent: str | None = None  # create_work | message | unknown


class EntityResolver:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve(
        self,
        organization_id: UUID,
        text: str,
        *,
        known_users: list[User] | None = None,
    ) -> ResolutionResult:
        result = ResolutionResult()
        normalized = text.strip()
        lower = normalized.lower()

        # Stock number: #124 or 124 after کمری / stock
        stock_match = re.search(r"#\s*(\d+)|(?:شماره|stock)\s*[:=]?\s*(\d+)", normalized, re.I)
        if stock_match:
            result.stock_number = stock_match.group(1) or stock_match.group(2)

        vehicles: list[Vehicle] = []
        if result.stock_number:
            vehicles = list(
                (
                    await self.db.execute(
                        select(Vehicle).where(
                            Vehicle.organization_id == organization_id,
                            Vehicle.stock_number == result.stock_number,
                        )
                    )
                ).scalars().all()
            )

        if not vehicles:
            for alias, (brand, model) in BRAND_MODEL_ALIASES.items():
                if alias in lower or alias in normalized:
                    q = select(Vehicle).where(
                        Vehicle.organization_id == organization_id,
                        Vehicle.brand.ilike(brand),
                        Vehicle.model.ilike(model),
                        Vehicle.status.in_(
                            [
                                VehicleStatus.IN_STOCK,
                                VehicleStatus.RESERVED,
                                VehicleStatus.UNDER_REVIEW,
                            ]
                        ),
                    )
                    vehicles = list((await self.db.execute(q)).scalars().all())
                    break

        result.vehicles = vehicles
        if len(vehicles) > 1:
            result.ambiguous = True
            lines = ["I found multiple possible vehicles. Which one do you mean?"]
            for v in vehicles:
                lines.append(
                    f"- {v.brand} {v.model} #{v.stock_number or '?'} "
                    f"(VIN …{v.vin[-6:]}, status {v.status.value})"
                )
            result.clarification = "\n".join(lines)
        elif len(vehicles) == 0 and any(a in normalized or a in lower for a in BRAND_MODEL_ALIASES):
            result.clarification = "No matching vehicle found in inventory for that model."

        # Resolve people by first name token against org users
        users = known_users
        if users is None:
            users = list(
                (
                    await self.db.execute(
                        select(User).where(
                            User.organization_id == organization_id,
                            User.is_active.is_(True),
                        )
                    )
                ).scalars().all()
            )

        for user in users:
            first = user.full_name.split()[0].lower()
            # Match Latin first name or full Persian/Latin token in text
            tokens = {first, user.full_name.lower()}
            # Common Persian short names used in demos
            if first == "reza" or "رضا" in user.full_name:
                tokens |= {"رضا", "reza"}
            if first == "sara" or "سارا" in user.full_name:
                tokens |= {"سارا", "sara"}
            if first == "ali" or "علی" in user.full_name:
                tokens |= {"علی", "ali"}
            for token in tokens:
                if token and (token in lower or token in normalized):
                    if not any(r.user.id == user.id for r in result.users):
                        result.users.append(ResolvedUser(user=user, matched_token=token))
                    break

        # Intent: work creation if we see collaboration verbs / multiple assignees
        work_signals = (
            "پیگیری",
            "آگهی",
            "تبلیغات",
            "آماد",
            "فروش",
            "task",
            "work",
            "assign",
        )
        if any(s in normalized or s in lower for s in work_signals) and result.users:
            result.intent = "create_work"
        elif normalized.startswith("/"):
            result.intent = "command"
        else:
            result.intent = "message"

        return result
