"""pgvector integration for PostgreSQL â€” zero-impact on SQLite.

Adds a vector column and ivfflat index when dialect is postgresql.
Keeps the JSON text column as the portable source of truth.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import DDL, event, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.embeddings import Embedding as EmbeddingModel

log = get_logger(__name__)


def _add_pgvector_column() -> None:
    """Attach pgvector column to Embedding table on PostgreSQL only."""
    @event.listens_for(EmbeddingModel.__table__, "after_create")
    def _create_pgvector_column(target, connection, **kw):
        bind = connection
        if bind.dialect.name != "postgresql":
            return
        try:
            # Enable pgvector extension
            connection.execute(DDL("CREATE EXTENSION IF NOT EXISTS vector"))
            # Add vector column (dimension from settings, default 64)
            connection.execute(DDL("""
                ALTER TABLE embeddings
                ADD COLUMN IF NOT EXISTS embedding_vec vector(64)
            """))
            # Create IVFFlat index for ANN (tune lists based on row count)
            connection.execute(DDL("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_embedding_vec
                ON embeddings USING ivfflat (embedding_vec vector_cosine_ops)
                WITH (lists = 100)
            """))
        except Exception as exc:  # noqa: BLE001 - pgvector missing: continue with JSON fallback
            log.info("pgvector_unavailable", error=str(exc))


# Call at module import to register the event
_add_pgvector_column()


# ============================================================
# Vector search helpers (PostgreSQL only)
# ============================================================

async def pgvector_semantic_search(
    db: AsyncSession,
    *,
    organization_id: str,
    query_vector: list[float],
    entity_types: list[str] | None = None,
    branch_id: str | None = None,
    vehicle_id: str | None = None,
    top_k: int = 5,
    min_score: float = 0.05,
    model_name: str = "hash-v1",
) -> list[dict[str, Any]]:
    """Fast ANN search using pgvector on PostgreSQL.
    
    Returns list of dicts with keys: embedding_id, entity_type, entity_id, 
    chunk_id, content, score, metadata.
    
    Falls back to empty list if pgvector not available.
    """
    bind = db.bind
    if bind is None or bind.dialect.name != "postgresql":
        return []

    try:
        vec_literal = "[" + ",".join(str(x) for x in query_vector) + "]"
        sql = f"""
            SELECT id, entity_type, entity_id, chunk_id, content, metadata_json,
                   1 - (embedding_vec <=> '{vec_literal}'::vector) AS score
            FROM embeddings
            WHERE organization_id = :org_id
              AND embedding_model = :model
              AND embedding_vec IS NOT NULL
        """
        params = {"org_id": organization_id, "model": model_name}
        
        if entity_types:
            placeholders = ",".join([f":et{i}" for i in range(len(entity_types))])
            sql += f" AND entity_type IN ({placeholders})"
            for i, et in enumerate(entity_types):
                params[f"et{i}"] = et
        
        sql += " ORDER BY embedding_vec <=> :vec LIMIT :limit"
        params["vec"] = vec_literal
        params["limit"] = str(top_k)  # SQL parameter needs string

        rows = await db.execute(text(sql), params)
        
        hits = []
        for row in rows:
            meta = json.loads(row.metadata_json) if row.metadata_json else {}
            if branch_id and meta.get("branch_id") != branch_id:
                continue
            if vehicle_id and meta.get("vehicle_id") != vehicle_id:
                continue
            if row.score < min_score:
                continue
            hits.append({
                "embedding_id": row.id,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "chunk_id": row.chunk_id,
                "content": row.content,
                "score": float(row.score),
                "metadata": meta,
            })
        return hits
    except Exception:  # noqa: BLE001 - caller falls back to Python cosine
        # pgvector not available or error â€” caller should fallback to Python cosine
        return []


async def sync_embedding_vectors(db: AsyncSession, model_name: str = "hash-v1", batch: int = 500) -> int:
    """Backfill embedding_vec from embedding_json for existing rows.
    Run after enabling pgvector on an existing database.
    """
    bind = db.bind
    if bind is None or bind.dialect.name != "postgresql":
        return 0

    try:
        # Find rows with JSON but no vector
        result = await db.execute(
            select(EmbeddingModel.id, EmbeddingModel.embedding)
            .where(
                EmbeddingModel.embedding_model == model_name,
                # column is added by DDL at runtime, so it is not on the mapped class
                getattr(EmbeddingModel, "embedding_vec").is_(None),  # noqa: B009
            )
            .limit(batch)
        )
        rows = result.all()
        if not rows:
            return 0
        
        for row in rows:
            try:
                vec = json.loads(row.embedding)
                vec_literal = "[" + ",".join(str(x) for x in vec) + "]"
                await db.execute(
                    text("UPDATE embeddings SET embedding_vec = :vec WHERE id = :id"),
                    {"vec": vec_literal, "id": row.id}
                )
            except Exception:  # noqa: BLE001 - skip unconvertible row
                continue
        
        await db.commit()
        return len(rows)
    except Exception:  # noqa: BLE001 - backfill is best effort
        return 0
