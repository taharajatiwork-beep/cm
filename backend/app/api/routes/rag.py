from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, handle_authz
from app.core.permissions import AuthorizationError
from app.db.session import get_db
from app.models import CommunicationCase, Message, WorkItem
from app.models.inventory import Vehicle
from app.services.hybrid_rag import HybridRagService
from app.services.rag import RagService

router = APIRouter(prefix="/rag", tags=["rag"])


class IndexBody(BaseModel):
    entity_type: str = Field(description="message | case | vehicle | work_item | custom")
    entity_id: UUID
    content: str | None = None  # required for custom; optional if loading from DB


class IndexResult(BaseModel):
    entity_type: str
    entity_id: UUID
    chunks_indexed: int


class QueryBody(BaseModel):
    query: str
    entity_types: list[str] | None = None
    branch_id: UUID | None = None
    vehicle_id: UUID | None = None
    top_k: int = 5
    min_score: float = 0.05


class RetrievalHitOut(BaseModel):
    embedding_id: UUID
    entity_type: str
    entity_id: UUID
    chunk_id: str
    content: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class QueryResult(BaseModel):
    query: str
    total: int
    hits: list[RetrievalHitOut]


@router.post("/index", response_model=IndexResult)
async def index_entity(
    body: IndexBody,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = RagService(db)
    try:
        if body.entity_type == "message":
            msg = await db.get(Message, body.entity_id)
            if not msg or msg.organization_id != ctx.organization_id:
                raise HTTPException(404, "Message not found")
            rows = await svc.index_message(msg, actor_permissions=ctx.permissions)
        elif body.entity_type == "case":
            case = await db.get(CommunicationCase, body.entity_id)
            if not case or case.organization_id != ctx.organization_id:
                raise HTTPException(404, "Case not found")
            rows = await svc.index_case(case, actor_permissions=ctx.permissions)
        elif body.entity_type == "vehicle":
            vehicle = await db.get(Vehicle, body.entity_id)
            if not vehicle or vehicle.organization_id != ctx.organization_id:
                raise HTTPException(404, "Vehicle not found")
            rows = await svc.index_vehicle(vehicle, actor_permissions=ctx.permissions)
        elif body.entity_type == "work_item":
            wi = await db.get(WorkItem, body.entity_id)
            if not wi or wi.organization_id != ctx.organization_id:
                raise HTTPException(404, "Work item not found")
            rows = await svc.index_work_item(wi, actor_permissions=ctx.permissions)
        elif body.entity_type == "custom":
            if not body.content:
                raise HTTPException(400, "content required for custom entity_type")
            rows = await svc.index_text(
                organization_id=ctx.organization_id,
                entity_type="custom",
                entity_id=body.entity_id,
                content=body.content,
                actor_permissions=ctx.permissions,
                metadata={"visibility_scope": "organization"},
            )
        else:
            raise HTTPException(400, f"Unsupported entity_type: {body.entity_type}")
    except AuthorizationError as e:
        raise handle_authz(e) from e

    return IndexResult(
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        chunks_indexed=len(rows),
    )


@router.post("/query", response_model=QueryResult)
async def semantic_query(
    body: QueryBody,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        hits = await RagService(db).semantic_search(
            organization_id=ctx.organization_id,
            query=body.query,
            actor_permissions=ctx.permissions,
            entity_types=body.entity_types,
            branch_id=body.branch_id,
            vehicle_id=body.vehicle_id,
            top_k=body.top_k,
            min_score=body.min_score,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e

    return QueryResult(
        query=body.query,
        total=len(hits),
        hits=[
            RetrievalHitOut(
                embedding_id=h.embedding_id,
                entity_type=h.entity_type,
                entity_id=h.entity_id,
                chunk_id=h.chunk_id,
                content=h.content,
                score=h.score,
                metadata=h.metadata,
            )
            for h in hits
        ],
    )


class HybridBody(BaseModel):
    query: str
    entity_types: list[str] | None = None
    branch_id: UUID | None = None
    top_k: int = 8
    context_char_limit: int = 4000


class FusedHitOut(BaseModel):
    entity_type: str
    entity_id: UUID
    title: str
    content: str
    sources: list[str]
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class HybridResultOut(BaseModel):
    request_id: str
    intent: str
    query: str
    total: int
    hits: list[FusedHitOut]
    context: str
    answer: str
    answer_mode: str = "extractive"
    analyzed: dict[str, Any]


@router.post("/hybrid", response_model=HybridResultOut)
async def hybrid_query(
    body: HybridBody,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await HybridRagService(db).run(
            organization_id=ctx.organization_id,
            query=body.query,
            actor_permissions=ctx.permissions,
            entity_types=body.entity_types,
            branch_id=body.branch_id,
            top_k=body.top_k,
            context_char_limit=body.context_char_limit,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e

    aq = result.query
    return HybridResultOut(
        request_id=result.request_id,
        intent=aq.intent,
        query=aq.raw,
        total=len(result.hits),
        hits=[
            FusedHitOut(
                entity_type=h.entity_type,
                entity_id=h.entity_id,
                title=h.title,
                content=h.content,
                sources=h.sources,
                score=h.score,
                metadata=h.metadata,
            )
            for h in result.hits
        ],
        context=result.context,
        answer=result.answer,
        answer_mode=result.answer_mode,
        analyzed={
            "vin": aq.vin,
            "case_number": aq.case_number,
            "stock_number": aq.stock_number,
            "brand": aq.brand,
            "model": aq.model,
            "entity_types": aq.entity_types,
            "wants_status": aq.wants_status,
        },
    )
