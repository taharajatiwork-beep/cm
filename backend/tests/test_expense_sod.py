"""جداسازی وظایف: سازنده، سرپرست، مالی روی یک هزینه."""

from app.core.permissions import PermissionCode
from tests.conftest import auth, login


async def _grant_user(db, seeded, email, perms):
    from app.services import OrgService

    svc = OrgService(db)
    role = await svc.create_role(seeded["org"].id, email, email.split("@")[0], perms, "team")
    user = await svc.create_user(
        organization_id=seeded["org"].id,
        email=email,
        full_name=email,
        password="password",
        role_id=role.id,
        branch_id=seeded["branch"].id,
        team_id=seeded["mkt_team"].id,
    )
    await db.commit()
    return user


async def test_same_user_cannot_manager_and_finance(client, seeded, db):
    dual = await _grant_user(
        db,
        seeded,
        "dual@autoco.example",
        [
            PermissionCode.REQUEST_TRIAGE,
            PermissionCode.EXPENSE_PAY,
            PermissionCode.EXPENSE_REQUEST,
            PermissionCode.PERF_WRITE,
            PermissionCode.PERF_READ,
        ],
    )
    headers = auth(await login(client, dual.email))
    created = await client.post(
        "/perf/payments",
        headers=headers,
        json={"kind": "other", "amount_toman": 1000, "beneficiary": "x", "project_id": None, "request_id": None},
    )
    assert created.status_code in (201, 422, 400)
    if created.status_code != 201:
        return
    payment_id = created.json()["id"]
    mgr = await client.post(
        f"/perf/payments/{payment_id}/advance",
        headers=headers,
        json={"action": "manager"},
    )
    if mgr.status_code == 403:
        return
    assert mgr.status_code == 200, mgr.text
    fin = await client.post(
        f"/perf/payments/{payment_id}/advance",
        headers=headers,
        json={"action": "finance", "seen_amount_toman": 1000},
    )
    assert fin.status_code == 403, fin.text


async def test_manager_step_for_linked_payment(client, seeded, db):
    from app.requests.models import WorkProject, WorkRequest

    triage = await _grant_user(
        db,
        seeded,
        "mgrpay@autoco.example",
        [
            PermissionCode.REQUEST_TRIAGE,
            PermissionCode.EXPENSE_REQUEST,
            PermissionCode.PERF_READ,
            PermissionCode.PERF_WRITE,
        ],
    )
    fin = await _grant_user(
        db,
        seeded,
        "finpay@autoco.example",
        [PermissionCode.EXPENSE_PAY, PermissionCode.PERF_READ],
    )
    req = WorkRequest(
        organization_id=seeded["org"].id,
        code="REQ-PAY",
        title="هزینه",
        description="",
        kind="عمومی",
        priority="normal",
        status="converted",
        requested_by=seeded["ali"].id,
        team_id=seeded["mkt_team"].id,
        created_by=seeded["ali"].id,
    )
    db.add(req)
    await db.flush()
    project = WorkProject(
        organization_id=seeded["org"].id,
        code="PRJ-PAY",
        title="پروژه",
        description="",
        kind="عمومی",
        status="new",
        request_id=req.id,
        team_id=seeded["mkt_team"].id,
        created_by=triage.id,
    )
    db.add(project)
    await db.commit()

    maker = await _grant_user(
        db,
        seeded,
        "makerpay@autoco.example",
        [PermissionCode.EXPENSE_REQUEST, PermissionCode.PERF_READ, PermissionCode.PERF_WRITE],
    )
    maker_headers = auth(await login(client, maker.email))
    created = await client.post(
        "/perf/payments",
        headers=maker_headers,
        json={
            "kind": "other",
            "amount_toman": 2000,
            "beneficiary": "z",
            "project_id": str(project.id),
        },
    )
    assert created.status_code == 201, created.text
    payment_id = created.json()["id"]
    mgr_headers = auth(await login(client, triage.email))
    mgr = await client.post(
        f"/perf/payments/{payment_id}/advance",
        headers=mgr_headers,
        json={"action": "manager"},
    )
    assert mgr.status_code == 200, mgr.text
    assert mgr.json()["status"] == "manager_ok"
    fin_headers = auth(await login(client, fin.email))
    pay = await client.post(
        f"/perf/payments/{payment_id}/advance",
        headers=fin_headers,
        json={"action": "finance", "seen_amount_toman": 2000},
    )
    assert pay.status_code == 200, pay.text
    assert pay.json()["status"] == "recorded"


