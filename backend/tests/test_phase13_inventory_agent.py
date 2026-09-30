from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import CommunicationCase
from app.models.ai_audit import AiActionLog
from app.models.enums import CaseType
from app.models.inventory import Vehicle
from app.services import OrgService
from tests.conftest import auth, login


async def _age_vehicle(db, vehicle_id, days: int = 35):
    vehicle = await db.get(Vehicle, UUID(str(vehicle_id)))
    assert vehicle is not None
    vehicle.created_at = datetime.now(UTC) - timedelta(days=days)
    await db.commit()


@pytest.mark.asyncio
async def test_inventory_agent_creates_opportunity(client: AsyncClient, seeded, db):
    token = await login(client, "ali@autoco.example")
    headers = auth(token)

    vehicle = await client.post(
        "/inventory/vehicles",
        headers=headers,
        json={
            "vin": "JTDBR32E720099901",
            "brand": "Toyota",
            "model": "Camry",
            "year": 2019,
            "stock_number": "901",
            "branch_id": str(seeded["branch"].id),
        },
    )
    assert vehicle.status_code == 200, vehicle.text
    vehicle_id = vehicle.json()["id"]
    await _age_vehicle(db, vehicle_id, days=40)

    branch_b = await OrgService(db).create_branch(
        seeded["org"].id, "North Branch", "NORTH", city="North"
    )
    await db.commit()

    for branch_id, subject in [
        (str(seeded["branch"].id), "Need Camry for showroom"),
        (str(branch_b.id), "Transfer request Camry 901"),
    ]:
        r = await client.post(
            "/inventory/requests",
            headers=headers,
            json={
                "vehicle_id": vehicle_id,
                "requesting_branch_id": branch_id,
                "subject": subject,
                "request_type": "TRANSFER",
            },
        )
        assert r.status_code == 200, r.text

    interest = await client.post(
        "/cases",
        headers=headers,
        json={
            "subject": "Buyer asking about Camry 901",
            "type": "CUSTOMER_INTEREST",
            "vehicle_id": vehicle_id,
            "priority": "HIGH",
        },
    )
    assert interest.status_code == 200, interest.text

    r = await client.post(
        "/agent/inventory",
        headers=headers,
        json={"min_days": 30, "min_branch_requests": 2, "auto_create": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["intent"] == "create_opportunities"
    assert body["opportunities_found"] >= 1
    assert len(body["cases_created"]) >= 1
    assert len(body["work_item_ids"]) >= 1
    tools = {t["tool"] for t in body["tool_trace"]}
    assert "list_aging_inventory" in tools
    assert "detect_inventory_opportunities" in tools
    assert "create_inventory_opportunity" in tools

    case = await db.get(CommunicationCase, UUID(body["cases_created"][0]))
    assert case is not None
    assert case.type == CaseType.INVENTORY_OPPORTUNITY
    assert str(case.vehicle_id) == vehicle_id

    logs = list(
        (
            await db.execute(
                select(AiActionLog).where(AiActionLog.request_id == body["request_id"])
            )
        )
        .scalars()
        .all()
    )
    assert any(log.agent == "InventoryAgent" for log in logs)

    r2 = await client.post(
        "/agent/inventory",
        headers=headers,
        json={"min_days": 30, "min_branch_requests": 2, "auto_create": True},
    )
    assert r2.status_code == 200
    assert r2.json()["opportunities_found"] == 0


@pytest.mark.asyncio
async def test_inventory_agent_recommend_only(client: AsyncClient, seeded, db):
    token = await login(client, "ali@autoco.example")
    headers = auth(token)

    vehicle = await client.post(
        "/inventory/vehicles",
        headers=headers,
        json={
            "vin": "JTDBR32E720099902",
            "brand": "Honda",
            "model": "Accord",
            "year": 2018,
            "stock_number": "902",
            "branch_id": str(seeded["branch"].id),
        },
    )
    vehicle_id = vehicle.json()["id"]
    await _age_vehicle(db, vehicle_id, days=45)

    branch_b = await OrgService(db).create_branch(
        seeded["org"].id, "East Branch", "EAST", city="East"
    )
    await db.commit()

    for branch_id in [str(seeded["branch"].id), str(branch_b.id)]:
        r = await client.post(
            "/inventory/requests",
            headers=headers,
            json={
                "vehicle_id": vehicle_id,
                "requesting_branch_id": branch_id,
                "subject": "Demand",
            },
        )
        assert r.status_code == 200, r.text

    r = await client.post(
        "/agent/inventory",
        headers=headers,
        json={"message": "scan only", "min_days": 30, "auto_create": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["intent"] == "recommend"
    assert body["opportunities_found"] >= 1
    assert body["cases_created"] == []


@pytest.mark.asyncio
async def test_inventory_agent_permission_denied(client: AsyncClient, seeded):
    token = await login(client, "viewer@autoco.example")
    r = await client.post("/agent/inventory", headers=auth(token), json={})
    assert r.status_code == 403
