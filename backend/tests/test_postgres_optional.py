"""Runs only when POSTGRES_TEST_URL is set. The default suite stays on SQLite."""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("POSTGRES_TEST_URL"),
    reason="POSTGRES_TEST_URL is not set",
)


@pytest.mark.asyncio
async def test_postgres_select_and_fts_function():
    import asyncpg

    url = os.environ["POSTGRES_TEST_URL"].replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)
    try:
        value = await conn.fetchval("SELECT 1")
        assert value == 1
        hits = await conn.fetchval(
            "SELECT to_tsvector('simple', $1) @@ plainto_tsquery('simple', $2)",
            "camry inventory",
            "camry",
        )
        assert hits is True
    finally:
        await conn.close()
