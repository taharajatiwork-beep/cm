"""Knowledge Base — upload → clean → chunk → embed → retrieve."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.permissions import PermissionCode, require_permission
from app.models.knowledge import Document, DocumentCategory, DocumentChunk, DocumentStatus
from app.services.rag import RagService, chunk_text


def clean_text(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def parse_upload(filename: str | None, content: str, content_type: str | None) -> str:
    """Phase 12 supports plain text / markdown. PDF/DOCX can plug in later."""
    ct = (content_type or "text/plain").lower()
    name = (filename or "").lower()
    if "pdf" in ct or name.endswith(".pdf"):
        # Placeholder: treat body as already-extracted text if client sends text
        return content
    return content


@dataclass
class KnowledgeHit:
    document_id: UUID
    title: str
    category: str
    chunk_index: int
    content: str
    score: float


class KnowledgeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.rag = RagService(db)

    async def upload(
        self,
        *,
        organization_id: UUID,
        uploaded_by: UUID,
        title: str,
        content: str,
        actor_permissions: set[str],
        category: DocumentCategory = DocumentCategory.COMPANY_KNOWLEDGE,
        filename: str | None = None,
        content_type: str = "text/plain",
        branch_id: UUID | None = None,
        auto_index: bool = True,
    ) -> Document:
        require_permission(actor_permissions, PermissionCode.KB_WRITE)
        raw = parse_upload(filename, content, content_type)
        cleaned = clean_text(raw)
        if not cleaned:
            raise ValueError("Document content is empty after cleaning")

        doc = Document(
            organization_id=organization_id,
            title=title,
            category=category,
            status=DocumentStatus.DRAFT,
            source_filename=filename,
            content_type=content_type,
            raw_text=raw,
            cleaned_text=cleaned,
            branch_id=branch_id,
            uploaded_by=uploaded_by,
        )
        self.db.add(doc)
        await self.db.flush()

        if auto_index:
            await self.index_document(doc.id, actor_permissions=actor_permissions)
            await self.db.refresh(doc)
        return doc

    async def index_document(
        self, document_id: UUID, *, actor_permissions: set[str]
    ) -> Document:
        require_permission(actor_permissions, PermissionCode.KB_WRITE)
        # Also need RAG_INDEX for embedding write
        require_permission(actor_permissions, PermissionCode.RAG_INDEX)

        doc = await self.db.scalar(
            select(Document)
            .options(selectinload(Document.chunks))
            .where(Document.id == document_id)
        )
        if not doc:
            raise ValueError("Document not found")

        # Replace chunks
        for existing in list(doc.chunks):
            await self.db.delete(existing)
        await self.db.flush()

        pieces = chunk_text(doc.cleaned_text, chunk_size=500, overlap=50)
        for i, piece in enumerate(pieces):
            self.db.add(
                DocumentChunk(
                    document_id=doc.id,
                    organization_id=doc.organization_id,
                    chunk_index=i,
                    content=piece,
                    content_hash=hashlib.sha256(piece.encode("utf-8")).hexdigest(),
                )
            )
        await self.db.flush()

        # Embed under entity_type=document
        await self.rag.index_text(
            organization_id=doc.organization_id,
            entity_type="document",
            entity_id=doc.id,
            content=doc.cleaned_text,
            actor_permissions=actor_permissions,
            metadata={
                "document_id": str(doc.id),
                "title": doc.title,
                "category": doc.category.value,
                "branch_id": str(doc.branch_id) if doc.branch_id else None,
                "visibility_scope": "organization",
            },
        )

        doc.chunk_count = len(pieces)
        doc.status = DocumentStatus.INDEXED
        await self.db.flush()
        return doc

    async def list_documents(
        self,
        organization_id: UUID,
        *,
        actor_permissions: set[str],
        category: DocumentCategory | None = None,
    ) -> list[Document]:
        require_permission(actor_permissions, PermissionCode.KB_READ)
        q = select(Document).where(Document.organization_id == organization_id)
        if category:
            q = q.where(Document.category == category)
        q = q.order_by(Document.created_at.desc())
        return list((await self.db.execute(q)).scalars().all())

    async def get_document(
        self, document_id: UUID, *, organization_id: UUID, actor_permissions: set[str]
    ) -> Document | None:
        require_permission(actor_permissions, PermissionCode.KB_READ)
        doc = await self.db.scalar(
            select(Document)
            .options(selectinload(Document.chunks))
            .where(Document.id == document_id, Document.organization_id == organization_id)
        )
        return doc

    async def search(
        self,
        *,
        organization_id: UUID,
        query: str,
        actor_permissions: set[str],
        category: str | None = None,
        top_k: int = 5,
    ) -> list[KnowledgeHit]:
        require_permission(actor_permissions, PermissionCode.KB_READ)
        require_permission(actor_permissions, PermissionCode.RAG_READ)

        hits = await self.rag.semantic_search(
            organization_id=organization_id,
            query=query,
            actor_permissions=actor_permissions,
            entity_types=["document"],
            top_k=top_k * 3,
            min_score=0.01,
        )

        out: list[KnowledgeHit] = []
        for h in hits:
            meta = h.metadata or {}
            if category and meta.get("category") != category:
                continue
            title = str(meta.get("title") or "Document")
            out.append(
                KnowledgeHit(
                    document_id=h.entity_id,
                    title=title,
                    category=str(meta.get("category") or ""),
                    chunk_index=int(h.chunk_id) if str(h.chunk_id).isdigit() else 0,
                    content=h.content,
                    score=h.score,
                )
            )
            if len(out) >= top_k:
                break
        return out
