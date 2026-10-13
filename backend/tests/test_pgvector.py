"""Tests for pgvector search on PostgreSQL."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pgvector import pgvector_semantic_search, sync_embedding_vectors
from app.services.rag import RagService
from app.services.search import SearchService


class TestPgvector:
    @pytest.mark.asyncio
    async def test_pgvector_semantic_search_empty_org(self, db: AsyncSession):
        hits = await pgvector_semantic_search(
            db,
            organization_id="00000000-0000-0000-0000-000000000000",
            query_vector=[0.1] * 64,
            top_k=5,
        )
        assert hits == []

    @pytest.mark.asyncio
    async def test_sync_embedding_vectors_with_no_rows(self, db: AsyncSession):
        count = await sync_embedding_vectors(db, model_name="hash-v1")
        assert count == 0


class TestSearchService:
    @pytest.mark.asyncio
    async def test_search_vehicles(self, seeded, db: AsyncSession):
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
        assert isinstance(hits, list)


class TestRagService:
    @pytest.mark.asyncio
    async def test_semantic_search(self, seeded, db: AsyncSession):
        from app.core.permissions import PermissionCode

        service = RagService(db)
        hits = await service.semantic_search(
            organization_id=seeded["org"].id,
            query="test vehicle",
            actor_permissions={PermissionCode.RAG_READ},
            top_k=5,
        )
        assert isinstance(hits, list)

    @pytest.mark.asyncio
    async def test_semantic_search_filters_by_branch(self, seeded, db: AsyncSession):
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
