import pytest
from httpx import AsyncClient

from tests.conftest import auth, login


@pytest.mark.asyncio
async def test_recommend_by_role_team_and_workload(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")

    # Give Reza sales skill; create a task so Sara has less/more workload asymmetry
    skill = await client.post(
        f"/assignment/users/{seeded['reza'].id}/skills",
        headers=auth(token),
        json={"skill_code": "sales", "level": 3},
    )
    assert skill.status_code == 200, skill.text

    await client.post(
        f"/assignment/users/{seeded['sara'].id}/skills",
        headers=auth(token),
        json={"skill_code": "marketing", "level": 2},
    )

    # Load Reza with an open task
    wi = await client.post(
        "/work-items",
        headers=auth(token),
        json={"title": "Busy work"},
    )
    await client.post(
        "/tasks",
        headers=auth(token),
        json={
            "title": "Heavy task",
            "work_item_id": wi.json()["id"],
            "assignee_ids": [str(seeded["reza"].id)],
        },
    )

    # Recommend seller on sales team with sales skill — Reza is only match but higher workload
    rec = await client.post(
        "/assignment/recommend",
        headers=auth(token),
        json={
            "role_code": "seller",
            "team_id": str(seeded["sales_team"].id),
            "required_skills": ["sales"],
            "limit": 5,
        },
    )
    assert rec.status_code == 200, rec.text
    body = rec.json()
    assert body["recommended_user_id"] == str(seeded["reza"].id)
    assert body["auto_assign_allowed"] is False  # business rule default
    assert body["candidates"][0]["open_tasks"] >= 1
    assert "sales" in body["candidates"][0]["skills"]

    # Marketing team recommendation
    mkt = await client.post(
        "/assignment/recommend",
        headers=auth(token),
        json={
            "role_code": "marketing",
            "team_id": str(seeded["mkt_team"].id),
            "required_skills": ["marketing"],
        },
    )
    assert mkt.status_code == 200
    assert mkt.json()["recommended_user_id"] == str(seeded["sara"].id)


@pytest.mark.asyncio
async def test_apply_requires_explicit_user_when_auto_disabled(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    wi = await client.post("/work-items", headers=auth(token), json={"title": "Assign me"})
    task = await client.post(
        "/tasks",
        headers=auth(token),
        json={"title": "Open", "work_item_id": wi.json()["id"]},
    )
    tid = task.json()["id"]

    blocked = await client.post(
        "/assignment/apply",
        headers=auth(token),
        json={"task_id": tid, "role_code": "seller"},
    )
    assert blocked.status_code == 400

    ok = await client.post(
        "/assignment/apply",
        headers=auth(token),
        json={"task_id": tid, "user_id": str(seeded["reza"].id)},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["assigned_user_id"] == str(seeded["reza"].id)


@pytest.mark.asyncio
async def test_branch_filter_and_permission(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    rec = await client.post(
        "/assignment/recommend",
        headers=auth(token),
        json={"branch_id": str(seeded["branch"].id)},
    )
    assert rec.status_code == 200
    assert len(rec.json()["candidates"]) >= 1

    viewer = await login(client, "viewer@autoco.example")
    denied = await client.post(
        "/assignment/recommend",
        headers=auth(viewer),
        json={},
    )
    assert denied.status_code == 403
