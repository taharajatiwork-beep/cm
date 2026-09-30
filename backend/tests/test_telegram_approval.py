"""Telegram approval decisions: inline «تأیید»/«رد» buttons over the signed callback."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import telegram as telegram_routes
from app.integrations.telegram.callbacks import encode_approval_callback, verify_callback
from app.integrations.telegram.client import FakeTelegramClient
from app.integrations.telegram.outbox import dispatch_pending
from app.models.telegram import TelegramAccount, TelegramOutbox
from app.services.enterprise_ops import EnterpriseService, notify_current_approver
from tests.conftest import auth, login

WEBHOOK_SECRET = "dev-telegram-webhook-secret"


def tg_headers() -> dict:
    return {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}


@pytest.fixture
def fake_tg():
    client = FakeTelegramClient()
    telegram_routes.set_test_telegram_client(client)
    yield client
    telegram_routes.set_test_telegram_client(None)


async def _link(client: AsyncClient, email: str, tg_user_id: int, chat_id: int, update_id: int) -> None:
    token = await login(client, email)
    code_resp = await client.post("/telegram/link-code", headers=auth(token))
    assert code_resp.status_code == 200, code_resp.text
    code = code_resp.json()["link_code"]
    r = await client.post(
        "/telegram/webhook",
        headers=tg_headers(),
        json={
            "update_id": update_id,
            "message": {
                "message_id": 1000 + update_id,
                "text": f"/link {code}",
                "chat": {"id": chat_id},
                "from": {"id": tg_user_id, "username": email.split("@")[0]},
            },
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


async def _callback(client: AsyncClient, data: str, tg_user_id: int, chat_id: int, update_id: int) -> dict:
    r = await client.post(
        "/telegram/webhook",
        headers=tg_headers(),
        json={
            "update_id": update_id,
            "callback_query": {
                "id": f"cq-{update_id}",
                "data": data,
                "from": {"id": tg_user_id, "username": "approver"},
                "message": {
                    "message_id": 500 + update_id,
                    "chat": {"id": chat_id},
                    "text": "درخواست تأیید جدید",
                },
            },
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _approval_status(client: AsyncClient, email: str, request_id: str) -> str:
    token = await login(client, email)
    r = await client.get("/approvals", headers=auth(token))
    assert r.status_code == 200, r.text
    for row in r.json():
        if row["id"] == request_id:
            return row["status"]
    raise AssertionError("approval not found")


@pytest.mark.asyncio
async def test_two_step_approval_from_telegram_buttons(
    client: AsyncClient, seeded, fake_tg: FakeTelegramClient
):
    """First button keeps status pending; the second one approves."""
    await _link(client, "reza@autoco.example", 9002, 1002, update_id=1)
    await _link(client, "ali@autoco.example", 9001, 1001, update_id=2)
    await _link(client, "sara@autoco.example", 9003, 1003, update_id=3)

    requester = await login(client, "reza@autoco.example")
    created = await client.post(
        "/approvals",
        headers=auth(requester),
        json={
            "kind": "discount",
            "title": "تخفیف ۱۰ درصد",
            "payload": {"percent": 10},
            # درخواست‌دهنده (reza) نباید تأییدکننده باشد — خود-تأییدی ممنوع
            "approver_ids": [str(seeded["ali"].id), str(seeded["sara"].id)],
        },
    )
    assert created.status_code == 200, created.text
    request_id = created.json()["id"]

    approve = encode_approval_callback("approve", request_id)
    assert verify_callback(approve) is not None

    first = await _callback(client, approve, 9001, 1001, update_id=11)
    assert first["ok"] is True
    assert await _approval_status(client, "reza@autoco.example", request_id) == "pending"

    second = await _callback(client, approve, 9003, 1003, update_id=12)
    assert second["ok"] is True
    assert "تأیید" in second["reply_text"]
    assert await _approval_status(client, "reza@autoco.example", request_id) == "approved"


@pytest.mark.asyncio
async def test_button_by_unrelated_user_is_refused(
    client: AsyncClient, seeded, fake_tg: FakeTelegramClient
):
    """A linked user who is not the current approver gets a Persian refusal."""
    await _link(client, "reza@autoco.example", 9002, 1002, update_id=21)
    await _link(client, "viewer@autoco.example", 9009, 1009, update_id=22)

    requester = await login(client, "reza@autoco.example")
    created = await client.post(
        "/approvals",
        headers=auth(requester),
        json={
            "kind": "discount",
            "title": "درخواست دسترسی",
            "approver_ids": [str(seeded["ali"].id)],
        },
    )
    assert created.status_code == 200, created.text
    request_id = created.json()["id"]

    approve = encode_approval_callback("approve", request_id)
    refused = await _callback(client, approve, 9009, 1009, update_id=23)
    assert refused["ok"] is False
    assert "شما تأییدکنندهٔ این مرحله نیستید" in refused["reply_text"]
    assert await _approval_status(client, "reza@autoco.example", request_id) == "pending"


@pytest.mark.asyncio
async def test_tampered_callback_is_rejected(
    client: AsyncClient, seeded, fake_tg: FakeTelegramClient
):
    await _link(client, "reza@autoco.example", 9002, 1002, update_id=31)
    await _link(client, "ali@autoco.example", 9001, 1001, update_id=33)

    requester = await login(client, "reza@autoco.example")
    created = await client.post(
        "/approvals",
        headers=auth(requester),
        json={
            "kind": "discount",
            "title": "درخواست جعلی",
            "approver_ids": [str(seeded["ali"].id)],
        },
    )
    assert created.status_code == 200, created.text
    request_id = created.json()["id"]

    good = encode_approval_callback("approve", request_id)
    tampered = good[:-1] + ("0" if good[-1] != "0" else "1")
    assert verify_callback(tampered) is None

    result = await _callback(client, tampered, 9002, 1002, update_id=32)
    assert result["ok"] is False
    assert await _approval_status(client, "reza@autoco.example", request_id) == "pending"


@pytest.mark.asyncio
async def test_request_sends_buttons_through_outbox(
    db: AsyncSession, seeded, fake_tg: FakeTelegramClient
):
    """Requester with linked Telegram → current approver gets inline buttons via outbox."""
    reza, ali = seeded["reza"], seeded["ali"]
    db.add(
        TelegramAccount(
            organization_id=reza.organization_id,
            user_id=reza.id,
            provider="telegram",
            telegram_user_id=9002,
            telegram_chat_id=1002,
        )
    )
    db.add(
        TelegramAccount(
            organization_id=ali.organization_id,
            user_id=ali.id,
            provider="telegram",
            telegram_user_id=9001,
            telegram_chat_id=1001,
        )
    )
    await db.flush()

    approval = await EnterpriseService(db).request_approval(
        organization_id=reza.organization_id,
        requester_id=reza.id,
        kind="discount",
        title="تخفیف ۱۰ درصد",
        payload={"percent": 10},
        approver_ids=[ali.id],
    )
    await notify_current_approver(db, approval)

    outbox = list(
        (await db.execute(select(TelegramOutbox).where(TelegramOutbox.user_id == ali.id))).scalars()
    )
    assert len(outbox) == 1
    row = outbox[0]
    assert row.event_type == "approval"
    assert "تأیید" in (row.text or "")
    assert row.buttons_json and "تأیید" in row.buttons_json and "رد" in row.buttons_json

    # Buttons ride the signed callback format.
    import json

    buttons = json.loads(row.buttons_json or "[]")
    datas = [b["callback_data"] for b in buttons[0]]
    first = verify_callback(datas[0])
    second = verify_callback(datas[1])
    assert first is not None and first[0] == "approve" and first[1] == "appr"
    assert second is not None and second[0] == "reject"

    sent = await dispatch_pending(db, {"telegram": fake_tg})
    assert sent == 1
    assert fake_tg.sent[-1].reply_markup is not None
    labels = [b["text"] for r in fake_tg.sent[-1].reply_markup["inline_keyboard"] for b in r]
    assert "تأیید" in labels and "رد" in labels


@pytest.mark.asyncio
async def test_unlinked_requester_sends_no_outbox(db: AsyncSession, seeded):
    """No Telegram link on the requester → nothing is queued, no direct send."""
    ali = seeded["ali"]
    approval = await EnterpriseService(db).request_approval(
        organization_id=ali.organization_id,
        requester_id=ali.id,
        kind="discount",
        title="بدون تلگرام",
        payload={},
        approver_ids=[seeded["reza"].id],
    )
    await notify_current_approver(db, approval)
    rows = list((await db.execute(select(TelegramOutbox))).scalars())
    assert rows == []
