"""AI Lab — snapshots, signing, tasks, webhook."""

import json
import time

import pytest

from app.ai_lab.signing import sign, verify
from app.core.config import get_settings
from app.core.permissions import PermissionCode
from app.perf.models import PmCampaign, PmLead, PmSmsSend
from tests.conftest import auth, login


@pytest.fixture
def ai_lab_on(monkeypatch):
    monkeypatch.setenv("AI_LAB_ENABLED", "true")
    monkeypatch.setenv("AI_LAB_MODE", "manual")
    monkeypatch.setenv("AI_LAB_INBOUND_SECRET", "inbound-secret-for-tests-32chars!!")
    monkeypatch.setenv("AI_LAB_OUTBOUND_SECRET", "outbound-secret-for-tests-32chars!")
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
        email="perf-ai@autoco.example",
        full_name="Perf AI",
        role_id=role.id,
        password="password",
    )
    await db.commit()
    return user


def test_sign_verify_roundtrip():
    body = b'{"task_id":"x"}'
    ts = str(int(time.time()))
    secret = "s" * 32
    sig = sign(secret, ts, body)
    assert verify(secret, ts, sig, body)
    assert not verify(secret, ts, "sha256=deadbeef", body)
    assert not verify(secret, str(int(time.time()) - 9999), sig, body)


