import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import PermissionCode, ROLE_TEMPLATES
from app.models import Event
from app.models.enums import (
    AssignmentTargetType,
    CaseType,
    Channel,
    Priority,
    SlaState,
    TaskStatus,
)
from app.services import OrgService, SlaService, WorkService
from tests.conftest import auth, login


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_bootstrap_and_me(client: AsyncClient):
    r = await client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "BootCo",
            "organization_slug": "bootco",
            "admin_email": "admin@bootco.example",
            "admin_name": "Admin",
            "admin_password": "secret12",
        },
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = await client.get("/auth/me", headers=auth(token))
    assert me.status_code == 200
    body = me.json()
    assert "org.admin" in body["permissions"]
    assert body["role_code"] == "admin"


@pytest.mark.asyncio
async def test_relationships_and_eligible(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    managers = await client.get(
        f"/org/users/{seeded['reza'].id}/managers", headers=auth(token)
    )
    assert managers.status_code == 200
    assert any(u["full_name"] == "Ali Manager" for u in managers.json())

    members = await client.get(
        f"/org/teams/{seeded['sales_team'].id}/members", headers=auth(token)
    )
    assert any(u["email"] == "reza@autoco.example" for u in members.json())

    eligible = await client.get(
        f"/org/eligible-assignees?team_id={seeded['mkt_team'].id}",
        headers=auth(token),
    )
    assert any(u["email"] == "sara@autoco.example" for u in eligible.json())


@pytest.mark.asyncio
async def test_permission_denial(client: AsyncClient, seeded):
    token = await login(client, "viewer@autoco.example")
    r = await client.post(
        "/work-items",
        headers=auth(token),
        json={"title": "Should fail"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_conversation_messages(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    conv = await client.post(
        "/conversations",
        headers=auth(token),
        json={
            "channel": Channel.WEB.value,
            "topic": "Camry discussion",
            "participant_ids": [str(seeded["ali"].id), str(seeded["reza"].id)],
        },
    )
    assert conv.status_code == 200
    cid = conv.json()["id"]
    msg = await client.post(
        f"/conversations/{cid}/messages",
        headers=auth(token),
        json={"text": "Please follow up with customers", "channel": "WEB"},
    )
    assert msg.status_code == 200
    assert msg.json()["text"] == "Please follow up with customers"
    listed = await client.get(f"/conversations/{cid}/messages", headers=auth(token))
    assert len(listed.json()) == 1


@pytest.mark.asyncio
async def test_camry_acceptance_workitem_reza_sara(client: AsyncClient, seeded):
    """Manager creates shared WorkItem with tasks for Reza and Sara; sees combined progress."""
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
            "color": "White",
            "sale_price": 2_500_000_000,
        },
    )
    assert vehicle.status_code == 200, vehicle.text
    vehicle_id = vehicle.json()["id"]

    wi = await client.post(
        "/work-items",
        headers=auth(token),
        json={
            "title": "Sell Camry #124",
            "description": "برای فروش این کمری، رضا مشتری‌ها رو پیگیری کنه و سارا آگهی رو آماده کنه.",
            "vehicle_id": vehicle_id,
            "participant_ids": [str(seeded["reza"].id), str(seeded["sara"].id)],
            "priority": "HIGH",
        },
    )
    assert wi.status_code == 200, wi.text
    work_item_id = wi.json()["id"]

    t1 = await client.post(
        "/tasks",
        headers=auth(token),
        json={
            "title": "Contact customers",
            "work_item_id": work_item_id,
            "assignee_ids": [str(seeded["reza"].id)],
            "priority": "HIGH",
        },
    )
    assert t1.status_code == 200, t1.text
    t2 = await client.post(
        "/tasks",
        headers=auth(token),
        json={
            "title": "Prepare listing",
            "work_item_id": work_item_id,
            "assignee_ids": [str(seeded["sara"].id)],
            "assignment_target_type": AssignmentTargetType.TEAM.value,
            "assignment_target_id": str(seeded["mkt_team"].id),
            "priority": "HIGH",
        },
    )
    assert t2.status_code == 200, t2.text

    progress = await client.get(f"/work-items/{work_item_id}/progress", headers=auth(token))
    assert progress.status_code == 200
    body = progress.json()
    assert body["total_tasks"] == 2
    assert body["completed_tasks"] == 0
    assert body["progress_pct"] == 0.0
    titles = {t["title"] for t in body["tasks"]}
    assert titles == {"Contact customers", "Prepare listing"}

    reza_token = await login(client, "reza@autoco.example")
    done = await client.post(f"/tasks/{t1.json()['id']}/complete", headers=auth(reza_token))
    assert done.status_code == 200
    assert done.json()["status"] == TaskStatus.COMPLETED.value

    progress2 = await client.get(f"/work-items/{work_item_id}/progress", headers=auth(token))
    assert progress2.json()["completed_tasks"] == 1
    assert progress2.json()["progress_pct"] == 50.0

    sara_token = await login(client, "sara@autoco.example")
    done2 = await client.post(f"/tasks/{t2.json()['id']}/complete", headers=auth(sara_token))
    assert done2.status_code == 200

    progress3 = await client.get(f"/work-items/{work_item_id}/progress", headers=auth(token))
    assert progress3.json()["completed_tasks"] == 2
    assert progress3.json()["progress_pct"] == 100.0
    assert progress3.json()["status"] == "COMPLETED"

    reza_notes = await client.get("/notifications", headers=auth(reza_token))
    assert any("task" in (n.get("entity_type") or "") for n in reza_notes.json())

    timeline = await client.get(f"/work-items/{work_item_id}/timeline", headers=auth(token))
    assert timeline.status_code == 200
    types = {e["event_type"] for e in timeline.json()}
    assert "work_item.created" in types
    assert "task.completed" in types


@pytest.mark.asyncio
async def test_task_dependencies(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    wi = await client.post("/work-items", headers=auth(token), json={"title": "Pipeline"})
    wid = wi.json()["id"]
    a = await client.post(
        "/tasks",
        headers=auth(token),
        json={"title": "A", "work_item_id": wid, "assignee_ids": [str(seeded["sara"].id)]},
    )
    b = await client.post(
        "/tasks",
        headers=auth(token),
        json={"title": "B", "work_item_id": wid, "assignee_ids": [str(seeded["reza"].id)]},
    )
    dep = await client.post(
        "/tasks/dependencies",
        headers=auth(token),
        json={
            "dependent_task_id": b.json()["id"],
            "prerequisite_task_id": a.json()["id"],
        },
    )
    assert dep.status_code == 200

    sara = auth(await login(client, "sara@autoco.example"))
    reza = auth(await login(client, "reza@autoco.example"))
    fail = await client.post(f"/tasks/{b.json()['id']}/complete", headers=reza)
    assert fail.status_code == 400

    await client.post(f"/tasks/{a.json()['id']}/complete", headers=sara)
    ok = await client.post(f"/tasks/{b.json()['id']}/complete", headers=reza)
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_delegation_audit(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    wi = await client.post("/work-items", headers=auth(token), json={"title": "Delegate me"})
    task = await client.post(
        "/tasks",
        headers=auth(token),
        json={
            "title": "Initial",
            "work_item_id": wi.json()["id"],
            "assignee_ids": [str(seeded["reza"].id)],
        },
    )
    tid = task.json()["id"]
    r = await client.post(
        f"/tasks/{tid}/delegate",
        headers=auth(token),
        json={"to_user_id": str(seeded["sara"].id)},
    )
    assert r.status_code == 200

    sara_token = await login(client, "sara@autoco.example")
    notes = await client.get("/notifications", headers=auth(sara_token))
    assert any("delegated" in n["title"].lower() for n in notes.json())

    timeline = await client.get(f"/timeline/task/{tid}", headers=auth(token))
    assert any(e["event_type"] == "task.reassigned" for e in timeline.json())


@pytest.mark.asyncio
async def test_sla_warning_breach_escalate(db: AsyncSession, seeded):
    svc = WorkService(db)
    sla = SlaService(db)
    policy = await sla.create_policy(
        organization_id=seeded["org"].id,
        name="HIGH 2h",
        priority=Priority.HIGH,
        response_minutes=120,
        warning_minutes=60,
        escalate_on_breach=True,
    )
    wi = await svc.create_work_item(
        organization_id=seeded["org"].id,
        title="SLA WI",
        owner_id=seeded["ali"].id,
    )
    task = await svc.create_task(
        organization_id=seeded["org"].id,
        title="SLA Task",
        owner_id=seeded["ali"].id,
        work_item_id=wi.id,
        assignee_ids=[seeded["reza"].id],
        sla_policy_id=policy.id,
        actor_permissions={PermissionCode.TASK_WRITE},
    )
    past = datetime.now(UTC) - timedelta(minutes=90)
    task.created_at = past
    await db.flush()

    task = await sla.evaluate_task(task.id, now=datetime.now(UTC))
    assert task.sla_state == SlaState.WARNING

    task.created_at = datetime.now(UTC) - timedelta(minutes=180)
    await db.flush()
    task = await sla.evaluate_task(task.id, now=datetime.now(UTC))
    assert task.sla_state == SlaState.ESCALATED

    events = (await db.execute(select(Event).where(Event.entity_id == task.id))).scalars().all()
    types = {e.event_type for e in events}
    assert "sla.warning" in types
    assert "sla.breached" in types or "sla.escalated" in types


@pytest.mark.asyncio
async def test_case_and_events(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    case = await client.post(
        "/cases",
        headers=auth(token),
        json={
            "subject": "Branch availability check",
            "type": CaseType.BRANCH_REQUEST.value,
            "owner_id": str(seeded["reza"].id),
            "priority": "MEDIUM",
        },
    )
    assert case.status_code == 200
    assert case.json()["case_number"].startswith("C-")
    tid = case.json()["id"]
    timeline = await client.get(f"/timeline/case/{tid}", headers=auth(token))
    types = {e["event_type"] for e in timeline.json()}
    assert "case.created" in types
    assert "case.assigned" in types


@pytest.mark.asyncio
async def test_update_case_status_and_owner(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    case = await client.post(
        "/cases",
        headers=auth(token),
        json={"subject": "Follow-up", "type": CaseType.FOLLOW_UP.value},
    )
    assert case.status_code == 200
    cid = case.json()["id"]
    assert case.json()["status"] == "OPEN"

    # فقط وضعیت
    r = await client.patch(f"/cases/{cid}", headers=auth(token), json={"status": "IN_PROGRESS"})
    assert r.status_code == 200
    assert r.json()["status"] == "IN_PROGRESS"
    assert r.json()["owner_id"] is None

    # فقط مسئول — وضعیتِ IN_PROGRESS حفظ می‌شود
    r = await client.patch(
        f"/cases/{cid}", headers=auth(token), json={"owner_id": str(seeded["reza"].id)}
    )
    assert r.status_code == 200
    assert r.json()["owner_id"] == str(seeded["reza"].id)
    assert r.json()["status"] == "IN_PROGRESS"

    timeline = await client.get(f"/timeline/case/{cid}", headers=auth(token))
    types = {e["event_type"] for e in timeline.json()}
    assert "case.status_changed" in types
    assert "case.assigned" in types

    # حذف مسئول
    r = await client.patch(f"/cases/{cid}", headers=auth(token), json={"owner_id": None})
    assert r.status_code == 200
    assert r.json()["owner_id"] is None

    # پروندهٔ ناموجود → 404
    r = await client.patch(
        f"/cases/{uuid.uuid4()}", headers=auth(token), json={"status": "OPEN"}
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_conversation_with_customer_link(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    customer = await client.post(
        "/customers",
        headers=auth(token),
        json={"full_name": "خریدار تست"},
    )
    assert customer.status_code == 200
    cust_id = customer.json()["id"]

    conv = await client.post(
        "/conversations",
        headers=auth(token),
        json={
            "topic": "About customer",
            "participant_ids": [str(seeded["ali"].id)],
            "customer_id": cust_id,
        },
    )
    assert conv.status_code == 200
    assert conv.json()["customer_id"] == cust_id


@pytest.mark.asyncio
async def test_member_role_template_can_list_owned_case(client: AsyncClient, seeded, db: AsyncSession):
    svc = OrgService(db)
    member_codes = [code.value for code in ROLE_TEMPLATES["member"][2]]
    role = await svc.create_role(
        seeded["org"].id,
        "عضو تست",
        "member_case_read_r8",
        member_codes,
        ROLE_TEMPLATES["member"][1],
    )
    member = await svc.create_user(
        organization_id=seeded["org"].id,
        email="member-case@autoco.example",
        full_name="عضو پرونده",
        password="password",
        role_id=role.id,
        branch_id=seeded["branch"].id,
        team_id=seeded["mkt_team"].id,
    )
    await db.commit()

    admin = auth(await login(client, "ali@autoco.example"))
    created = await client.post(
        "/cases",
        headers=admin,
        json={
            "subject": "پیگیری نما",
            "type": CaseType.FOLLOW_UP.value,
            "owner_id": str(member.id),
        },
    )
    assert created.status_code == 200
    case_id = created.json()["id"]

    member_headers = auth(await login(client, "member-case@autoco.example"))
    listed = await client.get("/cases", headers=member_headers)
    assert listed.status_code == 200
    ids = {row["id"] for row in listed.json()}
    assert case_id in ids
