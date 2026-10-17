"""AI Lab workspaces and kind-level access."""

import pytest

from app.core.permissions import PermissionCode
from tests.conftest import auth, login


@pytest.fixture
def ai_lab_on(monkeypatch):
    monkeypatch.setenv("AI_LAB_ENABLED", "true")
    monkeypatch.setenv("AI_LAB_MODE", "manual")
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def perf_user(client, seeded, db):
    from app.services import OrgService

    svc = OrgService(db)
    role = await svc.create_role(
        seeded["org"].id,
        "Perf",
        "perf_ai",
        [PermissionCode.PERF_READ, PermissionCode.PERF_WRITE],
        "organization",
    )
    user = await svc.create_user(
        organization_id=seeded["org"].id,
        email="perf-ws@autoco.example",
        full_name="Perf WS",
        role_id=role.id,
        password="password",
    )
    await db.commit()
    return user


@pytest.fixture
async def manager_user(client, seeded, db):
    from app.services import OrgService

    svc = OrgService(db)
    role = await svc.create_role(
        seeded["org"].id,
        "Mgr",
        "mgr_ai",
        [PermissionCode.PERF_READ, PermissionCode.PERF_APPROVE],
        "organization",
    )
    user = await svc.create_user(
        organization_id=seeded["org"].id,
        email="mgr-ws@autoco.example",
        full_name="Mgr WS",
        role_id=role.id,
        password="password",
    )
    await db.commit()
    return user


@pytest.fixture
async def finance_user(client, seeded, db):
    from app.services import OrgService

    svc = OrgService(db)
    role = await svc.create_role(
        seeded["org"].id,
        "Fin",
        "finance",
        [PermissionCode.PERF_READ, PermissionCode.PRICE_APPROVE],
        "organization",
    )
    user = await svc.create_user(
        organization_id=seeded["org"].id,
        email="fin-ws@autoco.example",
        full_name="Fin WS",
        role_id=role.id,
        password="password",
    )
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_workspaces_perf_and_manager(client, perf_user, manager_user, ai_lab_on):
    perf_token = await login(client, perf_user.email)
    perf_headers = auth(perf_token)
    res = await client.get("/ai-lab/workspaces", headers=perf_headers)
    assert res.status_code == 200
    keys = {w["key"] for w in res.json()["workspaces"]}
    assert keys == {"performance"}

    mgr_token = await login(client, manager_user.email)
    mgr_headers = auth(mgr_token)
    res2 = await client.get("/ai-lab/workspaces", headers=mgr_headers)
    keys2 = {w["key"] for w in res2.json()["workspaces"]}
    assert keys2 == {"manager"}


@pytest.mark.asyncio
async def test_manager_cannot_create_period_review(client, manager_user, ai_lab_on):
    token = await login(client, manager_user.email)
    headers = auth(token)
    res = await client.post(
        "/ai-lab/tasks",
        headers=headers,
        json={"kind": "period_review", "input": {"from_date": "2026-01-01", "to_date": "2026-01-07", "brand": ""}},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_manager_projects_health_snapshot(client, manager_user, ai_lab_on):
    token = await login(client, manager_user.email)
    headers = auth(token)
    res = await client.post(
        "/ai-lab/snapshot",
        headers=headers,
        json={"kind": "projects_health", "input": {"lane": "", "stale_days": 14}},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "projects_health"
    assert "open_cards" in body


@pytest.mark.asyncio
async def test_finance_workspace(client, finance_user, ai_lab_on):
    token = await login(client, finance_user.email)
    headers = auth(token)
    res = await client.get("/ai-lab/workspaces", headers=headers)
    assert res.status_code == 200
    keys = {w["key"] for w in res.json()["workspaces"]}
    assert keys == {"finance"}
    snap = await client.post("/ai-lab/snapshot", headers=headers, json={"kind": "finance_reconcile", "input": {}})
    assert snap.status_code == 200
    assert snap.json()["kind"] == "finance_reconcile"
