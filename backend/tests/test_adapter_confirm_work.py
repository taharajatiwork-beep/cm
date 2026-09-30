"""پوشش مسیر confirm create-work در TelegramAdapter."""

import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utc_now
from app.integrations.telegram.adapter import TelegramAdapter
from app.integrations.telegram.callbacks import encode_callback
from app.integrations.telegram.client import FakeTelegramClient
from app.models.inventory import Vehicle
from app.models.telegram import TelegramAccount, TelegramPendingConfirm


@pytest.mark.asyncio
async def test_offer_confirm_and_execute_create_work(db: AsyncSession, seeded):
    ali, reza = seeded["ali"], seeded["reza"]
    vehicle = Vehicle(
        organization_id=ali.organization_id,
        branch_id=seeded["branch"].id,
        brand="Toyota",
        model="Camry",
        year=2020,
        stock_number="ST-99",
        vin="JTDBR32E720000001",
    )
    db.add(vehicle)
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

    client = FakeTelegramClient()
    adapter = TelegramAdapter(db, client=client)

    resolution = SimpleNamespace(
        vehicles=[vehicle],
        users=[SimpleNamespace(user=reza, matched_token="رضا")],
        ambiguous=False,
        intent="create_work",
        clarification=None,
    )
    stored_id = uuid4()
    offer = await adapter._offer_create_work(
        ali, "بفروش به رضا", resolution, 1001, None, "fa", stored_id
    )
    assert offer.ok is True
    assert client.sent

    pending = await db.scalar(
        select(TelegramPendingConfirm).where(TelegramPendingConfirm.user_id == ali.id)
    )
    assert pending is not None

    data = encode_callback("ok", "conf", pending.id)
    result = await adapter.handle_update(
        {
            "update_id": 1100,
            "callback_query": {
                "id": "cq-ok",
                "data": data,
                "from": {"id": 9001},
                "message": {"message_id": 120, "chat": {"id": 1001}, "text": "preview"},
            },
        }
    )
    assert result.ok is True

    # cancel path with real pending
    pending2 = TelegramPendingConfirm(
        organization_id=ali.organization_id,
        user_id=ali.id,
        provider="telegram",
        kind="create_work",
        payload_json=json.dumps({"title": "x"}),
        expires_at=utc_now() + timedelta(minutes=10),
    )
    db.add(pending2)
    await db.flush()
    no = encode_callback("no", "conf", pending2.id)
    cancelled = await adapter.handle_update(
        {
            "update_id": 1101,
            "callback_query": {
                "id": "cq-cancel",
                "data": no,
                "from": {"id": 9001},
                "message": {"message_id": 121, "chat": {"id": 1001}, "text": "p"},
            },
        }
    )
    assert cancelled.ok is True


@pytest.mark.asyncio
async def test_ask_assistant_rate_limit_and_no_rag(db: AsyncSession, seeded, monkeypatch):
    ali = seeded["ali"]
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
    client = FakeTelegramClient()
    adapter = TelegramAdapter(db, client=client)
    monkeypatch.setattr(adapter, "_rate_ok", lambda _uid: False)
    from uuid import uuid4

    r = await adapter._ask_assistant(ali, "سلام", 1001, None, "fa", uuid4())
    assert r.ok is True
    assert client.sent