@pytest.mark.asyncio
async def test_disabled_returns_404(client, perf_user, ai_lab_on, monkeypatch):
    monkeypatch.setenv("AI_LAB_ENABLED", "false")
    get_settings.cache_clear()
    token = await login(client, perf_user.email)
    headers = auth(token)
    res = await client.post("/ai-lab/tasks", headers=headers, json={"kind": "period_review", "input": {}})
    assert res.status_code == 404
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_manual_cycle_and_schema(client, seeded, db, perf_user, ai_lab_on):
    token = await login(client, perf_user.email)
    headers = auth(token)
    camp = PmCampaign(
        organization_id=seeded["org"].id,
        code="AI1",
        title="Test",
        brand="فونیکس",
        budget_toman=10_000_000,
        status="active",
    )
    db.add(camp)
    await db.flush()
    send = PmSmsSend(
        organization_id=seeded["org"].id,
        campaign_id=camp.id,
        body="فونیکس لغو11",
        recipient_count=100,
        delivered_count=90,
        leads=3,
        cost_toman=500_000,
    )
    db.add(send)
    lead = PmLead(organization_id=seeded["org"].id, campaign_id=camp.id, phone="09123456789", quantity=1)
    db.add(lead)
    await db.commit()

    snap_res = await client.post(
        "/ai-lab/snapshot",
        headers=headers,
        json={
            "kind": "period_review",
            "input": {"from_date": "2026-01-01", "to_date": "2026-12-31", "brand": ""},
        },
    )
    assert snap_res.status_code == 200
    blob = json.dumps(snap_res.json(), ensure_ascii=False)
    assert "09123456789" not in blob

    create = await client.post(
        "/ai-lab/tasks",
        headers=headers,
        json={
            "kind": "campaign_review",
            "input": {"campaign_id": str(camp.id)},
        },
    )
    assert create.status_code == 200
    task_id = create.json()["id"]

    bad = await client.post(
        f"/ai-lab/tasks/{task_id}/manual-result",
        headers=headers,
        json={
            "payload": {
                "task_id": task_id,
                "status": "done",
                "result": {
                    "summary": "x",
                    "findings": [{"title": "t", "severity": "low"}],
                    "recommendations": [],
                },
            }
        },
    )
    assert bad.status_code == 200
    assert bad.json()["status"] == "failed"

    good_payload = {
        "task_id": task_id,
        "status": "done",
        "result": {
            "summary": "کمپین خوب است",
            "findings": [{"title": "CPL", "evidence": "500000/3", "severity": "medium"}],
            "recommendations": [{"id": "r1", "action": "ادامه", "reason": "لید دارد", "expected_impact": "+", "confidence": "high"}],
            "data_gaps": [],
        },
    }
    ok = await client.post(
        f"/ai-lab/tasks/{task_id}/manual-result",
        headers=headers,
        json={"payload": good_payload},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "done"

    dup = await client.post(
        f"/ai-lab/tasks/{task_id}/manual-result",
        headers=headers,
        json={"payload": good_payload},
    )
    assert dup.json()["status"] == "done"

    patch = await client.patch(
        f"/ai-lab/tasks/{task_id}/recommendations/r1",
        headers=headers,
        json={"decision": "accepted"},
    )
    assert patch.json()["decisions"]["r1"] == "accepted"


@pytest.mark.asyncio
async def test_inbound_signature(client, seeded, db, perf_user, ai_lab_on):
    token = await login(client, perf_user.email)
    headers = auth(token)
    create = await client.post(
        "/ai-lab/tasks",
        headers=headers,
        json={
            "kind": "channel_budget",
            "input": {
                "next_budget_toman": 1_000_000,
                "reference_from": "2026-01-01",
                "reference_to": "2026-12-31",
            },
        },
    )
    task_id = create.json()["id"]
    payload = {
        "task_id": task_id,
        "status": "done",
        "result": {
            "summary": "ok",
            "findings": [],
            "recommendations": [],
            "data_gaps": [],
        },
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    secret = get_settings().ai_lab_inbound_secret
    ts = str(int(time.time()))
    sig = sign(secret, ts, raw)
    bad = await client.post("/ai-lab/results", content=raw, headers={"X-Grok-Timestamp": ts, "X-Grok-Signature": "bad"})
    assert bad.status_code == 401
    good = await client.post(
        "/ai-lab/results",
        content=raw,
        headers={"X-Grok-Timestamp": ts, "X-Grok-Signature": sig, "Content-Type": "application/json"},
    )
    assert good.status_code == 200
    again = await client.post(
        "/ai-lab/results",
        content=raw,
        headers={"X-Grok-Timestamp": ts, "X-Grok-Signature": sig, "Content-Type": "application/json"},
    )
    assert again.json().get("idempotent") is True


@pytest.mark.asyncio
async def test_webhook_includes_bearer(client, seeded, perf_user, ai_lab_on, monkeypatch):
    from app.ai_lab import service as ai_service

    monkeypatch.setenv("AI_LAB_MODE", "webhook")
    monkeypatch.setenv("AI_LAB_OUTBOUND_URL", "http://127.0.0.1:9/capture")
    monkeypatch.setenv("AI_LAB_OUTBOUND_BEARER", "test-bearer-token")
    monkeypatch.setenv("LLM_EXTERNAL_ENABLED", "true")
    get_settings.cache_clear()
    captured: dict = {}

    class FakeResponse:
        status_code = 202

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, **kw):
            captured["headers"] = kw.get("headers")
            return FakeResponse()

    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **_kw: FakeClient())
    token = await login(client, perf_user.email)
    headers = auth(token)
    await client.post(
        "/ai-lab/tasks",
        headers=headers,
        json={
            "kind": "period_review",
            "input": {"from_date": "2026-01-01", "to_date": "2026-01-07", "brand": ""},
        },
    )
    assert captured.get("headers", {}).get("Authorization") == "Bearer test-bearer-token"
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_webhook_send_failure(client, seeded, perf_user, ai_lab_on, monkeypatch):
    monkeypatch.setenv("AI_LAB_MODE", "webhook")
    monkeypatch.setenv("AI_LAB_OUTBOUND_URL", "http://127.0.0.1:9/nope")
    monkeypatch.setenv("LLM_EXTERNAL_ENABLED", "true")
    get_settings.cache_clear()
    token = await login(client, perf_user.email)
    headers = auth(token)
    create = await client.post(
        "/ai-lab/tasks",
        headers=headers,
        json={
            "kind": "period_review",
            "input": {"from_date": "2026-01-01", "to_date": "2026-01-07", "brand": ""},
        },
    )
    assert create.status_code == 200
    assert create.json()["status"] == "failed"
    get_settings.cache_clear()
