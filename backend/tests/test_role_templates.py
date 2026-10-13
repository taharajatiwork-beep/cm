"""قالب مدیر صفحهٔ پروژه و خانهٔ تیم هم‌رده را نمی‌بیند."""

from app.core.permissions import PermissionCode
from tests.conftest import auth, login


async def _user(db, seeded, email, perms, team_id, scope="team"):
    from app.services import OrgService

    svc = OrgService(db)
    role = await svc.create_role(seeded["org"].id, email, email.split("@")[0], perms, scope)
    await svc.create_user(
        organization_id=seeded["org"].id,
        email=email,
        full_name=email,
        password="password",
        role_id=role.id,
        branch_id=seeded["branch"].id,
        team_id=team_id,
        department_id=seeded["mkt_team"].department_id,
    )
    await db.commit()


async def test_requester_cannot_open_project_or_team_home(client, seeded, db):
    await _user(db, seeded, "boss@autoco.example", [PermissionCode.REQUEST_CREATE, PermissionCode.CONVERSATION_READ], seeded["sales_team"].id, "self")
    await _user(
        db,
        seeded,
        "lead@autoco.example",
        [PermissionCode.REQUEST_TRIAGE, PermissionCode.REQUEST_MANAGE],
        seeded["mkt_team"].id,
        "team_tree",
    )
    boss = auth(await login(client, "boss@autoco.example"))
    lead = auth(await login(client, "lead@autoco.example"))
    created = await client.post(
        "/requests",
        headers=boss,
        json={"title": "تبلیغات", "kind": "تبلیغات", "priority": "normal", "team_id": str(seeded["mkt_team"].id)},
    )
    assert created.status_code == 201, created.text
    project = await client.post(
        f"/requests/{created.json()['id']}/projects",
        headers=lead,
        json={"title": "پرفورمنس", "kind": "پرفورمنس", "status": "new", "team_id": str(seeded["mkt_team"].id)},
    )
    assert project.status_code == 201, project.text
    opened_project = await client.get(f"/requests/projects/{project.json()['id']}", headers=boss)
    assert opened_project.status_code == 200, opened_project.text
    assert opened_project.json()["readonly"] is True
    assert opened_project.json().get("planning_pending") is True
    lead_create = await client.post("/requests", headers=lead, json={"title": "نباید بسازد"})
    assert lead_create.status_code == 403
    home = await client.get(f"/teams/{seeded['mkt_team'].id}", headers=boss)
    assert home.status_code == 403
    opened = await client.get(f"/teams/{seeded['mkt_team'].id}", headers=lead)
    assert opened.status_code == 200, opened.text
    assert opened.json()["team"]["name"] == seeded["mkt_team"].name


async def test_member_does_not_see_sibling_team(client, seeded, db):
    from app.services import OrgService

    svc = OrgService(db)
    design = await svc.create_team(seeded["org"].id, "Design", "DESIGN_T", seeded["mkt_team"].department_id, seeded["mkt_team"].id)
    film = await svc.create_team(seeded["org"].id, "Film", "FILM_T", seeded["mkt_team"].department_id, seeded["mkt_team"].id)
    await db.commit()
    await _user(db, seeded, "designer@autoco.example", [PermissionCode.TASK_READ, PermissionCode.TASK_WRITE], design.id)
    await _user(
        db,
        seeded,
        "chief@autoco.example",
        [PermissionCode.REQUEST_TRIAGE, PermissionCode.TASK_READ],
        seeded["mkt_team"].id,
        "team_tree",
    )
    member = auth(await login(client, "designer@autoco.example"))
    chief = auth(await login(client, "chief@autoco.example"))
    hidden = await client.get(f"/teams/{film.id}", headers=member)
    assert hidden.status_code == 404
    own = await client.get(f"/teams/{design.id}", headers=member)
    assert own.status_code == 200
    parent_hub = await client.get(f"/teams/{seeded['mkt_team'].id}", headers=member)
    assert parent_hub.status_code == 200, parent_hub.text
    assert parent_hub.json()["can_edit"] is False
    parent = await client.get(f"/teams/{seeded['mkt_team'].id}", headers=chief)
    assert parent.status_code == 200
    names = {item["name"] for item in parent.json()["sections"]}
    assert "Design" in names
    assert "Film" in names


async def test_performance_cannot_see_requests_or_create_projects(client, seeded, db):
    await _user(
        db,
        seeded,
        "perf-role@autoco.example",
        [PermissionCode.TASK_READ, PermissionCode.PERF_READ, PermissionCode.PERF_WRITE, PermissionCode.CAMPAIGN_READ],
        seeded["mkt_team"].id,
    )
    await _user(db, seeded, "boss-role@autoco.example", [PermissionCode.REQUEST_CREATE], seeded["sales_team"].id, "self")
    perf = auth(await login(client, "perf-role@autoco.example"))
    boss = auth(await login(client, "boss-role@autoco.example"))
    hidden = await client.get("/requests", headers=perf)
    assert hidden.status_code == 403
    created = await client.post("/requests", headers=boss, json={"title": "فقط برای سرپرست"})
    assert created.status_code == 201, created.text
    denied = await client.post(
        f"/requests/{created.json()['id']}/projects",
        headers=perf,
        json={"title": "نباید ساخته شود"},
    )
    assert denied.status_code == 403
    home = await client.get(f"/teams/{seeded['mkt_team'].id}", headers=perf)
    assert home.status_code == 200, home.text
    assert home.json()["requests"] == []
    assert home.json()["can_edit"] is False
