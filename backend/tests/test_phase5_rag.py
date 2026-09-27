import uuid

import pytest
from httpx import AsyncClient

from app.ai.embeddings import HashEmbeddingProvider, cosine_similarity
from tests.conftest import auth, login


@pytest.mark.asyncio
async def test_hash_embeddings_are_deterministic():
    p = HashEmbeddingProvider(dims=32)
    a = (await p.embed(["Toyota Camry white"]))[0]
    b = (await p.embed(["Toyota Camry white"]))[0]
    c = (await p.embed(["completely unrelated quantum physics"]))[0]
    assert a == b
    assert cosine_similarity(a, b) > 0.99
    assert cosine_similarity(a, c) < cosine_similarity(a, b)


@pytest.mark.asyncio
async def test_index_and_semantic_query_vehicle(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    vehicle = await client.post(
        "/inventory/vehicles",
        headers=auth(token),
        json={
            "vin": "JTDBR32E720055555",
            "brand": "Toyota",
            "model": "Camry",
            "year": 2020,
            "stock_number": "555",
            "color": "White",
            "branch_id": str(seeded["branch"].id),
        },
    )
    assert vehicle.status_code == 200, vehicle.text
    vid = vehicle.json()["id"]

    indexed = await client.post(
        "/rag/index",
        headers=auth(token),
        json={"entity_type": "vehicle", "entity_id": vid},
    )
    assert indexed.status_code == 200, indexed.text
    assert indexed.json()["chunks_indexed"] >= 1

    # Also index an unrelated case so retrieval must rank Camry higher
    case = await client.post(
        "/cases",
        headers=auth(token),
        json={"subject": "Office supplies order", "type": "GENERAL_OPERATIONAL_REQUEST"},
    )
    assert case.status_code == 200
    await client.post(
        "/rag/index",
        headers=auth(token),
        json={"entity_type": "case", "entity_id": case.json()["id"]},
    )

    q = await client.post(
        "/rag/query",
        headers=auth(token),
        json={"query": "white Toyota Camry sedan", "top_k": 5, "min_score": 0.01},
    )
    assert q.status_code == 200, q.text
    assert q.json()["total"] >= 1
    top = q.json()["hits"][0]
    assert top["entity_type"] == "vehicle"
    assert top["entity_id"] == vid
    assert "Camry" in top["content"]
    assert "request_id" in top["metadata"]


@pytest.mark.asyncio
async def test_index_work_item_persian_description(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    wi = await client.post(
        "/work-items",
        headers=auth(token),
        json={
            "title": "Sell Camry #124",
            "description": "برای فروش این کمری، رضا مشتری‌ها رو پیگیری کنه و سارا آگهی رو آماده کنه.",
        },
    )
    assert wi.status_code == 200
    wid = wi.json()["id"]

    indexed = await client.post(
        "/rag/index",
        headers=auth(token),
        json={"entity_type": "work_item", "entity_id": wid},
    )
    assert indexed.status_code == 200
    assert indexed.json()["chunks_indexed"] >= 1

    q = await client.post(
        "/rag/query",
        headers=auth(token),
        json={
            "query": "فروش کمری و پیگیری مشتری",
            "entity_types": ["work_item"],
            "top_k": 3,
            "min_score": 0.01,
        },
    )
    assert q.status_code == 200
    assert any(h["entity_id"] == wid for h in q.json()["hits"])


@pytest.mark.asyncio
async def test_custom_index_and_rag_permission_denied(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    doc_id = str(uuid.uuid4())
    r = await client.post(
        "/rag/index",
        headers=auth(token),
        json={
            "entity_type": "custom",
            "entity_id": doc_id,
            "content": "Company SOP: always confirm vehicle stock number before creating transfer cases.",
        },
    )
    assert r.status_code == 200

    viewer = await login(client, "viewer@autoco.example")
    denied = await client.post(
        "/rag/query",
        headers=auth(viewer),
        json={"query": "stock number transfer"},
    )
    assert denied.status_code == 403
