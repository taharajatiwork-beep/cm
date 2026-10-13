import pytest
from datetime import UTC, datetime
from httpx import AsyncClient

from app.models import Priority, Task, TaskStatus
from tests.conftest import auth, login


async def _admin(client, seeded, db) -> str:
    from app.services import OrgService

    await OrgService(db).create_user(
        organization_id=seeded["org"].id,
        email="site-admin@autoco.example",
        full_name="Site Admin",
        password="password",
        role_id=seeded["admin_role"].id,
        branch_id=seeded["branch"].id,
    )
    await db.commit()
    return await login(client, "site-admin@autoco.example")


@pytest.mark.asyncio
async def test_calendar_denied_for_plain_seller(client: AsyncClient, seeded):
    reza = await login(client, "reza@autoco.example")
    denied = await client.get("/calendar?from=2026-10-23&to=2026-11-21&year=1405&month=8", headers=auth(reza))
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_calendar_open_for_triage(client: AsyncClient, seeded, db):
    from app.core.permissions import PermissionCode
    from app.services import OrgService

    svc = OrgService(db)
    role = await svc.create_role(
        seeded["org"].id,
        "Mkt lead",
        "mkt_lead_cal",
        [PermissionCode.REQUEST_TRIAGE, PermissionCode.PERF_WRITE, PermissionCode.NOTIFICATION_READ],
        "team_tree",
    )
    user = await svc.create_user(
        organization_id=seeded["org"].id,
        email="cal-mgr@autoco.example",
        full_name="Cal Mgr",
        password="password",
        role_id=role.id,
        branch_id=seeded["branch"].id,
        team_id=seeded["mkt_team"].id,
    )
    await db.commit()
    token = await login(client, user.email)
    ok = await client.get(
        "/calendar?from=2026-10-23&to=2026-11-21&year=1405&month=8",
        headers=auth(token),
    )
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_calendar_crud_and_events(client: AsyncClient, seeded, db):
    token = await _admin(client, seeded, db)
    headers = auth(token)
    db.add(
        Task(
            organization_id=seeded["org"].id,
            title="مهلت تقویم",
            owner_id=seeded["reza"].id,
            status=TaskStatus.OPEN,
            priority=Priority.MEDIUM,
            deadline=datetime(2026, 10, 23, 9, 0, tzinfo=UTC),
        )
    )
    await db.commit()

    created = await client.post(
        "/calendar/entries",
        headers=headers,
        json={
            "on_date": "2026-10-23",
            "tier": "long",
            "format": "Reel",
            "channel": "Instagram",
            "topic": "معرفی شعبه",
            "cta": "تماس",
            "kpi": "Reach",
            "status": "todo",
        },
    )
    assert created.status_code == 201, created.text
    entry_id = created.json()["id"]

    listed = await client.get("/calendar?from=2026-10-23&to=2026-10-23&year=1405&month=8", headers=headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert any(row["topic"] == "معرفی شعبه" for row in body["entries"])
    assert any(row["kind"] == "task" and row["title"] == "مهلت تقویم" for row in body["events"])
    outside = await client.get("/calendar?from=2026-10-01&to=2026-10-02", headers=headers)
    assert outside.json()["entries"] == []
    assert all(row["title"] != "مهلت تقویم" for row in outside.json()["events"])

    patched = await client.patch(f"/calendar/entries/{entry_id}", headers=headers, json={"status": "done"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "done"

    month = await client.put(
        "/calendar/month/1405/8",
        headers=headers,
        json={"title": "آبان", "goal": "لید", "logic": ["حرکت از آگاهی به لید"], "weeks": [], "mix": [], "kpis": [], "rules": []},
    )
    assert month.status_code == 200, month.text
    again = await client.get("/calendar?from=2026-10-23&to=2026-10-23&year=1405&month=8", headers=headers)
    assert again.json()["month"]["goal"] == "لید"

    draft = await client.post("/calendar/month/1405/8/draft", headers=headers)
    assert draft.status_code == 200, draft.text
    assert draft.json()["source"] == "template"
    assert len(draft.json()["entries"]) == 30

    removed = await client.delete(f"/calendar/entries/{entry_id}", headers=headers)
    assert removed.status_code == 204


@pytest.mark.asyncio
async def test_aban_seed_is_idempotent(seeded, db):
    from app.calendar.seed import seed_content_calendar

    first = await seed_content_calendar(db, seeded["org"].id, seeded["ali"].id)
    await db.commit()
    assert first == {"entries": 30, "skipped": False}
    second = await seed_content_calendar(db, seeded["org"].id, seeded["ali"].id)
    assert second["skipped"] is True
    assert second["entries"] == 0
