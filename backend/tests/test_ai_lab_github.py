"""AI Lab GitHub result polling — signature, schedule, mocked API."""

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.ai_lab.github_results import envelope_to_callback, fetch_result_file
from app.ai_lab.polling import due_for_poll, is_poll_timeout, poll_interval_seconds, task_age_seconds
from app.ai_lab.signing import verify_github_result_signature
from app.core.config import get_settings
from tests.conftest import auth, login


def _github_sig(secret: str, timestamp: str | int, body: str) -> str:
    msg = f"{timestamp}.{body}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _done_body(task_id: str) -> str:
    payload = {
        "task_id": task_id,
        "status": "done",
        "result": {
            "summary": "ok",
            "findings": [{"title": "t", "evidence": "e", "severity": "low"}],
            "recommendations": [],
            "data_gaps": [],
        },
    }
    return json.dumps(payload, ensure_ascii=False)


@pytest.fixture
async def perf_user(client, seeded, db):
    from app.core.permissions import PermissionCode
    from app.services import OrgService

    svc = OrgService(db)
    role = await svc.create_role(
        seeded["org"].id,
        "Perf GH",
        "perf_gh",
        [PermissionCode.PERF_READ, PermissionCode.PERF_WRITE],
        "organization",
    )
    user = await svc.create_user(
        organization_id=seeded["org"].id,
        email="perf-gh@autoco.example",
        full_name="Perf GH",
        role_id=role.id,
        password="password",
    )
    await db.commit()
    return user


@pytest.fixture
def ai_lab_github(monkeypatch):
    monkeypatch.setenv("AI_LAB_ENABLED", "true")
    monkeypatch.setenv("AI_LAB_MODE", "webhook")
    monkeypatch.setenv("AI_LAB_RESULT_SOURCE", "github")
    monkeypatch.setenv("AI_LAB_GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("AI_LAB_GITHUB_TOKEN_RO", "ghp_test_token_not_real")
    monkeypatch.setenv("AI_LAB_INBOUND_SECRET", "inbound-secret-for-tests-32chars!!")
    monkeypatch.setenv("AI_LAB_OUTBOUND_SECRET", "outbound-secret-for-tests-32chars!")
    monkeypatch.setenv("AI_LAB_OUTBOUND_URL", "http://127.0.0.1:9/capture")
    monkeypatch.setenv("LLM_EXTERNAL_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_verify_github_signature_ok_and_bad():
    secret = "s" * 32
    body = '{"task_id":"x","status":"done"}'
    ts = 1700000000
    sig = _github_sig(secret, ts, body)
    assert verify_github_result_signature(secret, ts, sig, body)
    assert not verify_github_result_signature(secret, ts, "sha256=dead", body)
    assert not verify_github_result_signature(secret, ts, sig, body + " ")


def test_envelope_validation_mismatch_and_invalid_sig():
    secret = "inbound-secret-for-tests-32chars!!"
    task_id = uuid4()
    other = uuid4()
    body = _done_body(str(task_id))
    ts = str(int(time.time()))
    env = {
        "task_id": str(task_id),
        "timestamp": ts,
        "signature": _github_sig(secret, ts, body),
        "body": body,
    }
    parsed, err = envelope_to_callback(env, task_id, secret)
    assert parsed is not None and err is None

    env_bad_tid = {**env, "task_id": str(other)}
    _, err2 = envelope_to_callback(env_bad_tid, task_id, secret)
    assert err2 == "task_id mismatch"

    env_bad_sig = {**env, "signature": "sha256=00"}
    _, err3 = envelope_to_callback(env_bad_sig, task_id, secret)
    assert err3 == "invalid signature"

    body_wrong = _done_body(str(other))
    env_body = {
        **env,
        "body": body_wrong,
        "signature": _github_sig(secret, ts, body_wrong),
    }
    _, err4 = envelope_to_callback(env_body, task_id, secret)
    assert err4 == "task_id mismatch in body"


def test_poll_intervals_and_due():
    assert poll_interval_seconds(30) == 60
    assert poll_interval_seconds(600) == 300
    assert poll_interval_seconds(3600) == 900
    assert is_poll_timeout(2 * 3600 + 1)
    created = datetime.now(UTC) - timedelta(minutes=2)
    assert due_for_poll(created, None)
    assert not due_for_poll(created, datetime.now(UTC) - timedelta(seconds=30))
    old = datetime.now(UTC) - timedelta(hours=3)
    assert task_age_seconds(old) > 7200


@pytest.mark.asyncio
async def test_fetch_result_404(monkeypatch):
    import httpx

    class Resp:
        status_code = 404
        text = ""

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return None

        async def get(self, url, headers=None):
            assert headers.get("Authorization", "").startswith("Bearer ")
            return Resp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: Client())
    r404 = await fetch_result_file("owner/repo", uuid4(), "ghp_test")
    assert not r404.found and r404.transient_error is None


@pytest.mark.asyncio
async def test_fetch_result_5xx_transient(monkeypatch):
    import httpx

    class Resp:
        status_code = 502
        text = ""

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return None

        async def get(self, url, headers=None):
            return Resp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kw: Client())
    r = await fetch_result_file("owner/repo", uuid4(), "tok")
    assert r.transient_error


@pytest.mark.asyncio
async def test_webhook_github_no_callback_waiting(client, seeded, perf_user, ai_lab_github, monkeypatch):
    from app.ai_lab import service as ai_service

    captured: dict = {}

    class FakeResponse:
        status_code = 202

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, content=None, headers=None):
            captured["body"] = json.loads(content.decode("utf-8"))
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **_kw: FakeClient())

    token = await login(client, perf_user.email)
    headers = auth(token)
    res = await client.post(
        "/ai-lab/tasks",
        headers=headers,
        json={"kind": "period_review", "input": {"from_date": "2026-01-01", "to_date": "2026-01-07", "brand": ""}},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "waiting"
    assert "callback_url" not in captured["body"]
    auth_hdr = captured.get("headers", {}).get("Authorization", "")
    assert "ghp" not in auth_hdr


@pytest.mark.asyncio
async def test_poll_endpoint_applies_github_result(client, seeded, db, perf_user, ai_lab_github, monkeypatch):
    from app.ai_lab import service as ai_service

    class FakeResponse:
        status_code = 202

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_a, **_kw):
            return FakeResponse()

    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **_kw: FakeClient())

    token = await login(client, perf_user.email)
    headers = auth(token)
    create = await client.post(
        "/ai-lab/tasks",
        headers=headers,
        json={"kind": "period_review", "input": {"from_date": "2026-01-01", "to_date": "2026-01-07", "brand": ""}},
    )
    task_id = create.json()["id"]
    secret = get_settings().ai_lab_inbound_secret
    body = _done_body(task_id)
    ts = str(int(time.time()))
    envelope = {
        "task_id": task_id,
        "timestamp": ts,
        "signature": _github_sig(secret, ts, body),
        "body": body,
    }

    async def fake_fetch(repo, tid, token):
        assert token == "ghp_test_token_not_real"
        return type("R", (), {"found": True, "transient_error": None, "apply_error": None, "payload": envelope})()

    monkeypatch.setattr(ai_service, "fetch_result_file", fake_fetch)
    poll = await client.post(f"/ai-lab/tasks/{task_id}/poll", headers=headers)
    assert poll.status_code == 200
    assert poll.json()["status"] == "done"
    assert poll.json()["last_polled_at"] is not None
    again = await client.post(f"/ai-lab/tasks/{task_id}/poll", headers=headers)
    assert again.json()["status"] == "done"
