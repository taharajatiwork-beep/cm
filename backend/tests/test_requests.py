"""ماژول درخواست‌ها: مستقل از پرفورمنس، مدیر → تیم."""

from app.core.permissions import PermissionCode
from tests.conftest import auth, login


async def _request_user(db, seeded, email: str, name: str, permissions: list[str]) -> None:
    from app.services import OrgService

    svc = OrgService(db)
    role = await svc.create_role(seeded["org"].id, name, f"{email.split('@')[0]}_role", permissions, "organization")
    await svc.create_user(
        organization_id=seeded["org"].id,
        email=email,
        full_name=name,
        password="password",
        role_id=role.id,
        branch_id=seeded["branch"].id,
    )
    await db.commit()


async def test_request_flow_manager_creates_and_triage_updates(client, seeded, db):
    await _request_user(db, seeded, "manager-test@autoco.example", "مدیر تست", [PermissionCode.REQUEST_CREATE])
    await _request_user(db, seeded, "triage-test@autoco.example", "ترییج تست", [PermissionCode.REQUEST_TRIAGE])
    manager = auth(await login(client, "manager-test@autoco.example"))
    triage = auth(await login(client, "triage-test@autoco.example"))

    created = await client.post(
        "/requests",
        headers=manager,
        json={"title": "کمپین فروش بهمن", "description": "برای شعبه نور", "kind": "تبلیغات", "priority": "high", "team_id": str(seeded["mkt_team"].id)},
    )
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["code"].startswith("REQ-")
    assert row["status"] == "new"
    assert row["team_name"] == seeded["mkt_team"].name
    request_id = row["id"]

    # مدیر فقط درخواست‌های خودش را می‌بیند و نمی‌تواند وضعیت عوض کند
    mine = await client.get("/requests", headers=manager)
    assert mine.status_code == 200
    assert [item["id"] for item in mine.json()] == [request_id]
    forbidden = await client.patch(f"/requests/{request_id}", headers=manager, json={"status": "done"})
    assert forbidden.status_code == 403

    # ترییج همه را می‌بیند، وضعیت و تیم را عوض می‌کند
    queue = await client.get("/requests", headers=triage)
    assert queue.status_code == 200
    assert request_id in [item["id"] for item in queue.json()]
    patched = await client.patch(
        f"/requests/{request_id}",
        headers=triage,
        json={"status": "converted", "team_id": str(seeded["mkt_team"].id)},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["status"] == "converted"

    # فیلتر وضعیت
    filtered = await client.get("/requests?status=converted", headers=triage)
    assert [item["id"] for item in filtered.json()] == [request_id]

    # سرپرست حذف نمی‌کند؛ صاحب درخواست تا وقتی جدید است حذف می‌کند
    second = await client.post("/requests", headers=manager, json={"title": "درخواست دوم"})
    assert second.status_code == 201
    denied_delete = await client.delete(f"/requests/{second.json()['id']}", headers=triage)
    assert denied_delete.status_code == 403
    deleted = await client.delete(f"/requests/{second.json()['id']}", headers=manager)
    assert deleted.status_code == 204

    # کد پشت‌سرهم
    third = await client.post("/requests", headers=manager, json={"title": "درخواست سوم"})
    assert third.json()["code"] != row["code"]


async def test_triage_converts_request_into_projects(client, seeded, db):
    await _request_user(db, seeded, "manager-p@autoco.example", "مدیر پروژه", [PermissionCode.REQUEST_CREATE])
    await _request_user(db, seeded, "triage-p@autoco.example", "ترییج پروژه", [PermissionCode.REQUEST_TRIAGE])
    manager = auth(await login(client, "manager-p@autoco.example"))
    triage = auth(await login(client, "triage-p@autoco.example"))

    created = await client.post(
        "/requests", headers=manager,
        json={"title": "کمپین بهمن", "kind": "قیمت و پست‌ها", "team_id": str(seeded["mkt_team"].id)},
    )
    request_id = created.json()["id"]

    # تیم ترییج دو پروژه می‌سازد؛ وضعیت درخواست خودکار «تبدیل به پروژه» می‌شود
    first = await client.post(
        f"/requests/{request_id}/projects", headers=triage,
        json={"title": "کمپین پرفورمنس بهمن", "kind": "پرفورمنس", "team_id": str(seeded["mkt_team"].id)},
    )
    assert first.status_code == 201, first.text
    assert first.json()["code"].startswith("PRJ-")
    second = await client.post(
        f"/requests/{request_id}/projects", headers=triage,
        json={"title": "طراحی بنر بهمن", "kind": "طراحی"},
    )
    assert second.status_code == 201
    shown = await client.get("/requests", headers=manager)
    assert shown.json()[0]["status"] == "converted"

    # مدیر پروژه‌های درخواستش را می‌بیند ولی نمی‌تواند پروژه بسازد
    mine = await client.get(f"/requests/projects?request_id={request_id}", headers=manager)
    assert mine.status_code == 200
    assert len(mine.json()) == 2
    forbidden = await client.post(
        f"/requests/{request_id}/projects", headers=manager, json={"title": "پروژه تقلبی"}
    )
    assert forbidden.status_code in (401, 403)

    # تغییر وضعیت پروژه و حذف
    patched = await client.patch(
        f"/requests/projects/{first.json()['id']}", headers=triage, json={"status": "in_progress"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["status"] == "in_progress"

    from app.models import User
    from app.perf.models import PmCampaign
    from sqlalchemy import select

    people = list(
        (await db.scalars(select(User).where(User.email.in_(["manager-p@autoco.example", "triage-p@autoco.example"])))).all()
    )
    saved = await client.put(
        f"/requests/projects/{first.json()['id']}/members",
        headers=triage,
        json={"user_ids": [str(person.id) for person in people]},
    )
    assert saved.status_code == 200, saved.text
    assert len(saved.json()) == 2
    one = PmCampaign(organization_id=seeded["org"].id, code="S-MANY-1", title="کمپین اول")
    two = PmCampaign(organization_id=seeded["org"].id, code="S-MANY-2", title="کمپین دوم")
    db.add_all([one, two])
    await db.commit()
    linked = await client.put(
        f"/requests/projects/{first.json()['id']}/campaigns",
        headers=triage,
        json={"campaign_ids": [str(one.id), str(two.id)]},
    )
    assert linked.status_code == 200, linked.text
    assert {item["code"] for item in linked.json()} == {"S-MANY-1", "S-MANY-2"}
    deleted = await client.delete(f"/requests/projects/{second.json()['id']}", headers=triage)
    assert deleted.status_code == 204
    left = await client.get(f"/requests/projects?request_id={request_id}", headers=manager)
    assert len(left.json()) == 1


async def test_user_without_request_permission_cannot_see(client, seeded):
    token = await login(client, "reza@autoco.example")
    response = await client.get("/requests", headers=auth(token))
    assert response.status_code in (401, 403)


async def test_member_sees_only_projects_they_belong_to(client, seeded, db):
    from sqlalchemy import select

    from app.models import User

    await _request_user(db, seeded, "boss-m@autoco.example", "مدیر عضو", [PermissionCode.REQUEST_CREATE])
    await _request_user(db, seeded, "lead-m@autoco.example", "سرپرست عضو", [PermissionCode.REQUEST_TRIAGE])
    await _request_user(db, seeded, "member-m@autoco.example", "عضو تست", [PermissionCode.TASK_READ])
    boss = auth(await login(client, "boss-m@autoco.example"))
    lead = auth(await login(client, "lead-m@autoco.example"))
    member = auth(await login(client, "member-m@autoco.example"))
    user = await db.scalar(select(User).where(User.email == "member-m@autoco.example"))
    created = await client.post("/requests", headers=boss, json={"title": "برای عضو"})
    first = await client.post(f"/requests/{created.json()['id']}/projects", headers=lead, json={"title": "پروژه عضو"})
    second = await client.post("/requests/projects", headers=lead, json={"title": "پروژه دیگران"})
    assert first.status_code == 201 and second.status_code == 201
    saved = await client.put(
        f"/requests/projects/{first.json()['id']}/members",
        headers=lead,
        json={"user_ids": [str(user.id)]},
    )
    assert saved.status_code == 200, saved.text
    listed = await client.get("/requests/projects", headers=member)
    assert listed.status_code == 200, listed.text
    ids = [item["id"] for item in listed.json()]
    assert first.json()["id"] in ids
    assert second.json()["id"] not in ids
    forbidden_project = await client.get(f"/requests/projects/{second.json()['id']}", headers=member)
    assert forbidden_project.status_code == 403, forbidden_project.text
    text_edit = await client.patch(f"/requests/{created.json()['id']}", headers=lead, json={"title": "عوض نشود"})
    assert text_edit.status_code == 403


async def test_ticking_tasks_advances_project_and_request(client, seeded, db):
    await _request_user(db, seeded, "boss-tick@autoco.example", "مدیر تیک", [PermissionCode.REQUEST_CREATE])
    await _request_user(
        db,
        seeded,
        "lead-tick@autoco.example",
        "سرپرست تیک",
        [PermissionCode.REQUEST_TRIAGE, PermissionCode.TASK_WRITE, PermissionCode.TASK_READ],
    )
    boss = auth(await login(client, "boss-tick@autoco.example"))
    lead = auth(await login(client, "lead-tick@autoco.example"))
    created = await client.post("/requests", headers=boss, json={"title": "کمپین تیک"})
    request_id = created.json()["id"]
    first = await client.post(f"/requests/{request_id}/projects", headers=lead, json={"title": "پروژه اول"})
    second = await client.post(f"/requests/{request_id}/projects", headers=lead, json={"title": "پروژه دوم"})
    assert first.status_code == 201 and second.status_code == 201
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    async def add(project_id: str, title: str) -> str:
        made = await client.post(f"/requests/projects/{project_id}/tasks", headers=lead, json={"title": title})
        assert made.status_code == 201, made.text
        return made.json()["id"]

    one = await add(first_id, "قدم اول")
    two = await add(first_id, "قدم دوم")
    three = await add(second_id, "قدم سوم")

    started = await client.post(f"/tasks/{one}/complete", headers=lead)
    assert started.status_code == 200, started.text
    detail = await client.get(f"/requests/projects/{first_id}", headers=lead)
    assert detail.json()["status"] == "in_progress"
    assert detail.json()["progress"]["done"] == 1
    mine = await client.get("/requests/my-work", headers=lead)
    open_ids = [row["id"] for key in ("overdue", "today", "later", "waiting") for row in mine.json()[key]]
    assert one not in open_ids
    assert two in open_ids

    finished_first = await client.post(f"/tasks/{two}/complete", headers=lead)
    assert finished_first.status_code == 200
    detail = await client.get(f"/requests/projects/{first_id}", headers=lead)
    assert detail.json()["status"] == "done"
    still = await client.get("/requests", headers=lead)
    assert next(row["status"] for row in still.json() if row["id"] == request_id) == "converted"

    finished_second = await client.post(f"/tasks/{three}/complete", headers=lead)
    assert finished_second.status_code == 200
    closed = await client.get("/requests", headers=lead)
    assert next(row["status"] for row in closed.json() if row["id"] == request_id) == "done"
    gone = await client.get("/requests/my-work", headers=lead)
    left = [row["id"] for key in ("overdue", "today", "later", "waiting") for row in gone.json()[key]]
    assert three not in left


async def test_only_the_assignee_can_tick(client, seeded, db):
    await _request_user(
        db,
        seeded,
        "lead-own@autoco.example",
        "سرپرست تیک",
        [PermissionCode.REQUEST_TRIAGE, PermissionCode.TASK_WRITE, PermissionCode.TASK_READ],
    )
    await _request_user(db, seeded, "maker-own@autoco.example", "طراح تیک", [PermissionCode.TASK_READ])
    lead = auth(await login(client, "lead-own@autoco.example"))
    maker = auth(await login(client, "maker-own@autoco.example"))
    from sqlalchemy import select

    from app.models import User

    maker_user = await db.scalar(select(User).where(User.email == "maker-own@autoco.example"))
    project = await client.post("/requests/projects", headers=lead, json={"title": "پروژه نقش"})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    made = await client.post(
        f"/requests/projects/{project_id}/tasks",
        headers=lead,
        json={"title": "طرح بنر", "assignee_ids": [str(maker_user.id)]},
    )
    assert made.status_code == 201, made.text
    task_id = made.json()["id"]

    denied = await client.post(f"/tasks/{task_id}/complete", headers=lead)
    assert denied.status_code == 403

    done = await client.post(f"/tasks/{task_id}/complete", headers=maker)
    assert done.status_code == 200, done.text
    detail = await client.get(f"/requests/projects/{project_id}", headers=lead)
    assert detail.json()["tasks"][0]["assignee_ids"] == [str(maker_user.id)]
    assert detail.json()["status"] == "done"

    assignee_get = await client.get(f"/tasks/{task_id}", headers=maker)
    assert assignee_get.status_code == 200, assignee_get.text
    assert assignee_get.json()["assignees"][0]["id"] == str(maker_user.id)

    lead_get = await client.get(f"/tasks/{task_id}", headers=lead)
    assert lead_get.status_code == 200, lead_get.text
    assert lead_get.json()["id"] == task_id

    note = await client.post(
        f"/tasks/{task_id}/notes",
        headers=maker,
        json={"kind": "comment", "body": "آماده است"},
    )
    assert note.status_code == 201, note.text
    listed = await client.get(f"/tasks/{task_id}/notes", headers=maker)
    assert listed.status_code == 200
    assert any(row["body"] == "آماده است" for row in listed.json())


async def test_seller_inquiry_without_customer_admin(client, seeded, db):
    from sqlalchemy import select

    from app.models import User
    from app.models.customer import Customer
    from app.models.inventory import Vehicle

    seller = auth(await login(client, "reza@autoco.example"))
    vehicle = await db.scalar(select(Vehicle).where(Vehicle.organization_id == seeded.organization_id))
    assert vehicle is not None
    created = await client.post(
        "/cases/inquiry",
        headers=seller,
        json={
            "vehicle_id": str(vehicle.id),
            "full_name": "خریدار تست",
            "phone": "09120001122",
            "note": "تماس بگیرید",
        },
    )
    assert created.status_code == 201, created.text
    customer = await db.scalar(
        select(Customer).where(Customer.organization_id == seeded.organization_id, Customer.phone == "09120001122")
    )
    assert customer is not None
    denied = await client.get("/customers", headers=seller)
    assert denied.status_code == 403


async def test_static_request_paths_not_captured_as_uuid(client, seeded, db):
    """Regression: GET /{request_id} must not shadow /my-work, /projects, /team-load."""
    await _request_user(db, seeded, "route-mgr@autoco.example", "مدیر مسیر", [PermissionCode.REQUEST_CREATE])
    await _request_user(db, seeded, "route-lead@autoco.example", "سرپرست مسیر", [PermissionCode.REQUEST_TRIAGE, PermissionCode.TASK_READ])
    manager = auth(await login(client, "route-mgr@autoco.example"))
    lead = auth(await login(client, "route-lead@autoco.example"))

    created = await client.post("/requests", headers=manager, json={"title": "تست مسیر"})
    assert created.status_code == 201
    request_id = created.json()["id"]

    for path in ("/requests/my-work", "/requests/projects", "/requests/team-load"):
        res = await client.get(path, headers=lead)
        assert res.status_code != 422, f"{path} returned 422: {res.text}"

    one = await client.get(f"/requests/{request_id}", headers=manager)
    assert one.status_code == 200, one.text
    assert one.json()["request"]["id"] == request_id