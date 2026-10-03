"""GET /admin/analytics + GET /admin/monitoring — فقط org.admin، payload کامل."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import OrgService
from tests.conftest import auth, login, seeded  # noqa: F401


async def _org_admin(client: AsyncClient, seeded: dict, db: AsyncSession) -> str:
    svc = OrgService(db)
    await svc.create_user(
        organization_id=seeded["org"].id,
        email="boss2@autoco.example",
        full_name="Boss Analytics",
        password="password",
        role_id=seeded["admin_role"].id,
        branch_id=seeded["branch"].id,
    )
    await db.commit()
    return await login(client, "boss2@autoco.example")


@pytest.mark.asyncio
async def test_admin_analytics_requires_org_admin(client: AsyncClient, seeded, db):
    """کاربر بدون org.admin → 403."""
    token = await login(client, "ali@autoco.example")
    r = await client.get("/admin/analytics", headers=auth(token))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_analytics_payload_for_admin(client: AsyncClient, seeded, db):
    """ادمین سازمان همه بخش‌های تحلیل‌ها را می‌بیند با ساختار درست."""
    token = await _org_admin(client, seeded, db)
    r = await client.get("/admin/analytics", headers=auth(token))
    assert r.status_code == 200, r.text
    data = r.json()

    for key in (
        "tasks_weekly",
        "tasks_overdue",
        "avg_completion_hours",
        "tasks_by_priority",
        "cases_by_status",
        "cases_by_type",
        "avg_case_resolution_hours",
        "reply_buckets",
        "messages_daily",
        "vehicles_aging",
        "vehicles_value_by_status",
        "audit_daily_7d",
        "top_actions",
        "login_failed_7d",
        "as_of_jalali",
    ):
        assert key in data, key

    assert len(data["tasks_weekly"]) == 8
    assert all(set(w) == {"week", "created", "completed"} for w in data["tasks_weekly"])
    assert set(data["reply_buckets"]) == {"lt5", "lt30", "lt120", "gt120", "no_reply"}
    assert set(data["vehicles_aging"]) == {"lt7", "lt30", "lt90", "gt90"}
    assert len(data["messages_daily"]) == 14
    assert len(data["audit_daily_7d"]) == 7
    assert all(set(d) == {"day", "count"} for d in data["messages_daily"])
    assert isinstance(data["tasks_by_priority"], dict)
    assert isinstance(data["cases_by_type"], dict)


@pytest.mark.asyncio
async def test_admin_monitoring_requires_org_admin(client: AsyncClient, seeded, db):
    token = await login(client, "ali@autoco.example")
    r = await client.get("/admin/monitoring", headers=auth(token))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_monitoring_payload_for_admin(client: AsyncClient, seeded, db):
    """ادمین سازمان وضعیت DB، صف خروجی، قفل jobها و زنجیرهٔ ممیزی را می‌بیند."""
    token = await _org_admin(client, seeded, db)
    r = await client.get("/admin/monitoring", headers=auth(token))
    assert r.status_code == 200, r.text
    data = r.json()

    for key in (
        "database",
        "outbox",
        "job_locks",
        "events_24h",
        "auth_failed_24h",
        "audit_chain",
        "integrations",
        "as_of_jalali",
    ):
        assert key in data, key

    dbinfo = data["database"]
    assert set(dbinfo["table_counts"]) >= {"users", "tasks", "audit_logs"}
    assert dbinfo["table_counts"]["users"] >= 1
    assert isinstance(data["job_locks"], list)
    assert set(data["audit_chain"]) == {"ok", "rows_checked", "broken_at", "detail"}
    assert data["audit_chain"]["ok"] in (True, False, None)
    assert "outbox" in data and set(data["outbox"]) == {
        "by_status",
        "oldest_pending_minutes",
        "failed_samples",
    }