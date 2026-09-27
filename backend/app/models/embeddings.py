from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Embedding(Base):
    """Semantic memory chunks. Never the source of truth for structured fields."""

    __tablename__ = "embeddings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "entity_type",
            "entity_id",
            "chunk_id",
            "embedding_model",
            name="uq_embedding_chunk",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    chunk_id: Mapped[str] = mapped_column(String(64), nullable=False, default="0")

    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # JSON array of floats — portable across SQLite/Postgres; pgvector can replace later
    embedding: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1")
    dims: Mapped[int] = mapped_column(Integer, nullable=False)

    # JSON metadata: branch_id, vehicle_id, case_id, user_id, visibility_scope, ...
    metadata_json: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
