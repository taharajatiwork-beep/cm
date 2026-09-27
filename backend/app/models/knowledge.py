from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class DocumentCategory(str, enum.Enum):
    COMPANY_KNOWLEDGE = "COMPANY_KNOWLEDGE"
    POLICY = "POLICY"
    SOP = "SOP"
    BRANCH_RULES = "BRANCH_RULES"
    SALES_RULES = "SALES_RULES"
    PURCHASE_RULES = "PURCHASE_RULES"
    COMMUNICATION_RULES = "COMMUNICATION_RULES"
    OTHER = "OTHER"


class DocumentStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    INDEXED = "INDEXED"
    ARCHIVED = "ARCHIVED"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[DocumentCategory] = mapped_column(
        Enum(DocumentCategory, name="document_category"),
        default=DocumentCategory.COMPANY_KNOWLEDGE,
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"),
        default=DocumentStatus.DRAFT,
    )
    source_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100), default="text/plain")
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_text: Mapped[str] = mapped_column(Text, nullable=False)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chunks: Mapped[list[DocumentChunk]] = relationship(back_populates="document")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="chunks")
