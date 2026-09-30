from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import CommunicationCase
from app.models.ai_audit import AiActionLog
from app.models.enums import CaseType
from tests.conftest import auth, login


async def _age_case(db, case_id: str, days: int = 5):
    case = await db.get(CommunicationCase, UUID(case_id))
    assert case is not None
    case.created_at = datetime.now(UTC) - timedelta(days=days)
    await db.commit()


@pytest.mark.asyncio
async def test_sales_agent_creates_follow_up(client: AsyncClient, seeded, db):
    token = await login(client, "ali@autoco.example")
    headers = auth(token)

    vehicle = await client.post(
        "/inventory/vehicles",
        headers=headers,
        json={
            "vin": "JTDBR32E720088801",
            "brand": "Toyota",
            "model": "Camry",
            "year": 2020,
            "stock_number": "801",
            "branch_id": str(seeded["branch"].id),
        },
    )
    assert vehicle.status_code == 200, vehicle.text
    vehicle_id = vehicle.json()["id"]

    buyer = await client.post(
        "/cases",
        headers=headers,
        json={
            "subject": "خریدار دنبال کمری سفید است",
            "type": "BUYER_REQUEST",
            "vehicle_id": vehicle_id,
            "priority": "HIGH",
        },
    )
    assert buyer.status_code == 200, buyer.text
    case_id = buyer.json()["id"]
    await _age_case(db, case_id, days=5)

    r = await client.post(
        "/agent/sales",
        headers=headers,
        json={"stale_days": 3, "auto_create": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["intent"] == "create_follow_ups"
    assert body["follow_ups_found"] >= 1
    assert len(body["cases_created"]) >= 1
    assert len(body["work_item_ids"]) >= 1
    assert len(body["task_ids"]) >= 1
    tools = {t["tool"] for t in body["tool_trace"]}
    assert "detect_sales_follow_ups" in tools
    assert "create_sales_follow_up" in tools

    follow = await db.get(CommunicationCase, UUID(body["cases_created"][0]))
    assert follow is not None
    assert follow.type == CaseType.FOLLOW_UP
    assert follow.owner_id is not None

    logs = list(
        (
            await db.execute(
                select(AiActionLog).where(AiActionLog.request_id == body["request_id"])
            )
        )
        .scalars()
        .all()
    )
    assert any(log.agent == "SalesAgent" for log in logs)

    # Idempotent — already covered by open FOLLOW_UP on same vehicle
    r2 = await client.post(
        "/agent/sales",
        headers=headers,
        json={"stale_days": 3, "auto_create": True},
    )
    assert r2.status_code == 200
    assert r2.json()["follow_ups_found"] == 0


@pytest.mark.asyncio
async def test_sales_agent_match_inventory(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    headers = auth(token)

    await client.post(
        "/inventory/vehicles",
        headers=headers,
        json={
            "vin": "JTDBR32E720088802",
            "brand": "Toyota",
            "model": "Camry",
            "year": 2021,
            "stock_number": "802",
            "branch_id": str(seeded["branch"].id),
        },
    )
    buyer = await client.post(
        "/cases",
        headers=headers,
        json={"subject": "نیاز به کمری برای مشتری", "type": "CUSTOMER_INTEREST"},
    )
    case_id = buyer.json()["id"]

    r = await client.post(
        "/agent/sales",
        headers=headers,
        json={"message": "match inventory", "case_id": case_id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["intent"] == "match"
    assert "Matched case" in body["message"]
    assert "Camry" in body["message"]
    tools = {t["tool"] for t in body["tool_trace"]}
    assert "match_buyer_to_inventory" in tools


@pytest.mark.asyncio
async def test_sales_agent_pipeline_and_recommend(client: AsyncClient, seeded, db):
    token = await login(client, "ali@autoco.example")
    headers = auth(token)

    buyer = await client.post(
        "/cases",
        headers=headers,
        json={"subject": "Buyer wants Accord", "type": "BUYER_REQUEST"},
    )
    await _age_case(db, buyer.json()["id"], days=4)

    pipe = await client.post(
        "/agent/sales",
        headers=headers,
        json={"message": "list pipeline"},
    )
    assert pipe.status_code == 200
    assert pipe.json()["intent"] == "pipeline"
    assert "Sales pipeline" in pipe.json()["message"]

    rec = await client.post(
        "/agent/sales",
        headers=headers,
        json={"message": "scan only", "stale_days": 3, "auto_create": False},
    )
    assert rec.status_code == 200
    assert rec.json()["intent"] == "recommend"
    assert rec.json()["follow_ups_found"] >= 1
    assert rec.json()["cases_created"] == []


@pytest.mark.asyncio
async def test_sales_agent_permission_denied(client: AsyncClient, seeded):
    token = await login(client, "viewer@autoco.example")
    r = await client.post("/agent/sales", headers=auth(token), json={})
    assert r.status_code == 403
