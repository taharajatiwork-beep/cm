from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, handle_authz
from app.core.permissions import AuthorizationError
from app.db.session import get_db
from app.models.knowledge import DocumentCategory
from app.services.knowledge import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class UploadBody(BaseModel):
    title: str
    content: str
    category: DocumentCategory = DocumentCategory.COMPANY_KNOWLEDGE
    filename: str | None = None
    content_type: str = "text/plain"
    branch_id: UUID | None = None
    auto_index: bool = True


class DocumentOut(BaseModel):
    id: UUID
    title: str
    category: DocumentCategory
    status: str
    source_filename: str | None
    chunk_count: int
    branch_id: UUID | None

    model_config = {"from_attributes": True}


class DocumentDetailOut(DocumentOut):
    cleaned_text: str
    chunks: list[dict]


class SearchBody(BaseModel):
    query: str = Field(min_length=1)
    category: str | None = None
    top_k: int = 5


class KnowledgeHitOut(BaseModel):
    document_id: UUID
    title: str
    category: str
    chunk_index: int
    content: str
    score: float


@router.post("/documents", response_model=DocumentOut)
async def upload_document(
    body: UploadBody,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        doc = await KnowledgeService(db).upload(
            organization_id=ctx.organization_id,
            uploaded_by=ctx.user.id,
            title=body.title,
            content=body.content,
            actor_permissions=ctx.permissions,
            category=body.category,
            filename=body.filename,
            content_type=body.content_type,
            branch_id=body.branch_id,
            auto_index=body.auto_index,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return DocumentOut(
        id=doc.id,
        title=doc.title,
        category=doc.category,
        status=doc.status.value,
        source_filename=doc.source_filename,
        chunk_count=doc.chunk_count,
        branch_id=doc.branch_id,
    )


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(
    category: DocumentCategory | None = None,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        docs = await KnowledgeService(db).list_documents(
            ctx.organization_id,
            actor_permissions=ctx.permissions,
            category=category,
            scope=ctx.scope,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return [
        DocumentOut(
            id=d.id,
            title=d.title,
            category=d.category,
            status=d.status.value,
            source_filename=d.source_filename,
            chunk_count=d.chunk_count,
            branch_id=d.branch_id,
        )
        for d in docs
    ]


@router.get("/documents/{document_id}", response_model=DocumentDetailOut)
async def get_document(
    document_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        doc = await KnowledgeService(db).get_document(
            document_id,
            organization_id=ctx.organization_id,
            actor_permissions=ctx.permissions,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    if not doc:
        raise HTTPException(404, "Document not found")
    return DocumentDetailOut(
        id=doc.id,
        title=doc.title,
        category=doc.category,
        status=doc.status.value,
        source_filename=doc.source_filename,
        chunk_count=doc.chunk_count,
        branch_id=doc.branch_id,
        cleaned_text=doc.cleaned_text,
        chunks=[
            {"index": c.chunk_index, "content": c.content}
            for c in sorted(doc.chunks, key=lambda x: x.chunk_index)
        ],
    )


@router.post("/documents/{document_id}/index", response_model=DocumentOut)
async def reindex_document(
    document_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        doc = await KnowledgeService(db).index_document(
            document_id,
            actor_permissions=ctx.permissions,
            organization_id=ctx.organization_id,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return DocumentOut(
        id=doc.id,
        title=doc.title,
        category=doc.category,
        status=doc.status.value,
        source_filename=doc.source_filename,
        chunk_count=doc.chunk_count,
        branch_id=doc.branch_id,
    )


@router.post("/search", response_model=list[KnowledgeHitOut])
async def search_knowledge(
    body: SearchBody,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        hits = await KnowledgeService(db).search(
            organization_id=ctx.organization_id,
            query=body.query,
            actor_permissions=ctx.permissions,
            category=body.category,
            top_k=body.top_k,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return [
        KnowledgeHitOut(
            document_id=h.document_id,
            title=h.title,
            category=h.category,
            chunk_index=h.chunk_index,
            content=h.content,
            score=h.score,
        )
        for h in hits
    ]
