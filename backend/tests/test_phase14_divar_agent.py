from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.integrations.divar import reset_fake_divar_client
from app.models.ai_audit import AiActionLog
from app.models.divar import DivarListing
from tests.conftest import auth, login


@pytest.fixture(autouse=True)
def _fresh_fake_divar():
    reset_fake_divar_client()
    yield
    reset_fake_divar_client()


@pytest.mark.asyncio
async def test_divar_agent_prepare_listing(client: AsyncClient, seeded, db):
    token = await login(client, "ali@autoco.example")
    headers = auth(token)

    vehicle = await client.post(
        "/inventory/vehicles",
        headers=headers,
        json={
            "vin": "JTDBR32E720077701",
            "brand": "Toyota",
            "model": "Camry",
            "year": 2020,
            "stock_number": "701",
            "color": "سفید",
            "mileage": 45000,
            "sale_price": 1200000000,
            "branch_id": str(seeded["branch"].id),
        },
    )
    assert vehicle.status_code == 200, vehicle.text
    vehicle_id = vehicle.json()["id"]

    r = await client.post(
        "/agent/divar",
        headers=headers,
        json={"vehicle_id": vehicle_id, "auto_create": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["intent"] == "prepare"
    assert body["listings_prepared"] == 1
    assert len(body["listing_ids"]) == 1
    assert len(body["work_item_ids"]) == 1
    assert "human-only" in body["message"].lower() or "Human" in body["message"]
    tools = {t["tool"] for t in body["tool_trace"]}
    assert "prepare_divar_listing" in tools

    listing = await db.get(DivarListing, UUID(body["listing_ids"][0]))
    assert listing is not None
    assert listing.divar_product_id
    assert listing.divar_task_id
    assert listing.vehicle_id is not None
    assert str(listing.vehicle_id) == vehicle_id

    logs = list(
        (
            await db.execute(
                select(AiActionLog).where(AiActionLog.request_id == body["request_id"])
            )
        )
        .scalars()
        .all()
    )
    assert any(log.agent == "DivarAgent" for log in logs)

    # Idempotent — existing open listing
    r2 = await client.post(
        "/agent/divar",
        headers=headers,
        json={"vehicle_id": vehicle_id, "auto_create": True},
    )
    assert r2.status_code == 200
    assert r2.json()["listings_prepared"] == 1
    data = r2.json()["tool_trace"][-1]["result"]["data"]
    assert data.get("already_exists") is True


@pytest.mark.asyncio
async def test_divar_agent_candidates_and_recommend(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    headers = auth(token)

    await client.post(
        "/inventory/vehicles",
        headers=headers,
        json={
            "vin": "JTDBR32E720077702",
            "brand": "Honda",
            "model": "Accord",
            "year": 2019,
            "stock_number": "702",
            "sale_price": 900000000,
            "branch_id": str(seeded["branch"].id),
        },
    )

    cand = await client.post(
        "/agent/divar",
        headers=headers,
        json={"message": "list candidates"},
    )
    assert cand.status_code == 200
    assert cand.json()["intent"] == "candidates"
    assert "Accord" in cand.json()["message"]

    rec = await client.post(
        "/agent/divar",
        headers=headers,
        json={"message": "scan only", "auto_create": False, "limit": 2},
    )
    assert rec.status_code == 200
    assert rec.json()["intent"] == "recommend"
    assert rec.json()["listings_prepared"] == 0


@pytest.mark.asyncio
async def test_divar_agent_permission_denied(client: AsyncClient, seeded):
    token = await login(client, "viewer@autoco.example")
    r = await client.post("/agent/divar", headers=auth(token), json={})
    assert r.status_code == 403
