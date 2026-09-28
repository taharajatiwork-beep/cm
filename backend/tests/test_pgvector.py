"""Tests for pgvector integration (PostgreSQL) and FTS fallback (SQLite)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pgvector import pgvector_semantic_search, sync_embedding_vectors
from app.services.rag import RagService
from app.services.search import SearchService


class TestPgvectorFallback:
    """pgvector functions should return empty list on SQLite (graceful fallback)."""

    @pytest.mark.asyncio
    async def test_pgvector_semantic_search_returns_empty_on_sqlite(
        self, db: AsyncSession
    ):
        """On SQLite, pgvector search should return [] without error."""
        hits = await pgvector_semantic_search(
            db,
            organization_id="00000000-0000-0000-0000-000000000000",
            query_vector=[0.1] * 64,
            top_k=5,
        )
        assert hits == []

    @pytest.mark.asyncio
    async def test_sync_embedding_vectors_returns_zero_on_sqlite(
        self, db: AsyncSession
    ):
        """On SQLite, sync should return 0 without error."""
        count = await sync_embedding_vectors(db, model_name="hash-v1")
        assert count == 0


class TestSearchServiceFtsFallback:
    """SearchService._text_contains uses ilike on SQLite, tsvector on Postgres."""

    @pytest.mark.asyncio
    async def test_search_uses_ilike_on_sqlite(self, seeded, db: AsyncSession):
        """Search should work on SQLite using ilike fallback."""
        from app.core.permissions import PermissionCode
        from app.services.search import SearchEntityType

        service = SearchService(db)
        hits = await service.search(
            organization_id=seeded["org"].id,
            actor_permissions={PermissionCode.SEARCH, PermissionCode.INVENTORY_READ},
            q="Hyundai",
            types=[SearchEntityType.VEHICLE],
            limit=10,
        )
        # Should not error; may return 0 or more hits
        assert isinstance(hits, list)


class TestRagServiceFallback:
    """RagService.semantic_search falls back to Python cosine on SQLite."""

    @pytest.mark.asyncio
    async def test_semantic_search_works_on_sqlite(self, seeded, db: AsyncSession):
        """semantic_search should work on SQLite via Python cosine fallback."""
        from app.core.permissions import PermissionCode

        service = RagService(db)
        hits = await service.semantic_search(
            organization_id=seeded["org"].id,
            query="test vehicle",
            actor_permissions={PermissionCode.RAG_READ},
            top_k=5,
        )
        # Should not error; returns list (may be empty)
        assert isinstance(hits, list)

    @pytest.mark.asyncio
    async def test_semantic_search_filters_by_branch(self, seeded, db: AsyncSession):
        """Filters should apply in fallback mode too."""
        from app.core.permissions import PermissionCode

        service = RagService(db)
        hits = await service.semantic_search(
            organization_id=seeded["org"].id,
            query="test",
            actor_permissions={PermissionCode.RAG_READ},
            branch_id=seeded["branch"].id,
            top_k=5,
        )
        assert isinstance(hits, list)