import pytest
from httpx import AsyncClient

from app.ai.llm import FakeLLMClient
from app.ai.llm_planner import LLMPlanner
from app.ai.llm_planner import ToolCall as PlanToolCall
from app.integrations.telegram.resolver import EntityResolver
from tests.conftest import auth, login


@pytest.mark.asyncio
async def test_create_and_search_customer(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    headers = auth(token)

    created = await client.post(
        "/customers",
        headers=headers,
        json={
            "full_name": "حسین خریدار",
            "phone": "09121234567",
            "email": "hossein@example.com",
            "notes": "علاقه‌مند به کمری",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["full_name"] == "حسین خریدار"
    assert body["phone"] == "09121234567"

    listed = await client.get("/customers?q=حسین", headers=headers)
    assert listed.status_code == 200
    assert any(c["id"] == body["id"] for c in listed.json())

    # Link customer on a case
    case = await client.post(
        "/cases",
        headers=headers,
        json={
            "subject": "Buyer Camry interest",
            "type": "CUSTOMER_INTEREST",
            "customer_id": body["id"],
        },
    )
    assert case.status_code == 200, case.text
    assert case.json()["customer_id"] == body["id"]


@pytest.mark.asyncio
async def test_customer_permission_denied(client: AsyncClient, seeded):
    token = await login(client, "viewer@autoco.example")
    r = await client.post(
        "/customers",
        headers=auth(token),
        json={"full_name": "X"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_llm_planner_fake_client(db, seeded):
    client = FakeLLMClient(
        {
            "intent": "create_work",
            "clarification": None,
            "tools": [
                {"name": "search_inventory", "args": {"q": "Camry", "model": "Camry"}},
                {"name": "find_users", "args": {"q": "رضا"}},
                {"name": "_compose_work", "args": {}},
            ],
        }
    )
    planner = LLMPlanner(EntityResolver(db), client=client)
    intent, calls, clarification = await planner.plan(
        seeded["org"].id,
        "برای این کمری رضا پیگیری کنه",
    )
    assert clarification is None
    assert intent == "create_work"
    assert any(isinstance(c, PlanToolCall) and c.name == "search_inventory" for c in calls)
    assert any(c.name == "find_users" for c in calls)
    assert any(c.name == "_compose_work" for c in calls)
