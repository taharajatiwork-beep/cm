from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, handle_authz
from app.core.permissions import AuthorizationError
from app.db.session import get_db
from app.services.search import SearchEntityType, SearchService

router = APIRouter(prefix="/search", tags=["search"])


class SearchHitOut(BaseModel):
    entity_type: str
    entity_id: UUID
    title: str
    subtitle: str | None = None
    score: float
    match_kind: str
    metadata: dict = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str | None
    total: int
    hits: list[SearchHitOut]


@router.get("", response_model=SearchResponse)
async def search(
    q: str | None = Query(None, description="Free-text query"),
    types: str | None = Query(
        None,
        description="Comma-separated: vehicle,case,user,work_item",
    ),
    status: str | None = None,
    branch_id: UUID | None = None,
    vin: str | None = None,
    case_number: str | None = None,
    stock_number: str | None = None,
    employee: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(50, ge=1, le=100),
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    parsed_types: list[SearchEntityType] | None = None
    if types:
        parsed_types = []
        for part in types.split(","):
            part = part.strip().lower()
            if not part:
                continue
            try:
                parsed_types.append(SearchEntityType(part))
            except ValueError:
                continue

    try:
        hits = await SearchService(db).search(
            organization_id=ctx.organization_id,
            actor_permissions=ctx.permissions,
            q=q,
            types=parsed_types,
            status=status,
            branch_id=branch_id,
            vin=vin,
            case_number=case_number,
            stock_number=stock_number,
            employee=employee,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            scope=ctx.scope,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e

    return SearchResponse(
        query=q,
        total=len(hits),
        hits=[
            SearchHitOut(
                entity_type=h.entity_type,
                entity_id=h.entity_id,
                title=h.title,
                subtitle=h.subtitle,
                score=h.score,
                match_kind=h.match_kind,
                metadata=h.metadata,
            )
            for h in hits
        ],
    )
