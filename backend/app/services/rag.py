"""Semantic memory indexing & retrieval.

Structured fields (VIN, price, status, ids) stay in SQL / SearchService.
This module only handles narrative/content chunks.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import (
    EmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
)
from app.core.config import get_settings
from app.core.permissions import PermissionCode, require_permission
from app.core.pgvector import pgvector_semantic_search
from app.models import CommunicationCase, Message, WorkItem
from app.models.embeddings import Embedding
from app.models.inventory import Vehicle


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


@dataclass
class RetrievalHit:
    embedding_id: UUID
    entity_type: str
    entity_id: UUID
    chunk_id: str
    content: str
    score: float
    metadata: dict[str, Any]


class RagService:
    def __init__(self, db: AsyncSession, provider: EmbeddingProvider | None = None):
        self.db = db
        self.provider = provider or get_embedding_provider()

    async def index_text(
        self,
        *,
        organization_id: UUID,
        entity_type: str,
        entity_id: UUID,
        content: str,
        actor_permissions: set[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[Embedding]:
        if actor_permissions is not None:
            require_permission(actor_permissions, PermissionCode.RAG_INDEX)

        chunks = chunk_text(content)
        if not chunks:
            return []

        vectors = await self.provider.embed(chunks)
        meta_json = json.dumps(metadata or {})
        stored: list[Embedding] = []

        for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            chunk_id = str(i)
            chash = _content_hash(chunk)
            existing = await self.db.scalar(
                select(Embedding).where(
                    Embedding.organization_id == organization_id,
                    Embedding.entity_type == entity_type,
                    Embedding.entity_id == entity_id,
                    Embedding.chunk_id == chunk_id,
                    Embedding.embedding_model == self.provider.model_name,
                )
            )
            if existing and existing.content_hash == chash:
                stored.append(existing)
                continue

            payload = json.dumps(vector)
            if existing:
                existing.content = chunk
                existing.content_hash = chash
                existing.embedding = payload
                existing.dims = len(vector)
                existing.embedding_version = self.provider.version
                existing.metadata_json = meta_json
                stored.append(existing)
            else:
                row = Embedding(
                    organization_id=organization_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    chunk_id=chunk_id,
                    content=chunk,
                    content_hash=chash,
                    embedding=payload,
                    embedding_model=self.provider.model_name,
                    embedding_version=self.provider.version,
                    dims=len(vector),
                    metadata_json=meta_json,
                )
                self.db.add(row)
                stored.append(row)

        await self.db.flush()
        return stored

    async def index_message(
        self, message: Message, actor_permissions: set[str] | None = None
    ) -> list[Embedding]:
        return await self.index_text(
            organization_id=message.organization_id,
            entity_type="message",
            entity_id=message.id,
            content=message.text,
            actor_permissions=actor_permissions,
            metadata={
                "conversation_id": str(message.conversation_id),
                "sender_id": str(message.sender_id) if message.sender_id else None,
                "channel": message.channel.value,
                "visibility_scope": "organization",
            },
        )

    async def index_case(
        self, case: CommunicationCase, actor_permissions: set[str] | None = None
    ) -> list[Embedding]:
        content = f"Case {case.case_number}: {case.subject}. Type {case.type.value}. Status {case.status.value}."
        return await self.index_text(
            organization_id=case.organization_id,
            entity_type="case",
            entity_id=case.id,
            content=content,
            actor_permissions=actor_permissions,
            metadata={
                "case_id": str(case.id),
                "branch_id": str(case.branch_id) if case.branch_id else None,
                "vehicle_id": str(case.vehicle_id) if case.vehicle_id else None,
                "visibility_scope": "organization",
            },
        )

    async def index_vehicle(
        self, vehicle: Vehicle, actor_permissions: set[str] | None = None
    ) -> list[Embedding]:
        # Narrative description only — VIN/price remain SQL-primary
        parts = [
            f"{vehicle.brand} {vehicle.model}",
            f"year {vehicle.year}",
        ]
        if vehicle.color:
            parts.append(f"color {vehicle.color}")
        if vehicle.trim:
            parts.append(f"trim {vehicle.trim}")
        if vehicle.stock_number:
            parts.append(f"stock {vehicle.stock_number}")
        content = ", ".join(parts)
        return await self.index_text(
            organization_id=vehicle.organization_id,
            entity_type="vehicle",
            entity_id=vehicle.id,
            content=content,
            actor_permissions=actor_permissions,
            metadata={
                "vehicle_id": str(vehicle.id),
                "branch_id": str(vehicle.branch_id) if vehicle.branch_id else None,
                "visibility_scope": "organization",
                # Structured fields recorded for filtering only — not semantic truth
                "stock_number": vehicle.stock_number,
            },
        )

    async def index_work_item(
        self, work_item: WorkItem, actor_permissions: set[str] | None = None
    ) -> list[Embedding]:
        content = work_item.title
        if work_item.description:
            content += f"\n{work_item.description}"
        return await self.index_text(
            organization_id=work_item.organization_id,
            entity_type="work_item",
            entity_id=work_item.id,
            content=content,
            actor_permissions=actor_permissions,
            metadata={
                "work_item_id": str(work_item.id),
                "vehicle_id": str(work_item.vehicle_id) if work_item.vehicle_id else None,
                "branch_id": str(work_item.branch_id) if work_item.branch_id else None,
                "visibility_scope": "organization",
            },
        )

    async def semantic_search(
        self,
        *,
        organization_id: UUID,
        query: str,
        actor_permissions: set[str],
        entity_types: list[str] | None = None,
        branch_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        top_k: int = 5,
        min_score: float = 0.05,
    ) -> list[RetrievalHit]:
        require_permission(actor_permissions, PermissionCode.RAG_READ)
        request_id = str(uuid.uuid4())

        q_vec = (await self.provider.embed([query]))[0]

        # ANN only when explicitly enabled. Default stays JSON cosine on every dialect.
        pg_hits: list[dict] = []
        if get_settings().embedding_backend == "pgvector":
            pg_hits = await pgvector_semantic_search(
            self.db,
            organization_id=str(organization_id),
            query_vector=q_vec,
            entity_types=entity_types,
            branch_id=str(branch_id) if branch_id else None,
            vehicle_id=str(vehicle_id) if vehicle_id else None,
            top_k=top_k,
            min_score=min_score,
            model_name=self.provider.model_name,
        )
        if pg_hits:
            return [
                RetrievalHit(
                    embedding_id=h["embedding_id"],
                    entity_type=h["entity_type"],
                    entity_id=h["entity_id"],
                    chunk_id=h["chunk_id"],
                    content=h["content"],
                    score=h["score"],
                    metadata={**h["metadata"], "request_id": request_id},
                )
                for h in pg_hits
            ]

        # Fallback: Python cosine similarity on JSON column
        stmt = select(Embedding).where(
            Embedding.organization_id == organization_id,
            Embedding.embedding_model == self.provider.model_name,
        )
        if entity_types:
            stmt = stmt.where(Embedding.entity_type.in_(entity_types))

        rows = list((await self.db.execute(stmt)).scalars().all())
        hits: list[RetrievalHit] = []
        for row in rows:
            meta = json.loads(row.metadata_json) if row.metadata_json else {}
            if branch_id and meta.get("branch_id") and meta.get("branch_id") != str(branch_id):
                continue
            if vehicle_id and meta.get("vehicle_id") and meta.get("vehicle_id") != str(vehicle_id):
                continue
            vec = json.loads(row.embedding)
            score = cosine_similarity(q_vec, vec)
            if score < min_score:
                continue
            hits.append(
                RetrievalHit(
                    embedding_id=row.id,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    chunk_id=row.chunk_id,
                    content=row.content,
                    score=score,
                    metadata={**meta, "request_id": request_id},
                )
            )

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[: max(1, min(top_k, 50))]
