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
async def test_calendar_timed_event_recurrence_and_bulk(client: AsyncClient, seeded, db):
    token = await _admin(client, seeded, db)
    headers = auth(token)
    event = await client.post(
        "/calendar/entries",
        headers=headers,
        json={
            "on_date": "2026-10-20",
            "entry_type": "event",
            "title": "جلسه هفتگی",
            "all_day": False,
            "start_time": "09:00",
            "end_time": "10:00",
            "recurrence": "weekly",
            "recur_until": "2026-11-03",
            "attendee_ids": [str(seeded["reza"].id)],
        },
    )
    assert event.status_code == 201, event.text
    parent_id = event.json()["entry_id"]
    listed = await client.get("/calendar?from=2026-10-20&to=2026-11-03&year=1405&month=8", headers=headers)
    assert listed.status_code == 200
    titles = [row["title"] for row in listed.json()["entries"] if row["entry_type"] == "event"]
    assert titles.count("جلسه هفتگی") >= 2

    patched = await client.patch(
        f"/calendar/entries/{parent_id}",
        headers=headers,
        json={"scope": "this", "occurrence_date": "2026-10-27", "title": "جلسه منتقل"},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "جلسه منتقل"

    bulk = await client.post(
        "/calendar/entries/bulk",
        headers=headers,
        json={
            "entries": [
                {
                    "on_date": "2026-10-21",
                    "topic": "پست A",
                    "tier": "long",
                    "format": "Post",
                    "channel": "IG",
                    "status": "todo",
                },
                {
                    "on_date": "2026-10-21",
                    "topic": "پست B",
                    "tier": "short",
                    "format": "Story",
                    "channel": "IG",
                    "status": "todo",
                },
            ]
        },
    )
    assert bulk.status_code == 201
    assert bulk.json()["added"] == 2


@pytest.mark.asyncio
async def test_calendar_occasions_and_mizito_layer(client: AsyncClient, seeded, db):
    from datetime import UTC, datetime

    from app.requests.models import WorkProject

    token = await _admin(client, seeded, db)
    headers = auth(token)
    db.add(
        WorkProject(
            organization_id=seeded["org"].id,
            code="MZ-1",
            title="میزیتو تست",
            team_id=seeded["mkt_team"].id,
            status="new",
            mizito_deadline=datetime(2026, 10, 25, 12, 0, tzinfo=UTC),
        )
    )
    await db.commit()

    range_body = await client.get("/calendar?from=2026-10-20&to=2026-10-30&year=1405&month=8", headers=headers)
    assert range_body.status_code == 200
    body = range_body.json()
    assert any(row.get("kind") == "mizito" for row in body["events"])
    assert any(row.get("is_off") for row in body.get("occasions", []))

    denied = await client.post(
        "/calendar/occasions",
        headers=auth(await login(client, "reza@autoco.example")),
        json={"on_date": "2026-12-01", "title": "رویداد فروش", "kind": "marketing"},
    )
    assert denied.status_code == 403

    created = await client.post(
        "/calendar/occasions",
        headers=headers,
        json={"on_date": "2026-12-01", "title": "رویداد فروش", "kind": "marketing"},
    )
    assert created.status_code == 201
    occ_id = created.json()["id"]
    removed = await client.delete(f"/calendar/occasions/{occ_id}", headers=headers)
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
