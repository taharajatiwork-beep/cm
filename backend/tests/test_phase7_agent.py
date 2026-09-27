import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.ai_audit import AiActionLog
from tests.conftest import auth, login


@pytest.mark.asyncio
async def test_communication_agent_camry_work(client: AsyncClient, seeded, db):
    token = await login(client, "ali@autoco.example")
    vehicle = await client.post(
        "/inventory/vehicles",
        headers=auth(token),
        json={
            "vin": "JTDBR32E720012424",
            "brand": "Toyota",
            "model": "Camry",
            "year": 2020,
            "stock_number": "124",
            "branch_id": str(seeded["branch"].id),
        },
    )
    assert vehicle.status_code == 200, vehicle.text

    r = await client.post(
        "/agent/communication",
        headers=auth(token),
        json={
            "message": "برای این کمری، رضا مشتری رو پیگیری کنه و سارا تبلیغات رو انجام بده."
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["intent"] == "create_work"
    assert body["work_item_id"]
    assert len(body["task_ids"]) == 2
    assert "WorkItem created" in body["message"]
    assert "Contact customers" in body["message"]
    assert "Prepare marketing material" in body["message"]
    tools_used = {t["tool"] for t in body["tool_trace"]}
    assert "search_inventory" in tools_used
    assert "find_users" in tools_used
    assert "create_work_item" in tools_used
    assert "create_task" in tools_used

    progress = await client.get(
        f"/work-items/{body['work_item_id']}/progress",
        headers=auth(token),
    )
    assert progress.json()["total_tasks"] == 2

    logs = list(
        (await db.execute(select(AiActionLog).where(AiActionLog.request_id == body["request_id"])))
        .scalars()
        .all()
    )
    assert len(logs) >= 3


@pytest.mark.asyncio
async def test_agent_ambiguous_vehicles(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    for stock, suffix in [("124", "12424"), ("125", "12525")]:
        r = await client.post(
            "/inventory/vehicles",
            headers=auth(token),
            json={
                "vin": f"JTDBR32E7200{suffix}",
                "brand": "Toyota",
                "model": "Camry",
                "year": 2020,
                "stock_number": stock,
                "branch_id": str(seeded["branch"].id),
            },
        )
        assert r.status_code == 200, r.text

    r = await client.post(
        "/agent/communication",
        headers=auth(token),
        json={"message": "برای این کمری، رضا مشتری رو پیگیری کنه و سارا تبلیغات رو انجام بده."},
    )
    assert r.status_code == 200
    assert r.json()["intent"] == "clarify"
    assert r.json()["work_item_id"] is None
    assert "multiple" in (r.json()["clarification"] or "").lower() or "Which one" in (
        r.json()["message"] or ""
    )


@pytest.mark.asyncio
async def test_agent_permission_denied(client: AsyncClient, seeded):
    token = await login(client, "viewer@autoco.example")
    r = await client.post(
        "/agent/communication",
        headers=auth(token),
        json={"message": "hello"},
    )
    assert r.status_code == 403
