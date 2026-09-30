from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.services.hybrid_rag import QueryAnalyzer, reciprocal_rank_fusion
from tests.conftest import auth, login


def test_query_analyzer_extracts_structured_fields():
    a = QueryAnalyzer().analyze("Check VIN JTDBR32E720012424 and stock #124 please")
    assert a.vin == "JTDBR32E720012424"
    assert a.stock_number == "124"
    assert a.intent == "lookup"


def test_query_analyzer_vehicle_status_not_policy():
    a = QueryAnalyzer().analyze("Hyundai Elantra (2021) چه وضعیتی دارد")
    assert a.brand and a.brand.lower() == "hyundai"
    assert a.model and a.model.lower() == "elantra"
    assert a.wants_status
    assert "vehicle" in a.entity_types
    assert "document" not in a.entity_types
    assert a.intent == "lookup"


def test_query_analyzer_persian_model_and_digits():
    a = QueryAnalyzer().analyze("النترا ۲۰۲۱ موجود است؟")
    assert a.model == "Elantra"
    assert "vehicle" in a.entity_types
    assert "2021" in a.free_text


@pytest.mark.asyncio
async def test_hybrid_vehicle_status_prefers_vehicle(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    vehicle = await client.post(
        "/inventory/vehicles",
        headers=auth(token),
        json={
            "vin": "KMHD84LF5JU999888",
            "brand": "Hyundai",
            "model": "Elantra",
            "year": 2021,
            "stock_number": "2109",
            "color": "Silver",
            "status": "IN_STOCK",
            "branch_id": str(seeded["branch"].id),
        },
    )
    assert vehicle.status_code == 200, vehicle.text
    vid = vehicle.json()["id"]
    await client.post(
        "/rag/index",
        headers=auth(token),
        json={"entity_type": "vehicle", "entity_id": vid},
    )

    hybrid = await client.post(
        "/rag/hybrid",
        headers=auth(token),
        json={"query": "Hyundai Elantra (2021) چه وضعیتی دارد", "top_k": 5},
    )
    assert hybrid.status_code == 200, hybrid.text
    body = hybrid.json()
    assert body["total"] >= 1
    assert body["hits"][0]["entity_type"] == "vehicle"
    assert body["hits"][0]["entity_id"] == vid
    assert "Elantra" in body["answer"] or "النترا" in body["answer"] or "IN_STOCK" in body["answer"]


def test_rrf_prefers_multi_list_agreement():
    id1, id2 = uuid4(), uuid4()
    scores = reciprocal_rank_fusion(
        [
            [("vehicle", id1, 10.0), ("vehicle", id2, 5.0)],
            [("vehicle", id1, 0.9), ("case", id2, 0.8)],
        ]
    )
    assert scores[("vehicle", id1)] > scores[("vehicle", id2)]


@pytest.mark.asyncio
async def test_hybrid_fuses_sql_and_vector(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    vin = "JTDBR32E720066666"
    vehicle = await client.post(
        "/inventory/vehicles",
        headers=auth(token),
        json={
            "vin": vin,
            "brand": "Toyota",
            "model": "Camry",
            "year": 2021,
            "stock_number": "666",
            "color": "Silver",
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
    assert indexed.status_code == 200

    # Noise entity
    other = await client.post(
        "/cases",
        headers=auth(token),
        json={"subject": "Printer toner request", "type": "GENERAL_OPERATIONAL_REQUEST"},
    )
    await client.post(
        "/rag/index",
        headers=auth(token),
        json={"entity_type": "case", "entity_id": other.json()["id"]},
    )

    hybrid = await client.post(
        "/rag/hybrid",
        headers=auth(token),
        json={
            "query": f"Find silver Camry stock #666 VIN {vin}",
            "top_k": 5,
        },
    )
    assert hybrid.status_code == 200, hybrid.text
    body = hybrid.json()
    assert body["request_id"]
    assert body["analyzed"]["vin"] == vin
    assert body["analyzed"]["stock_number"] == "666"
    assert body["total"] >= 1
    assert body["hits"][0]["entity_id"] == vid
    assert "exact" in body["hits"][0]["sources"] or "sql" in body["hits"][0]["sources"]
    assert body["context"]
    assert "Camry" in body["answer"] or "vehicle" in body["answer"].lower()
    assert len(body["context"]) <= 4000


@pytest.mark.asyncio
async def test_hybrid_semantic_work_item(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    wi = await client.post(
        "/work-items",
        headers=auth(token),
        json={
            "title": "Sell Camry #124",
            "description": "برای فروش این کمری رضا مشتری‌ها را پیگیری کند",
        },
    )
    assert wi.status_code == 200
    wid = wi.json()["id"]
    await client.post(
        "/rag/index",
        headers=auth(token),
        json={"entity_type": "work_item", "entity_id": wid},
    )

    hybrid = await client.post(
        "/rag/hybrid",
        headers=auth(token),
        json={"query": "فروش کمری و پیگیری مشتری توسط رضا", "top_k": 5},
    )
    assert hybrid.status_code == 200, hybrid.text
    ids = {h["entity_id"] for h in hybrid.json()["hits"]}
    assert wid in ids
    assert hybrid.json()["context"]


@pytest.mark.asyncio
async def test_hybrid_permission_denied(client: AsyncClient, seeded):
    token = await login(client, "viewer@autoco.example")
    r = await client.post(
        "/rag/hybrid",
        headers=auth(token),
        json={"query": "Camry"},
    )
    assert r.status_code == 403
