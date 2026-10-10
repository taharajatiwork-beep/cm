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

    # حذف توسط ترییج
    second = await client.post("/requests", headers=manager, json={"title": "درخواست دوم"})
    assert second.status_code == 201
    deleted = await client.delete(f"/requests/{second.json()['id']}", headers=triage)
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