"""Structured + exact + text search over core entities.

PostgreSQL FTS (tsvector) can replace ilike later; SQLite uses case-insensitive LIKE.
Never uses vector/RAG — that is Phase 5+.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import PermissionCode, require_permission
from app.core.scope import scope_clause
from app.models import CommunicationCase, User, WorkItem
from app.models.enums import CaseStatus, VehicleStatus, WorkItemStatus
from app.models.inventory import Vehicle


class SearchEntityType(StrEnum):
    VEHICLE = "vehicle"
    CASE = "case"
    USER = "user"
    WORK_ITEM = "work_item"
    BRANCH = "branch"


@dataclass
class SearchHit:
    entity_type: str
    entity_id: UUID
    title: str
    subtitle: str | None
    score: float
    match_kind: str  # exact | text | filter
    metadata: dict[str, Any]


class SearchService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _text_contains(self, column, token: str):
        """ilike on SQLite; PostgreSQL tsvector when the engine is Postgres."""
        bind = self.db.bind
        if bind is not None and bind.dialect.name == "postgresql":
            return func.to_tsvector("simple", func.coalesce(column, "")).bool_op("@@")(
                func.plainto_tsquery("simple", token)
            )
        return column.ilike(f"%{token}%")

    async def search(
        self,
        *,
        organization_id: UUID,
        actor_permissions: set[str],
        q: str | None = None,
        types: list[SearchEntityType] | None = None,
        status: str | None = None,
        branch_id: UUID | None = None,
        vin: str | None = None,
        case_number: str | None = None,
        stock_number: str | None = None,
        brand: str | None = None,
        model: str | None = None,
        employee: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        scope=None,
    ) -> list[SearchHit]:
        require_permission(actor_permissions, PermissionCode.SEARCH)
        self._scope = scope
        types = types or list(SearchEntityType)
        hits: list[SearchHit] = []
        q_norm = (q or "").strip()

        if SearchEntityType.VEHICLE in types and (
            PermissionCode.INVENTORY_READ in actor_permissions
            or PermissionCode.ORG_ADMIN in actor_permissions
            or PermissionCode.SEARCH in actor_permissions
        ):
            hits.extend(
                await self._search_vehicles(
                    organization_id,
                    q=q_norm,
                    status=status,
                    branch_id=branch_id,
                    vin=vin,
                    stock_number=stock_number,
                    brand=brand,
                    model=model,
                    date_from=date_from,
                    date_to=date_to,
                )
            )

        if SearchEntityType.CASE in types and (
            PermissionCode.CASE_READ in actor_permissions
            or PermissionCode.ORG_ADMIN in actor_permissions
            or PermissionCode.SEARCH in actor_permissions
        ):
            hits.extend(
                await self._search_cases(
                    organization_id,
                    q=q_norm,
                    status=status,
                    branch_id=branch_id,
                    case_number=case_number,
                    date_from=date_from,
                    date_to=date_to,
                )
            )

        if SearchEntityType.USER in types and (
            PermissionCode.USER_READ in actor_permissions
            or PermissionCode.ORG_ADMIN in actor_permissions
            or PermissionCode.SEARCH in actor_permissions
        ):
            hits.extend(
                await self._search_users(
                    organization_id,
                    q=q_norm,
                    employee=employee,
                    branch_id=branch_id,
                )
            )

        if SearchEntityType.WORK_ITEM in types and (
            PermissionCode.WORK_ITEM_READ in actor_permissions
            or PermissionCode.ORG_ADMIN in actor_permissions
            or PermissionCode.SEARCH in actor_permissions
        ):
            hits.extend(
                await self._search_work_items(
                    organization_id,
                    q=q_norm,
                    status=status,
                    branch_id=branch_id,
                    date_from=date_from,
                    date_to=date_to,
                )
            )

        hits.sort(key=lambda h: (-h.score, h.title.lower()))
        return hits[: max(1, min(limit, 100))]

    async def _search_vehicles(
        self,
        organization_id: UUID,
        *,
        q: str,
        status: str | None,
        branch_id: UUID | None,
        vin: str | None,
        stock_number: str | None,
        brand: str | None = None,
        model: str | None = None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> list[SearchHit]:
        filters = [Vehicle.organization_id == organization_id]
        scoped = scope_clause(Vehicle, getattr(self, "_scope", None))
        if scoped is not None:
            filters.append(scoped)
        match_kind = "filter"
        score = 1.0

        if vin:
            filters.append(Vehicle.vin == vin.upper())
            match_kind = "exact"
            score = 10.0
        if stock_number:
            filters.append(Vehicle.stock_number == stock_number)
            match_kind = "exact"
            score = max(score, 9.0)
        if brand:
            filters.append(Vehicle.brand.ilike(f"%{brand}%"))
            match_kind = "text"
            score = max(score, 7.0)
        if model:
            filters.append(Vehicle.model.ilike(f"%{model}%"))
            match_kind = "text"
            score = max(score, 8.0)
        if status:
            try:
                filters.append(Vehicle.status == VehicleStatus(status))
            except ValueError:
                pass
        if branch_id:
            filters.append(Vehicle.branch_id == branch_id)
        if date_from:
            filters.append(Vehicle.created_at >= date_from)
        if date_to:
            filters.append(Vehicle.created_at <= date_to)

        query: Select = select(Vehicle).where(and_(*filters))
        if q and not vin and not stock_number and not brand and not model:
            tokens = [
                t
                for t in re.split(r"[\s,;/|()]+", q)
                if len(t) >= 2 and not re.fullmatch(r"(?:19|20)\d{2}", t)
            ]
            if not tokens:
                tokens = [q]

            def _token_match(tok: str):
                return or_(
                    self._text_contains(Vehicle.vin, tok),
                    self._text_contains(Vehicle.stock_number, tok),
                    self._text_contains(Vehicle.brand, tok),
                    self._text_contains(Vehicle.model, tok),
                    self._text_contains(Vehicle.color, tok),
                    self._text_contains(Vehicle.trim, tok),
                    self._text_contains(Vehicle.plate_number, tok),
                    self._text_contains(Vehicle.description, tok),
                    self._text_contains(Vehicle.options, tok),
                )

            if len(tokens) == 1:
                query = query.where(_token_match(tokens[0]))
            else:
                # "Hyundai Elantra" → each token must match some field (AND)
                query = query.where(and_(*[_token_match(t) for t in tokens[:5]]))
            match_kind = "exact" if self._looks_like_vin(q) else "text"
            score = 8.0 if match_kind == "exact" else 3.0
            if self._looks_like_vin(q):
                like = f"%{q}%"
                query = select(Vehicle).where(
                    and_(
                        Vehicle.organization_id == organization_id,
                        or_(Vehicle.vin == q.upper(), Vehicle.vin.ilike(like)),
                        *([Vehicle.branch_id == branch_id] if branch_id else []),
                    )
                )

        rows = list((await self.db.execute(query.limit(40))).scalars().all())
        hits: list[SearchHit] = []
        for v in rows:
            exact = (vin and v.vin == vin.upper()) or (stock_number and v.stock_number == stock_number)
            hits.append(
                SearchHit(
                    entity_type=SearchEntityType.VEHICLE,
                    entity_id=v.id,
                    title=f"{v.brand} {v.model}"
                    + (f" #{v.stock_number}" if v.stock_number else ""),
                    subtitle=f"VIN {v.vin} · {v.status.value}"
                    + (f" · {v.year}" if v.year else ""),
                    score=10.0 if exact else score,
                    match_kind="exact" if exact or match_kind == "exact" else match_kind,
                    metadata={
                        "vin": v.vin,
                        "stock_number": v.stock_number,
                        "status": v.status.value,
                        "branch_id": str(v.branch_id) if v.branch_id else None,
                        "year": v.year,
                        "brand": v.brand,
                        "model": v.model,
                    },
                )
            )
        return hits

    async def _search_cases(
        self,
        organization_id: UUID,
        *,
        q: str,
        status: str | None,
        branch_id: UUID | None,
        case_number: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> list[SearchHit]:
        filters = [CommunicationCase.organization_id == organization_id]
        _scoped = scope_clause(CommunicationCase, getattr(self, "_scope", None))
        if _scoped is not None:
            filters.append(_scoped)
        match_kind = "filter"
        score = 1.0

        if case_number:
            filters.append(
                or_(
                    CommunicationCase.case_number == case_number,
                    CommunicationCase.case_number == case_number.upper(),
                    CommunicationCase.case_number.ilike(case_number),
                )
            )
            match_kind = "exact"
            score = 10.0
        if status:
            try:
                filters.append(CommunicationCase.status == CaseStatus(status))
            except ValueError:
                pass
        if branch_id:
            filters.append(CommunicationCase.branch_id == branch_id)
        if date_from:
            filters.append(CommunicationCase.created_at >= date_from)
        if date_to:
            filters.append(CommunicationCase.created_at <= date_to)

        query = select(CommunicationCase).where(and_(*filters))
        if q and not case_number:
            like = f"%{q}%"
            if q.upper().startswith("C-"):
                query = select(CommunicationCase).where(
                    CommunicationCase.organization_id == organization_id,
                    CommunicationCase.case_number.ilike(q),
                )
                match_kind = "exact"
                score = 10.0
            else:
                query = query.where(
                    or_(
                        CommunicationCase.case_number.ilike(like),
                        CommunicationCase.subject.ilike(like),
                    )
                )
                match_kind = "text"
                score = 3.0

        rows = list((await self.db.execute(query.limit(40))).scalars().all())
        return [
            SearchHit(
                entity_type=SearchEntityType.CASE,
                entity_id=c.id,
                title=c.case_number,
                subtitle=f"{c.subject} · {c.status.value}",
                score=score,
                match_kind=match_kind,
                metadata={
                    "status": c.status.value,
                    "type": c.type.value,
                    "branch_id": str(c.branch_id) if c.branch_id else None,
                    "vehicle_id": str(c.vehicle_id) if c.vehicle_id else None,
                },
            )
            for c in rows
        ]

    async def _search_users(
        self,
        organization_id: UUID,
        *,
        q: str,
        employee: str | None,
        branch_id: UUID | None,
    ) -> list[SearchHit]:
        filters = [User.organization_id == organization_id, User.is_active.is_(True)]
        _scoped = scope_clause(User, getattr(self, "_scope", None))
        if _scoped is not None:
            filters.append(_scoped)
        if branch_id:
            filters.append(User.branch_id == branch_id)

        term = (employee or q or "").strip()
        if not term:
            if branch_id:
                rows = list((await self.db.execute(select(User).where(and_(*filters)).limit(40))).scalars().all())
                return [
                    SearchHit(
                        entity_type=SearchEntityType.USER,
                        entity_id=u.id,
                        title=u.full_name,
                        subtitle=u.email,
                        score=1.0,
                        match_kind="filter",
                        metadata={"email": u.email, "branch_id": str(u.branch_id) if u.branch_id else None},
                    )
                    for u in rows
                ]
            return []

        like = f"%{term}%"
        # Exact email
        exact_email = await self.db.scalar(
            select(User).where(
                User.organization_id == organization_id,
                func.lower(User.email) == term.lower(),
            )
        )
        query = select(User).where(
            and_(
                *filters,
                or_(User.full_name.ilike(like), User.email.ilike(like)),
            )
        )
        rows = list((await self.db.execute(query.limit(40))).scalars().all())
        hits: list[SearchHit] = []
        seen: set[UUID] = set()
        if exact_email:
            hits.append(
                SearchHit(
                    entity_type=SearchEntityType.USER,
                    entity_id=exact_email.id,
                    title=exact_email.full_name,
                    subtitle=exact_email.email,
                    score=10.0,
                    match_kind="exact",
                    metadata={
                        "email": exact_email.email,
                        "branch_id": str(exact_email.branch_id) if exact_email.branch_id else None,
                    },
                )
            )
            seen.add(exact_email.id)
        for u in rows:
            if u.id in seen:
                continue
            hits.append(
                SearchHit(
                    entity_type=SearchEntityType.USER,
                    entity_id=u.id,
                    title=u.full_name,
                    subtitle=u.email,
                    score=3.0,
                    match_kind="text",
                    metadata={"email": u.email, "branch_id": str(u.branch_id) if u.branch_id else None},
                )
            )
        return hits

    async def _search_work_items(
        self,
        organization_id: UUID,
        *,
        q: str,
        status: str | None,
        branch_id: UUID | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> list[SearchHit]:
        filters = [WorkItem.organization_id == organization_id]
        _scoped = scope_clause(WorkItem, getattr(self, "_scope", None))
        if _scoped is not None:
            filters.append(_scoped)
        if status:
            try:
                filters.append(WorkItem.status == WorkItemStatus(status))
            except ValueError:
                pass
        if branch_id:
            filters.append(WorkItem.branch_id == branch_id)
        if date_from:
            filters.append(WorkItem.created_at >= date_from)
        if date_to:
            filters.append(WorkItem.created_at <= date_to)

        query = select(WorkItem).where(and_(*filters))
        match_kind = "filter"
        score = 1.0
        if q:
            like = f"%{q}%"
            query = query.where(
                or_(WorkItem.title.ilike(like), WorkItem.description.ilike(like))
            )
            match_kind = "text"
            score = 3.0

        rows = list((await self.db.execute(query.limit(40))).scalars().all())
        return [
            SearchHit(
                entity_type=SearchEntityType.WORK_ITEM,
                entity_id=w.id,
                title=w.title,
                subtitle=w.status.value,
                score=score,
                match_kind=match_kind,
                metadata={
                    "status": w.status.value,
                    "vehicle_id": str(w.vehicle_id) if w.vehicle_id else None,
                    "branch_id": str(w.branch_id) if w.branch_id else None,
                },
            )
            for w in rows
        ]

    @staticmethod
    def _looks_like_vin(value: str) -> bool:
        cleaned = value.strip().upper()
        return len(cleaned) >= 11 and cleaned.isalnum()
