"""مرحله ۴: GET /admin/overview فقط برای org.admin + تست‌های گفتگو/نوتیفیکیشن."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification
from app.services import OrgService
from tests.conftest import auth, login, seeded  # noqa: F401


async def _org_admin(client: AsyncClient, seeded: dict, db: AsyncSession) -> str:
    svc = OrgService(db)
    await svc.create_user(
        organization_id=seeded["org"].id,
        email="boss@autoco.example",
        full_name="Boss Admin",
        password="password",
        role_id=seeded["admin_role"].id,
        branch_id=seeded["branch"].id,
    )
    await db.commit()
    return await login(client, "boss@autoco.example")


# --------------------------------------------------------------------- overview


@pytest.mark.asyncio
async def test_admin_overview_requires_org_admin(client: AsyncClient, seeded, db):
    """مدیر شعبه org.admin ندارد، پس ۴۰۳ می‌گیرد."""
    ali = await login(client, "ali@autoco.example")
    r = await client.get("/admin/overview", headers=auth(ali))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_overview_payload_for_admin(client: AsyncClient, seeded, db):
    """ادمین سازمان همه بخش‌های نمای کلی را می‌بیند."""
    token = await _org_admin(client, seeded, db)
    ali_token = await login(client, "ali@autoco.example")

    # یک گفتگو با پیام از یک نفر → منتظر پاسخ
    conv = await client.post(
        "/conversations",
        headers=auth(ali_token),
        json={
            "channel": "WEB",
            "participant_ids": [str(seeded["ali"].id)],
            "topic": "Overview thread",
        },
    )
    assert conv.status_code == 200, conv.text
    cid = conv.json()["id"]
    posted = await client.post(
        f"/conversations/{cid}/messages",
        headers=auth(ali_token),
        json={"text": "سلام، کسی جواب می‌دهد؟", "channel": "WEB"},
    )
    assert posted.status_code == 200, posted.text

    r = await client.get("/admin/overview", headers=auth(token))
    assert r.status_code == 200, r.text
    data = r.json()

    for key in (
        "as_of_jalali",
        "users",
        "messages_7d",
        "conversations_waiting_reply",
        "avg_first_reply_minutes",
        "tasks_by_branch",
        "top_users",
        "cases",
        "approvals_pending",
        "vehicles",
        "divar_errors",
        "trend",
    ):
        assert key in data, f"missing key {key}"

    # کاربران: boss + چهار کاربر seed
    assert data["users"]["total"] == 5
    assert data["users"]["active"] == 5
    assert data["users"]["inactive"] == 0
    # پیام تازه در ۷ روز اخیر شمرده می‌شود
    assert data["messages_7d"] >= 1
    # گفتگوی بدون پاسخ در شمارش منتظر پاسخ است
    assert data["conversations_waiting_reply"] >= 1
    assert isinstance(data["tasks_by_branch"], list)
    assert isinstance(data["top_users"], list)
    assert isinstance(data["trend"], list)


@pytest.mark.asyncio
async def test_admin_overview_avg_first_reply(client: AsyncClient, seeded, db):
    """میانگین زمان اولین پاسخ وقتی هر دو طرف پیام داده‌اند محاسبه می‌شود."""
    token = await _org_admin(client, seeded, db)
    ali = await login(client, "ali@autoco.example")
    sara = await login(client, "sara@autoco.example")

    conv = await client.post(
        "/conversations",
        headers=auth(ali),
        json={
            "channel": "WEB",
            "participant_ids": [str(seeded["ali"].id), str(seeded["sara"].id)],
            "topic": "Two-way",
        },
    )
    cid = conv.json()["id"]
    await client.post(
        f"/conversations/{cid}/messages",
        headers=auth(ali),
        json={"text": "سلام سارا", "channel": "WEB"},
    )
    await client.post(
        f"/conversations/{cid}/messages",
        headers=auth(sara),
        json={"text": "سلام علی", "channel": "WEB"},
    )

    r = await client.get("/admin/overview", headers=auth(token))
    assert r.status_code == 200
    data = r.json()
    assert data["avg_first_reply_minutes"] is not None
    assert data["avg_first_reply_minutes"] >= 0


# ----------------------------------------------------------------- conversations


@pytest.mark.asyncio
async def test_conversation_list_carries_last_message_and_needs_reply(
    client: AsyncClient, seeded
):
    """لیست گفتگو باید last_message/needs_reply را بدون درخواست جدا بدهد."""
    ali = await login(client, "ali@autoco.example")
    sara = await login(client, "sara@autoco.example")

    conv = await client.post(
        "/conversations",
        headers=auth(ali),
        json={
            "channel": "WEB",
            "participant_ids": [str(seeded["ali"].id), str(seeded["sara"].id)],
            "topic": "Board thread",
        },
    )
    assert conv.status_code == 200, conv.text
    cid = conv.json()["id"]

    listed = await client.get("/conversations", headers=auth(ali))
    assert listed.status_code == 200
    rows = listed.json()
    row = next(r for r in rows if r["id"] == cid)
    # گفتگوی خالی چیزی برای پاسخ ندارد
    assert row["needs_reply"] is False
    assert row["last_message_text"] is None

    await client.post(
        f"/conversations/{cid}/messages",
        headers=auth(sara),
        json={"text": "پیام تازه برای علی", "channel": "WEB"},
    )
    rows = (await client.get("/conversations", headers=auth(ali))).json()
    row = next(r for r in rows if r["id"] == cid)
    assert row["last_message_text"] == "پیام تازه برای علی"
    assert row["last_sender_id"] == str(seeded["sara"].id)
    assert row["last_message_at"] is not None
    # طرف مقابل فرستاده، پس هنوز منتظر پاسخِ علی است
    assert row["needs_reply"] is True
    assert str(seeded["sara"].id) in [str(p) for p in row["participant_ids"]]


@pytest.mark.asyncio
async def test_add_participant_to_existing_conversation(client: AsyncClient, seeded):
    """افزودن همکار به گفتگوی موجود."""
    ali = await login(client, "ali@autoco.example")
    reza = seeded["reza"]

    conv = await client.post(
        "/conversations",
        headers=auth(ali),
        json={
            "channel": "WEB",
            "participant_ids": [str(seeded["ali"].id)],
            "topic": "Add people",
        },
    )
    cid = conv.json()["id"]

    r = await client.post(
        f"/conversations/{cid}/participants",
        headers=auth(ali),
        json={"user_id": str(reza.id)},
    )
    assert r.status_code == 200, r.text

    rows = (await client.get("/conversations", headers=auth(ali))).json()
    row = next(x for x in rows if x["id"] == cid)
    assert str(reza.id) in [str(p) for p in row["participant_ids"]]


@pytest.mark.asyncio
async def test_message_creates_notification_for_other_participants(
    client: AsyncClient, seeded, db: AsyncSession
):
    """پیام جدید برای بقیه شرکت‌کننده‌ها Notification با entity_type=conversation می‌سازد."""
    ali = await login(client, "ali@autoco.example")
    sara = seeded["sara"]

    conv = await client.post(
        "/conversations",
        headers=auth(ali),
        json={
            "channel": "WEB",
            "participant_ids": [str(seeded["ali"].id), str(seeded["sara"].id)],
            "topic": "Notify me",
        },
    )
    cid = conv.json()["id"]
    await client.post(
        f"/conversations/{cid}/messages",
        headers=auth(ali),
        json={"text": "این پیام برای سارا است", "channel": "WEB"},
    )

    await db.commit()
    rows = list(
        (
            await db.execute(
                select(Notification).where(
                    Notification.organization_id == seeded["org"].id,
                    Notification.entity_type == "conversation",
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows, "no conversation notification was created"
    target = [n for n in rows if n.user_id == sara.id]
    assert target, "sara did not get a notification"
    assert str(target[0].entity_id) == cid
    # فرستنده نباید برای پیام خودش اعلان بگیرد
    assert not [n for n in rows if n.user_id == seeded["ali"].id]


# ---------------------------------------------------------------------- archive


@pytest.mark.asyncio
async def test_unarchive_returns_conversation_to_board(client: AsyncClient, seeded):
    ali = await login(client, "ali@autoco.example")
    conv = await client.post(
        "/conversations",
        headers=auth(ali),
        json={
            "channel": "WEB",
            "participant_ids": [str(seeded["ali"].id), str(seeded["sara"].id)],
            "topic": "Archive me",
        },
    )
    cid = conv.json()["id"]
    sara = await login(client, "sara@autoco.example")
    await client.post(
        f"/conversations/{cid}/messages",
        headers=auth(sara),
        json={"text": "این را بعد از بازگردانی ببین", "channel": "WEB"},
    )

    arch = await client.post(f"/conversations/{cid}/archive", headers=auth(ali))
    assert arch.status_code == 200, arch.text

    active = (await client.get("/conversations", headers=auth(ali))).json()
    assert cid not in [r["id"] for r in active]

    archived = await client.get("/conversations?archived=true", headers=auth(ali))
    assert archived.status_code == 200
    assert cid in [r["id"] for r in archived.json()]

    un = await client.post(f"/conversations/{cid}/unarchive", headers=auth(ali))
    assert un.status_code == 200, un.text

    active = (await client.get("/conversations", headers=auth(ali))).json()
    assert cid in [r["id"] for r in active]

    rows = list((await client.get("/conversations", headers=auth(ali))).json())
    row = next(r for r in rows if r["id"] == cid)
    assert row["needs_reply"] is True


# ------------------------------------------------------------------- audit xlsx


@pytest.mark.asyncio
async def test_audit_xlsx_and_filters_require_admin(client: AsyncClient, seeded, db):
    ali = await login(client, "ali@autoco.example")
    # مدیر شعبه هم فیلتر می‌گیرد (event.read) ولی اکسل ادمین نیست
    assert (await client.get("/audit?action=auth.login", headers=auth(ali))).status_code == 200
    assert (await client.get("/audit.xlsx", headers=auth(ali))).status_code == 403

    token = await _org_admin(client, seeded, db)
    await client.get("/admin/overview", headers=auth(token))  # یک ردیف ممیزی بسازد

    filtered = await client.get("/audit?action=auth.login", headers=auth(token))
    assert filtered.status_code == 200
    assert all(row["action"] == "auth.login" for row in filtered.json())

    bad_day = await client.get("/audit?day=not-a-date", headers=auth(token))
    assert bad_day.status_code == 400

    xlsx = await client.get("/audit.xlsx", headers=auth(token))
    assert xlsx.status_code == 200
    assert xlsx.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert xlsx.content[:2] == b"PK"


@pytest.mark.asyncio
async def test_audit_export_is_audited(client: AsyncClient, seeded, db):
    token = await _org_admin(client, seeded, db)
    assert (await client.get("/audit.xlsx", headers=auth(token))).status_code == 200
    await db.commit()
    rows = list(
        (
            await db.execute(
                select(Notification).where(Notification.organization_id == seeded["org"].id)
            )
        )
        .scalars()
        .all()
    )
    assert rows is not None  # sanity: query works
    # لاگ ممیزیِ خروجی از طریق AuditLog ثبت می‌شود
    from app.models import AuditLog

    actions = set(
        (await db.execute(select(AuditLog.action))).scalars().all()
    )
    assert "report.export" in actions
