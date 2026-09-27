"""Collaboration core — list APIs, multi-participant, team assign, workload."""

import pytest
from httpx import AsyncClient

from app.models.enums import AssignmentTargetType, TaskRole
from tests.conftest import auth, login


@pytest.mark.asyncio
async def test_org_structure_list_apis(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    h = auth(token)

    people = await client.get("/people", headers=h)
    assert people.status_code == 200, people.text
    emails = {p["email"] for p in people.json()}
    assert "reza@autoco.example" in emails
    assert "sara@autoco.example" in emails

    teams = await client.get("/teams", headers=h)
    assert teams.status_code == 200
    assert any(t["code"] == "MKT_T" for t in teams.json())

    depts = await client.get("/departments", headers=h)
    assert any(d["code"] == "SALES" for d in depts.json())

    branches = await client.get("/branches", headers=h)
    assert any(b["code"] == "THR" for b in branches.json())

    rels = await client.get("/relationships", headers=h)
    assert rels.status_code == 200
    assert len(rels.json()) >= 2

    reports = await client.get(f"/people/{seeded['ali'].id}/reports", headers=h)
    assert any(u["email"] == "reza@autoco.example" for u in reports.json())


@pytest.mark.asyncio
async def test_work_item_list_participants_and_team_task(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    h = auth(token)

    wi = await client.post(
        "/work-items",
        headers=h,
        json={
            "title": "Sell Camry collaboration hub",
            "participant_ids": [str(seeded["reza"].id)],
        },
    )
    assert wi.status_code == 200
    wid = wi.json()["id"]

    add = await client.post(
        f"/work-items/{wid}/participants",
        headers=h,
        json={"user_id": str(seeded["sara"].id)},
    )
    assert add.status_code == 200

    listed = await client.get("/work-items", headers=h)
    assert any(x["id"] == wid for x in listed.json())

    t_user = await client.post(
        "/tasks",
        headers=h,
        json={
            "title": "Reza follow-up",
            "work_item_id": wid,
            "assignee_ids": [str(seeded["reza"].id)],
        },
    )
    assert t_user.status_code == 200

    t_team = await client.post(
        "/tasks",
        headers=h,
        json={
            "title": "Marketing listing",
            "work_item_id": wid,
            "assignment_target_type": AssignmentTargetType.TEAM.value,
            "assignment_target_id": str(seeded["mkt_team"].id),
            "assignee_ids": [str(seeded["sara"].id)],
        },
    )
    assert t_team.status_code == 200
    assert t_team.json()["assignment_target_type"] == AssignmentTargetType.TEAM.value

    part = await client.post(
        f"/tasks/{t_user.json()['id']}/participants",
        headers=h,
        json={"user_id": str(seeded["sara"].id), "role": TaskRole.FOLLOWER.value},
    )
    assert part.status_code == 200

    progress = await client.get(f"/work-items/{wid}/progress", headers=h)
    body = progress.json()
    assert body["total_tasks"] == 2
    assert len(body["participants"]) >= 2
    assert any(t["assignment_target_type"] == "TEAM" for t in body["tasks"])

    tasks = await client.get(f"/tasks?work_item_id={wid}", headers=h)
    assert len(tasks.json()) == 2

    workload = await client.get(f"/users/{seeded['reza'].id}/workload", headers=h)
    assert workload.status_code == 200
    assert workload.json()["open_tasks"] >= 1


@pytest.mark.asyncio
async def test_seller_can_list_people_via_work_item_read(client: AsyncClient, seeded):
    token = await login(client, "reza@autoco.example")
    r = await client.get("/people", headers=auth(token))
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_conversation_list_linked_to_work_item(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    h = auth(token)
    wi = await client.post("/work-items", headers=h, json={"title": "Linked chat"})
    wid = wi.json()["id"]
    conv = await client.post(
        "/conversations",
        headers=h,
        json={
            "topic": "About this work",
            "participant_ids": [str(seeded["ali"].id), str(seeded["reza"].id)],
            "work_item_id": wid,
            "channel": "WEB",
        },
    )
    assert conv.status_code == 200
    listed = await client.get(f"/conversations?work_item_id={wid}", headers=h)
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == conv.json()["id"]


@pytest.mark.asyncio
async def test_assign_endpoint_and_task_timeline(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    h = auth(token)
    wi = await client.post("/work-items", headers=h, json={"title": "Assign path"})
    task = await client.post(
        "/tasks",
        headers=h,
        json={"title": "Needs owner", "work_item_id": wi.json()["id"]},
    )
    tid = task.json()["id"]
    assigned = await client.post(
        f"/tasks/{tid}/assign",
        headers=h,
        json={
            "to_user_id": str(seeded["reza"].id),
            "to_target_type": AssignmentTargetType.TEAM.value,
            "to_target_id": str(seeded["sales_team"].id),
        },
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["assignment_target_type"] == "TEAM"

    tl = await client.get(f"/tasks/{tid}/timeline", headers=h)
    assert tl.status_code == 200
    types = {e["event_type"] for e in tl.json()}
    assert "task.created" in types or "task.reassigned" in types
