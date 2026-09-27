"""Unit tests for Telegram outbox dispatch, quiet hours, and callbacks."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utc_now
from app.integrations.telegram.callbacks import encode_callback, verify_callback
from app.integrations.telegram.client import FakeTelegramClient
from app.integrations.telegram.outbox import (
    dispatch_pending,
    enqueue_telegram,
    is_quiet_now,
    parse_prefs,
)
from app.models.telegram import TelegramAccount


def test_callback_roundtrip():
    eid = uuid4()
    data = encode_callback("done", "task", eid)
    parsed = verify_callback(data)
    assert parsed is not None
    action, et, short = parsed
    assert action == "done"
    assert et == "task"
    assert str(eid).replace("-", "").startswith(short)
    assert verify_callback(data[:-1] + ("0" if data[-1] != "0" else "1")) is None


def test_parse_prefs_defaults():
    prefs = parse_prefs(None)
    assert prefs["task_assigned"] is True
    prefs2 = parse_prefs('{"task_assigned": false, "message": true}')
    assert prefs2["task_assigned"] is False
    assert prefs2["message"] is True


def test_quiet_hours_wrap():
    acc = TelegramAccount(
        organization_id=uuid4(),
        user_id=uuid4(),
        quiet_start_hour=22,
        quiet_end_hour=8,
    )
    noon = utc_now().replace(hour=12, minute=0, second=0, microsecond=0)
    night = utc_now().replace(hour=23, minute=0, second=0, microsecond=0)
    morning = utc_now().replace(hour=7, minute=0, second=0, microsecond=0)
    assert is_quiet_now(acc, noon) is False
    assert is_quiet_now(acc, night) is True
    assert is_quiet_now(acc, morning) is True


@pytest.mark.asyncio
async def test_outbox_429_retry(db: AsyncSession, seeded):
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
    row = await enqueue_telegram(
        db,
        organization_id=ali.organization_id,
        user_id=ali.id,
        event_type="task_assigned",
        text="hello",
    )
    assert row is not None
    client = FakeTelegramClient()
    client.fail_status = 429
    client.retry_after = 5
    n = await dispatch_pending(db, {"telegram": client})
    assert n == 0
    await db.refresh(row)
    assert row.status == "pending"
    assert row.attempts == 1
    assert row.next_attempt_at is not None


@pytest.mark.asyncio
async def test_outbox_403_disables(db: AsyncSession, seeded):
    ali = seeded["ali"]
    account = TelegramAccount(
        organization_id=ali.organization_id,
        user_id=ali.id,
        provider="telegram",
        telegram_user_id=9001,
        telegram_chat_id=1001,
    )
    db.add(account)
    await db.flush()
    row = await enqueue_telegram(
        db,
        organization_id=ali.organization_id,
        user_id=ali.id,
        event_type="task_assigned",
        text="hello",
    )
    client = FakeTelegramClient()
    client.fail_status = 403
    n = await dispatch_pending(db, {"telegram": client})
    assert n == 0
    await db.refresh(row)
    await db.refresh(account)
    assert row.status == "failed"
    assert account.disabled_at is not None


@pytest.mark.asyncio
async def test_outbox_send_ok(db: AsyncSession, seeded):
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
    row = await enqueue_telegram(
        db,
        organization_id=ali.organization_id,
        user_id=ali.id,
        event_type="task_assigned",
        text="کار جدید",
        buttons=[[{"text": "Done", "callback_data": "x"}]],
    )
    client = FakeTelegramClient()
    n = await dispatch_pending(db, {"telegram": client})
    assert n == 1
    await db.refresh(row)
    assert row.status == "sent"
    assert row.telegram_message_id is not None
    assert len(client.sent) == 1
    assert client.sent[0].reply_markup is not None