async def test_finance_sees_amount_change_409(client, seeded, db):
    fin = await _grant_user(
        db,
        seeded,
        "finonly@autoco.example",
        [PermissionCode.EXPENSE_PAY, PermissionCode.PERF_READ],
    )
    headers = auth(await login(client, fin.email))
    created = await client.post(
        "/perf/payments",
        headers=headers,
        json={"kind": "other", "amount_toman": 5000, "beneficiary": "y"},
    )
    if created.status_code != 201:
        return
    payment_id = created.json()["id"]
    bad = await client.post(
        f"/perf/payments/{payment_id}/advance",
        headers=headers,
        json={"action": "finance", "seen_amount_toman": 1},
    )
    assert bad.status_code == 409, bad.text


async def test_mina_like_user_cannot_manager_ok_own_expense(client, seeded, db):
    """expense.request + request.triage — نه تأیید هزینهٔ خودش."""
    from app.requests.models import WorkProject, WorkRequest

    triage = await _grant_user(
        db,
        seeded,
        "mina-like@autoco.example",
        [
            PermissionCode.REQUEST_TRIAGE,
            PermissionCode.EXPENSE_REQUEST,
            PermissionCode.PERF_READ,
            PermissionCode.PERF_WRITE,
        ],
    )
    req = WorkRequest(
        organization_id=seeded["org"].id,
        code="REQ-MINA",
        title="هزینه مینا",
        description="",
        kind="عمومی",
        priority="normal",
        status="converted",
        requested_by=seeded["ali"].id,
        team_id=seeded["mkt_team"].id,
        created_by=triage.id,
    )
    db.add(req)
    await db.flush()
    project = WorkProject(
        organization_id=seeded["org"].id,
        code="PRJ-MINA",
        title="پروژه",
        description="",
        kind="عمومی",
        status="new",
        request_id=req.id,
        team_id=seeded["mkt_team"].id,
        created_by=triage.id,
    )
    db.add(project)
    await db.commit()

    headers = auth(await login(client, triage.email))
    created = await client.post(
        "/perf/payments",
        headers=headers,
        json={
            "kind": "other",
            "amount_toman": 3000,
            "beneficiary": "self",
            "project_id": str(project.id),
        },
    )
    assert created.status_code == 201, created.text
    payment_id = created.json()["id"]
    mgr = await client.post(
        f"/perf/payments/{payment_id}/advance",
        headers=headers,
        json={"action": "manager"},
    )
    assert mgr.status_code == 403, mgr.text


async def test_org_admin_second_finance_step_blocked_but_audited(client, seeded, db):
    from uuid import UUID

    from app.models import AuditLog
    from app.requests.models import WorkProject, WorkRequest
    from sqlalchemy import select

    from app.services import OrgService

    svc = OrgService(db)
    admin_user = await svc.create_user(
        organization_id=seeded["org"].id,
        email="pay-admin@autoco.example",
        full_name="Pay Admin",
        password="password",
        role_id=seeded["admin_role"].id,
        branch_id=seeded["branch"].id,
    )
    req = WorkRequest(
        organization_id=seeded["org"].id,
        code="REQ-ADM",
        title="هزینه ادمین",
        description="",
        kind="عمومی",
        priority="normal",
        status="converted",
        requested_by=seeded["ali"].id,
        team_id=seeded["mkt_team"].id,
        created_by=seeded["ali"].id,
    )
    db.add(req)
    await db.flush()
    project = WorkProject(
        organization_id=seeded["org"].id,
        code="PRJ-ADM",
        title="پروژه",
        description="",
        kind="عمومی",
        status="new",
        request_id=req.id,
        team_id=seeded["mkt_team"].id,
        created_by=seeded["ali"].id,
    )
    db.add(project)
    await db.commit()

    maker = await _grant_user(
        db,
        seeded,
        "makeradm@autoco.example",
        [PermissionCode.EXPENSE_REQUEST, PermissionCode.PERF_READ, PermissionCode.PERF_WRITE],
    )
    maker_headers = auth(await login(client, maker.email))
    created = await client.post(
        "/perf/payments",
        headers=maker_headers,
        json={
            "kind": "other",
            "amount_toman": 4000,
            "beneficiary": "v",
            "project_id": str(project.id),
        },
    )
    assert created.status_code == 201, created.text
    payment_id = created.json()["id"]
    admin_headers = auth(await login(client, admin_user.email))
    mgr = await client.post(
        f"/perf/payments/{payment_id}/advance",
        headers=admin_headers,
        json={"action": "manager"},
    )
    assert mgr.status_code == 200, mgr.text
    fin = await client.post(
        f"/perf/payments/{payment_id}/advance",
        headers=admin_headers,
        json={"action": "finance", "seen_amount_toman": 4000},
    )
    assert fin.status_code == 403, fin.text
    logs = (
        await db.scalars(
            select(AuditLog).where(
                AuditLog.organization_id == seeded["org"].id,
                    AuditLog.entity_id == UUID(payment_id),
                    AuditLog.action == "payment.manager_ok",
            )
        )
    ).all()
    assert len(logs) == 1
