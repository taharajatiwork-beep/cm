"""AI Lab history, followups, automation helpers."""

import json
import pytest
from sqlalchemy import select

from app.ai_lab.history import HISTORY_MAX_BYTES, _trim_history
from app.ai_lab.polling import poll_interval_seconds
from app.ai_lab.snapshots import build_snapshot
from app.core.config import get_settings
from tests.conftest import auth, login


@pytest.fixture
def ai_lab_on(monkeypatch):
    monkeypatch.setenv("AI_LAB_ENABLED", "true")
    monkeypatch.setenv("AI_LAB_MODE", "manual")
    monkeypatch.setenv("AI_LAB_INBOUND_SECRET", "inbound-secret-for-tests-32chars!!")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_trim_history_respects_max_bytes():
    big = [{"summary": "x" * 2000, "decisions": [], "outcomes": []} for _ in range(5)]
    trimmed = _trim_history(big)
    assert len(json.dumps(trimmed, ensure_ascii=False).encode("utf-8")) <= HISTORY_MAX_BYTES


def test_poll_intervals_unchanged():
    assert poll_interval_seconds(30) == 60
    assert poll_interval_seconds(400) == 300


@pytest.mark.asyncio
async def test_snapshot_includes_history_key(client, seeded, db, ai_lab_on):
    from app.ai_lab.models import AiTask
    from app.core.permissions import PermissionCode
    from app.services import OrgService

    svc = OrgService(db)
    role = await svc.create_role(
        seeded["org"].id,
        "Perf",
        "p",
        [PermissionCode.PERF_READ, PermissionCode.PERF_WRITE],
        "organization",
    )
    user = await svc.create_user(
        organization_id=seeded["org"].id,
        email="hist@autoco.example",
        full_name="H",
        role_id=role.id,
        password="password",
    )
    row = AiTask(
        organization_id=seeded["org"].id,
        created_by=user.id,
        kind="period_review",
        input_json=json.dumps({"from_date": "2026-01-01", "to_date": "2026-01-07", "brand": ""}),
        snapshot_json="{}",
        status="done",
        result_json=json.dumps(
            {
                "summary": "ok",
                "findings": [],
                "recommendations": [{"id": "r1", "action": "a", "reason": "b", "expected_impact": "c", "confidence": "low"}],
                "data_gaps": [],
            }
        ),
        decisions_json='{"r1": "rejected"}',
    )
    db.add(row)
    await db.commit()
    snap = await build_snapshot(
        db,
        seeded["org"].id,
        "period_review",
        {"from_date": "2026-01-01", "to_date": "2026-01-07", "brand": ""},
    )
    assert "history" in snap
    assert isinstance(snap["history"], list)


@pytest.mark.asyncio
async def test_sms_copy_review_snapshot(client, seeded, db, ai_lab_on):
    from app.perf.models import PmCampaign, PmSmsSend

    camp = PmCampaign(
        organization_id=seeded["org"].id,
        code="SMS1",
        title="T",
        brand="فونیکس",
        budget_toman=1_000_000,
        status="active",
    )
    db.add(camp)
    await db.flush()
    db.add(
        PmSmsSend(
            organization_id=seeded["org"].id,
            campaign_id=camp.id,
            body="فونیکس لغو11",
            recipient_count=100,
            delivered_count=90,
            leads=2,
            cost_toman=100_000,
        )
    )
    await db.commit()
    snap = await build_snapshot(
        db,
        seeded["org"].id,
        "sms_copy_review",
        {"from_date": "2020-01-01", "to_date": "2030-12-31", "brand": ""},
    )
    assert snap["kind"] == "sms_copy_review"
    assert "sms_samples" in snap
    assert "09123456789" not in json.dumps(snap)


@pytest.fixture
async def perf_user(client, seeded, db):
    from app.core.permissions import PermissionCode
    from app.services import OrgService

    svc = OrgService(db)
    role = await svc.create_role(
        seeded["org"].id,
        "Perf FU",
        "perf_fu",
        [PermissionCode.PERF_READ, PermissionCode.PERF_WRITE],
        "organization",
    )
    user = await svc.create_user(
        organization_id=seeded["org"].id,
        email="perf-fu@autoco.example",
        full_name="Perf FU",
        role_id=role.id,
        password="password",
    )
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_accept_creates_followup(client, seeded, db, perf_user, ai_lab_on):
    from app.ai_lab.models import AiRecFollowup, AiTask

    token = await login(client, perf_user.email)
    headers = auth(token)
    row = AiTask(
        organization_id=seeded["org"].id,
        created_by=perf_user.id,
        kind="period_review",
        input_json=json.dumps({"from_date": "2026-01-01", "to_date": "2026-01-31", "brand": ""}),
        snapshot_json="{}",
        status="done",
        result_json=json.dumps(
            {
                "summary": "s",
                "findings": [],
                "recommendations": [
                    {"id": "r1", "action": "a", "reason": "b", "expected_impact": "c", "confidence": "high"}
                ],
                "data_gaps": [],
            }
        ),
    )
    db.add(row)
    await db.commit()
    res = await client.patch(
        f"/ai-lab/tasks/{row.id}/recommendations/r1",
        headers=headers,
        json={"decision": "accepted"},
    )
    assert res.status_code == 200
    fu = await db.scalar(select(AiRecFollowup).where(AiRecFollowup.ai_task_id == row.id))
    assert fu is not None
    assert res.json()["followups"]["r1"]["baseline"] is not None
