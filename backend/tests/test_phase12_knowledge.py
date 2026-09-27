import pytest
from httpx import AsyncClient

from tests.conftest import auth, login


SOP_TEXT = """
Communication SOP

1. Always create a WorkItem when two or more people must collaborate on a vehicle sale.
2. Confirm the stock number before assigning tasks.
3. Escalate HIGH priority cases if there is no response within two hours.
4. Marketing must not publish a listing until inventory status is IN_STOCK or RESERVED.
"""


@pytest.mark.asyncio
async def test_upload_index_and_search_sop(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    uploaded = await client.post(
        "/knowledge/documents",
        headers=auth(token),
        json={
            "title": "Communication Rules",
            "category": "COMMUNICATION_RULES",
            "filename": "comms-sop.md",
            "content": SOP_TEXT,
            "auto_index": True,
        },
    )
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["status"] == "INDEXED"
    assert body["chunk_count"] >= 1

    listed = await client.get("/knowledge/documents", headers=auth(token))
    assert listed.status_code == 200
    assert any(d["id"] == body["id"] for d in listed.json())

    detail = await client.get(f"/knowledge/documents/{body['id']}", headers=auth(token))
    assert detail.status_code == 200
    assert "WorkItem" in detail.json()["cleaned_text"]
    assert len(detail.json()["chunks"]) >= 1

    search = await client.post(
        "/knowledge/search",
        headers=auth(token),
        json={"query": "escalate high priority cases response time", "top_k": 3},
    )
    assert search.status_code == 200, search.text
    assert len(search.json()) >= 1
    assert search.json()[0]["document_id"] == body["id"]
    assert "escalat" in search.json()[0]["content"].lower() or "two hours" in search.json()[0]["content"].lower()


@pytest.mark.asyncio
async def test_kb_permission_denied(client: AsyncClient, seeded):
    token = await login(client, "viewer@autoco.example")
    r = await client.get("/knowledge/documents", headers=auth(token))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_seller_can_read_but_not_write(client: AsyncClient, seeded):
    # Seed as manager
    admin = await login(client, "ali@autoco.example")
    await client.post(
        "/knowledge/documents",
        headers=auth(admin),
        json={
            "title": "Sales Rules",
            "category": "SALES_RULES",
            "content": "Never invent a buyer. Always link the vehicle_id on the case.",
        },
    )

    seller = await login(client, "reza@autoco.example")
    listed = await client.get("/knowledge/documents", headers=auth(seller))
    assert listed.status_code == 200
    assert len(listed.json()) >= 1

    denied = await client.post(
        "/knowledge/documents",
        headers=auth(seller),
        json={"title": "Hack", "content": "x"},
    )
    assert denied.status_code == 403
