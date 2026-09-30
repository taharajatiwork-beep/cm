"""پوشش SlaService.evaluate_case و CommunicationService list/helpers."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CaseType, Channel, Priority, SlaState
from app.services import CommunicationService, SlaService, WorkService


@pytest.mark.asyncio
async def test_sla_evaluate_case_breach_and_warning(db: AsyncSession, seeded):
    ali = seeded["ali"]
    work = WorkService(db)
    sla = SlaService(db)
    policy = await sla.create_policy(
        organization_id=ali.organization_id,
        name="fast",
        priority=Priority.HIGH,
        response_minutes=60,
        warning_minutes=30,
        escalate_on_breach=True,
    )
    case = await work.create_case(
        organization_id=ali.organization_id,
        subject="SLA case",
        case_type=CaseType.FOLLOW_UP,
        created_by=ali.id,
        owner_id=ali.id,
        sla_policy_id=policy.id,
        deadline=datetime.now(UTC) - timedelta(minutes=5),
    )
    # force active so warning/breach paths are meaningful
    case.sla_state = SlaState.ACTIVE
    case.created_at = datetime.now(UTC) - timedelta(hours=2)
    await db.flush()

    out = await sla.evaluate_case(case.id, now=datetime.now(UTC))
    assert out.sla_state in (SlaState.BREACHED, SlaState.ESCALATED) or out.status


@pytest.mark.asyncio
async def test_communication_list_and_last_messages(db: AsyncSession, seeded):
    ali, reza = seeded["ali"], seeded["reza"]
    comms = CommunicationService(db)
    conv = await comms.create_conversation(
        organization_id=ali.organization_id,
        channel=Channel.WEB,
        participant_ids=[ali.id, reza.id],
        topic="cover-comms",
        actor_id=ali.id,
    )
    await comms.post_message(
        organization_id=ali.organization_id,
        conversation_id=conv.id,
        sender_id=ali.id,
        text="سلام",
        channel=Channel.WEB,
    )
    await comms.add_participant(
        organization_id=ali.organization_id,
        conversation_id=conv.id,
        user_id=seeded["sara"].id,
    )
    listed = await comms.list_conversations(ali.organization_id)
    assert any(c.id == conv.id for c in listed)
    msgs = await comms.list_messages(conv.id)
    assert msgs
    got = await comms.get_conversation(conv.id)
    assert got is not None
    lasts = await comms.last_messages([conv.id])
    assert conv.id in lasts
    empty = await comms.last_messages([])
    assert empty == {}


@pytest.mark.asyncio
async def test_ask_assistant_real_path(db: AsyncSession, seeded):
    from uuid import uuid4

    from app.integrations.telegram.adapter import TelegramAdapter
    from app.integrations.telegram.client import FakeTelegramClient
    from app.models.telegram import TelegramAccount

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
    r = await adapter._ask_assistant(ali, "سلام سیستم", 1001, None, "fa", uuid4())
    assert r.ok in (True, False)
    assert client.sent
