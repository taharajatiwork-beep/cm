"""ستون فقرات درخواست تا گزارش."""

import ast
from pathlib import Path
from uuid import uuid4

from app.core.permissions import PermissionCode
from tests.conftest import auth, login


def test_services_do_not_import_perf():
    """ماژول‌های زیرین نباید به perf وابسته باشند (perf خودش به آن‌ها وابسته است).

    استثنای مجاز: پلِ `app.core.campaigns` که عمداً در core زندگی می‌کند تا هر دو
    ماژول بتوانند از آن استفاده کنند بدون وابستگی دوطرفه. فقط import تأخیری
    (داخل تابع) مجاز است — import سطح ماژول یعنی وابستگی ساختاری واقعی.
    """
    root = Path(__file__).resolve().parents[1] / "app"
    for folder in ("services", "requests", "core"):
        for path in (root / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
                if isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)
                if not any(name == "app.perf" or name.startswith("app.perf.") for name in modules):
                    continue
                # فقط پلِ core مجاز است و فقط با import تأخیری
                assert path.name == "campaigns.py", path
                assert isinstance(node, ast.ImportFrom) and node.col_offset > 0, path


async def _user(db, seeded, email, perms):
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


async def test_operational_task_and_project_page(client, seeded, db):
    await _user(db, seeded, "boss-u@autoco.example", [PermissionCode.REQUEST_CREATE])
    await _user(db, seeded, "triage-u@autoco.example", [PermissionCode.REQUEST_TRIAGE, PermissionCode.TASK_WRITE])
    boss = auth(await login(client, "boss-u@autoco.example"))
    triage = auth(await login(client, "triage-u@autoco.example"))
    created = await client.post(
        "/requests",
        headers=boss,
        json={"title": "قیمت امروز", "kind": "قیمت و پست‌ها", "team_id": str(seeded["mkt_team"].id)},
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]
    task = await client.post(f"/requests/{request_id}/tasks", headers=triage, json={"title": "اصلاح قیمت"})
    assert task.status_code == 201, task.text
    assert task.json()["status"] == "converted"

    project_req = await client.post(
        "/requests",
        headers=boss,
        json={"title": "تبلیغ", "kind": "تبلیغات", "team_id": str(seeded["mkt_team"].id)},
    )
    made = await client.post(
        f"/requests/{project_req.json()['id']}/projects",
        headers=triage,
        json={"title": "طرح", "kind": "طراحی", "team_id": str(seeded["mkt_team"].id)},
    )
    assert made.status_code == 201, made.text
    detail = await client.get(f"/requests/projects/{made.json()['id']}", headers=triage)
    assert detail.status_code == 200, detail.text
    assert "thread_id" in detail.json()
    preview = await client.post(f"/requests/projects/{made.json()['id']}/apply-template", headers=triage, json={})
    assert preview.status_code == 422
    applied = await client.post(
        f"/requests/projects/{made.json()['id']}/apply-template", headers=triage, json={"confirm": True}
    )
    assert applied.status_code == 201, applied.text
    assert len(applied.json()["tasks"]) == 4


async def test_linked_expense_needs_manager(client, seeded, db):
    await _user(db, seeded, "perf-u@autoco.example", [PermissionCode.PERF_WRITE, PermissionCode.REQUEST_CREATE])
    await _user(
        db,
        seeded,
        "lead-u@autoco.example",
        [PermissionCode.REQUEST_TRIAGE, PermissionCode.EXPENSE_APPROVE, PermissionCode.PERF_READ],
    )
    await _user(db, seeded, "fin-u@autoco.example", [PermissionCode.PRICE_WRITE, PermissionCode.PERF_READ])
    perf = auth(await login(client, "perf-u@autoco.example"))
    lead = auth(await login(client, "lead-u@autoco.example"))
    fin = auth(await login(client, "fin-u@autoco.example"))
    req = await client.post("/requests", headers=perf, json={"title": "هزینه", "kind": "عمومی"})
    project = await client.post(
        f"/requests/{req.json()['id']}/projects",
        headers=lead,
        json={"title": "پروژه هزینه", "kind": "عمومی"},
    )
    payment = await client.post(
        "/perf/payments",
        headers=perf,
        json={"kind": "other", "amount_toman": 1000, "project_id": project.json()["id"], "team_id": str(seeded["mkt_team"].id)},
    )
    assert payment.status_code == 201, payment.text
    pay_id = payment.json()["id"]
    blocked = await client.post(f"/perf/payments/{pay_id}/advance", headers=fin, json={"action": "pay", "seen_amount_toman": 1000})
    assert blocked.status_code == 403, blocked.text
    ok = await client.post(f"/perf/payments/{pay_id}/advance", headers=lead, json={"action": "manager"})
    assert ok.status_code == 200, ok.text
    paid = await client.post(f"/perf/payments/{pay_id}/advance", headers=fin, json={"action": "pay", "seen_amount_toman": 1000})
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "recorded"


async def test_report_scope_is_clamped(client, seeded, db):
    await _user(db, seeded, "me-u@autoco.example", [PermissionCode.TASK_READ])
    me = auth(await login(client, "me-u@autoco.example"))
    own = await client.get("/reports/work?scope=me", headers=me)
    assert own.status_code == 200, own.text
    denied = await client.get("/reports/work?scope=org", headers=me)
    assert denied.status_code == 403
    person = await client.get("/reports/work?scope=me&group_by=person", headers=me)
    assert person.status_code == 403


async def test_foreign_context_is_hidden(client, seeded, db):
    await _user(db, seeded, "ctx-u@autoco.example", [PermissionCode.REQUEST_CREATE])
    headers = auth(await login(client, "ctx-u@autoco.example"))
    missing = await client.get(f"/requests/context/project/{uuid4()}", headers=headers)
    assert missing.status_code == 404


async def test_task_from_message_needs_confirm(client, seeded, db):
    user = await _user(
        db,
        seeded,
        "chat-u@autoco.example",
        [PermissionCode.CONVERSATION_WRITE, PermissionCode.CONVERSATION_READ, PermissionCode.TASK_WRITE, PermissionCode.REQUEST_CREATE],
    )
    headers = auth(await login(client, "chat-u@autoco.example"))
    conv = await client.post(
        "/conversations", headers=headers, json={"topic": "گفتگو", "participant_ids": [str(user.id)]}
    )
    assert conv.status_code == 200, conv.text
    conv_id = conv.json()["id"]
    message = await client.post(f"/conversations/{conv_id}/messages", headers=headers, json={"text": "این را پیگیری کن"})
    assert message.status_code == 200, message.text
    preview = await client.post(
        f"/conversations/{conv_id}/messages/{message.json()['id']}/task", headers=headers, json={}
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["created"] is False
    made = await client.post(
        f"/conversations/{conv_id}/messages/{message.json()['id']}/task", headers=headers, json={"confirm": True}
    )
    assert made.status_code == 200, made.text
    assert made.json()["created"] is True
    ghost = await client.post(f"/conversations/{conv_id}/approve-payment", headers=headers, json={})
    assert ghost.status_code == 404
