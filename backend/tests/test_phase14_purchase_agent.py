from datetime import datetime, timedelta, timezone
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
    case.created_at = datetime.now(timezone.utc) - timedelta(days=days)
    await db.commit()


@pytest.mark.asyncio
async def test_purchase_agent_unmet_demand(client: AsyncClient, seeded, db):
    token = await login(client, "ali@autoco.example")
    headers = auth(token)

    buyer = await client.post(
        "/cases",
        headers=headers,
        json={"subject": "مشتری پرادو می‌خواد", "type": "BUYER_REQUEST", "priority": "HIGH"},
    )
    assert buyer.status_code == 200, buyer.text

    r = await client.post(
        "/agent/purchase",
        headers=headers,
        json={"auto_create": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["intent"] == "create_opportunities"
    assert body["opportunities_found"] >= 1
    assert len(body["cases_created"]) >= 1
    assert "Prado" in body["message"]
    tools = {t["tool"] for t in body["tool_trace"]}
    assert "detect_purchase_opportunities" in tools
    assert "create_purchase_opportunity" in tools

    created = await db.get(CommunicationCase, UUID(body["cases_created"][0]))
    assert created is not None
    assert "Purchase opportunity: Toyota Prado" in created.subject

    r2 = await client.post(
        "/agent/purchase",
        headers=headers,
        json={"auto_create": True},
    )
    assert r2.status_code == 200
    assert r2.json()["opportunities_found"] == 0


@pytest.mark.asyncio
async def test_purchase_agent_stale_seller_offer(client: AsyncClient, seeded, db):
    token = await login(client, "ali@autoco.example")
    headers = auth(token)

    seller = await client.post(
        "/cases",
        headers=headers,
        json={
            "subject": "فروشنده آکورد ۲۰۱۸ پیشنهاد داده",
            "type": "SELLER_REQUEST",
            "priority": "MEDIUM",
        },
    )
    assert seller.status_code == 200, seller.text
    await _age_case(db, seller.json()["id"], days=5)

    r = await client.post(
        "/agent/purchase",
        headers=headers,
        json={"stale_days": 3, "auto_create": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["opportunities_found"] >= 1
    assert len(body["task_ids"]) >= 1

    follow = await db.get(CommunicationCase, UUID(body["cases_created"][0]))
    assert follow is not None
    assert follow.type in (CaseType.FOLLOW_UP, CaseType.GENERAL_OPERATIONAL_REQUEST)

    logs = list(
        (
            await db.execute(
                select(AiActionLog).where(AiActionLog.request_id == body["request_id"])
            )
        )
        .scalars()
        .all()
    )
    assert any(log.agent == "PurchaseAgent" for log in logs)


@pytest.mark.asyncio
async def test_purchase_agent_pipeline_and_recommend(client: AsyncClient, seeded, db):
    token = await login(client, "ali@autoco.example")
    headers = auth(token)

    await client.post(
        "/cases",
        headers=headers,
        json={"subject": "Seller Civic offer", "type": "SELLER_REQUEST"},
    )

    pipe = await client.post(
        "/agent/purchase",
        headers=headers,
        json={"message": "list pipeline"},
    )
    assert pipe.status_code == 200
    assert pipe.json()["intent"] == "pipeline"

    await client.post(
        "/cases",
        headers=headers,
        json={"subject": "نیاز به سیویک", "type": "CUSTOMER_INTEREST"},
    )
    rec = await client.post(
        "/agent/purchase",
        headers=headers,
        json={"message": "scan only", "auto_create": False},
    )
    assert rec.status_code == 200
    assert rec.json()["intent"] == "recommend"
    assert rec.json()["opportunities_found"] >= 1
    assert rec.json()["cases_created"] == []


@pytest.mark.asyncio
async def test_purchase_agent_permission_denied(client: AsyncClient, seeded):
    token = await login(client, "viewer@autoco.example")
    r = await client.post("/agent/purchase", headers=auth(token), json={})
    assert r.status_code == 403
