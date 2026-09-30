"""تست‌های مستقیم TelegramAdapter.handle_update — edited/callback/unsupported."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.telegram.adapter import TelegramAdapter
from app.integrations.telegram.callbacks import encode_callback
from app.integrations.telegram.client import FakeTelegramClient
from app.models.telegram import TelegramAccount
from app.services import WorkService


async def _link_account(db: AsyncSession, user, *, tg_user_id: int = 9001, chat_id: int = 1001) -> TelegramAccount:
    acc = TelegramAccount(
        organization_id=user.organization_id,
        user_id=user.id,
        provider="telegram",
        telegram_user_id=tg_user_id,
        telegram_chat_id=chat_id,
        telegram_username="ali_mgr",
    )
    db.add(acc)
    await db.flush()
    return acc


class TestHandleUpdateShapes:
    @pytest.mark.asyncio
    async def test_unsupported_update_type(self, db: AsyncSession, seeded):
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        result = await adapter.handle_update(
            {"update_id": 901, "channel_post": {"text": "ignored"}}
        )
        assert result.ok is True
        assert result.reply_text == ""
        assert client.sent == []

    @pytest.mark.asyncio
    async def test_edited_message_help(self, db: AsyncSession, seeded):
        await _link_account(db, seeded["ali"])
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        result = await adapter.handle_update(
            {
                "update_id": 902,
                "edited_message": {
                    "message_id": 11,
                    "text": "/help",
                    "chat": {"id": 1001},
                    "from": {"id": 9001, "username": "ali_mgr"},
                },
            }
        )
        assert result.ok is True
        assert result.reply_text
        assert len(client.sent) == 1

    @pytest.mark.asyncio
    async def test_duplicate_update_short_circuits(self, db: AsyncSession, seeded):
        await _link_account(db, seeded["ali"])
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        payload = {
            "update_id": 903,
            "message": {
                "message_id": 12,
                "text": "/help",
                "chat": {"id": 1001},
                "from": {"id": 9001, "username": "ali_mgr"},
            },
        }
        r1 = await adapter.handle_update(payload)
        assert r1.ok is True
        n = len(client.sent)
        r2 = await adapter.handle_update(payload)
        assert r2.ok is True
        assert r2.reply_text == ""
        assert len(client.sent) == n

    @pytest.mark.asyncio
    async def test_empty_text_message(self, db: AsyncSession, seeded):
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        result = await adapter.handle_update(
            {
                "update_id": 904,
                "message": {
                    "message_id": 13,
                    "text": "   ",
                    "chat": {"id": 1001},
                    "from": {"id": 9001},
                },
            }
        )
        assert result.ok is True
        assert len(client.sent) == 1


class TestCallbackDecodeFailures:
    @pytest.mark.asyncio
    async def test_invalid_callback_data(self, db: AsyncSession, seeded):
        await _link_account(db, seeded["ali"])
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        result = await adapter.handle_update(
            {
                "update_id": 910,
                "callback_query": {
                    "id": "cq-bad",
                    "data": "not-a-valid-signed-callback",
                    "from": {"id": 9001, "username": "ali_mgr"},
                    "message": {
                        "message_id": 20,
                        "chat": {"id": 1001},
                        "text": "x",
                    },
                },
            }
        )
        assert result.ok is False
        assert "Invalid" in (result.reply_text or "")
        assert any(a.get("id") == "cq-bad" for a in client.answered_callbacks)

    @pytest.mark.asyncio
    async def test_callback_unlinked_user(self, db: AsyncSession, seeded):
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        result = await adapter.handle_update(
            {
                "update_id": 911,
                "callback_query": {
                    "id": "cq-unlink",
                    "data": "whatever",
                    "from": {"id": 99999, "username": "stranger"},
                    "message": {"message_id": 21, "chat": {"id": 2002}, "text": "x"},
                },
            }
        )
        assert result.ok is False
        assert client.answered_callbacks


class TestLinkedCommands:
    @pytest.mark.asyncio
    async def test_start_welcome_unlinked(self, db: AsyncSession, seeded):
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        result = await adapter.handle_update(
            {
                "update_id": 920,
                "message": {
                    "message_id": 30,
                    "text": "/start",
                    "chat": {"id": 1001},
                    "from": {"id": 9001},
                },
            }
        )
        assert result.ok is True
        assert client.sent

    @pytest.mark.asyncio
    async def test_start_already_linked(self, db: AsyncSession, seeded):
        await _link_account(db, seeded["ali"])
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        result = await adapter.handle_update(
            {
                "update_id": 921,
                "message": {
                    "message_id": 31,
                    "text": "/start",
                    "chat": {"id": 1001},
                    "from": {"id": 9001, "username": "ali_mgr"},
                },
            }
        )
        assert result.ok is True
        assert client.sent

    @pytest.mark.asyncio
    async def test_link_usage(self, db: AsyncSession, seeded):
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        result = await adapter.handle_update(
            {
                "update_id": 922,
                "message": {
                    "message_id": 32,
                    "text": "/link",
                    "chat": {"id": 1001},
                    "from": {"id": 9001},
                },
            }
        )
        assert result.ok is True
        assert client.sent

    @pytest.mark.asyncio
    async def test_link_invalid_code(self, db: AsyncSession, seeded):
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        result = await adapter.handle_update(
            {
                "update_id": 923,
                "message": {
                    "message_id": 33,
                    "text": "/link deadbeef",
                    "chat": {"id": 1001},
                    "from": {"id": 9001},
                },
            }
        )
        assert result.ok is False

    @pytest.mark.asyncio
    async def test_link_by_code_and_status(self, db: AsyncSession, seeded):
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        code = await adapter.create_link_code(seeded["ali"])
        status0 = await adapter.get_status(seeded["ali"])
        assert status0["linked"] is False

        result = await adapter.handle_update(
            {
                "update_id": 924,
                "message": {
                    "message_id": 34,
                    "text": f"/link {code}",
                    "chat": {"id": 1001},
                    "from": {"id": 9001, "username": "ali_mgr"},
                },
            }
        )
        assert result.ok is True
        status1 = await adapter.get_status(seeded["ali"])
        assert status1["linked"] is True

    @pytest.mark.asyncio
    async def test_kar_and_payam_and_unlink(self, db: AsyncSession, seeded):
        await _link_account(db, seeded["ali"])
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)

        kar = await adapter.handle_update(
            {
                "update_id": 930,
                "message": {
                    "message_id": 40,
                    "text": "/kar",
                    "chat": {"id": 1001},
                    "from": {"id": 9001, "username": "ali_mgr"},
                },
            }
        )
        assert kar.ok is True

        payam = await adapter.handle_update(
            {
                "update_id": 931,
                "message": {
                    "message_id": 41,
                    "text": "/payam",
                    "chat": {"id": 1001},
                    "from": {"id": 9001, "username": "ali_mgr"},
                },
            }
        )
        assert payam.ok is True

        khodro = await adapter.handle_update(
            {
                "update_id": 932,
                "message": {
                    "message_id": 42,
                    "text": "/khodro camry",
                    "chat": {"id": 1001},
                    "from": {"id": 9001, "username": "ali_mgr"},
                },
            }
        )
        assert khodro.ok is True

        unlink = await adapter.handle_update(
            {
                "update_id": 933,
                "message": {
                    "message_id": 43,
                    "text": "/unlink",
                    "chat": {"id": 1001},
                    "from": {"id": 9001, "username": "ali_mgr"},
                },
            }
        )
        assert unlink.ok is True
        status = await adapter.get_status(seeded["ali"])
        assert status["linked"] is False

    @pytest.mark.asyncio
    async def test_update_prefs_and_not_linked_command(self, db: AsyncSession, seeded):
        acc = await _link_account(db, seeded["ali"])
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        updated = await adapter.update_prefs(
            seeded["ali"],
            notify_prefs={"task_assigned": False},
            quiet_start_hour=22,
            quiet_end_hour=8,
            digest_enabled=False,
        )
        assert updated is not None
        assert acc.quiet_start_hour == 22
        status = await adapter.get_status(seeded["ali"])
        assert status["notify_prefs"]["task_assigned"] is False

        # کاربر دیگر متصل نیست
        result = await adapter.handle_update(
            {
                "update_id": 940,
                "message": {
                    "message_id": 50,
                    "text": "/help",
                    "chat": {"id": 2002},
                    "from": {"id": 88888},
                },
            }
        )
        assert result.ok is False


class TestCallbackActions:
    @pytest.mark.asyncio
    async def test_done_task_not_found_and_hando(self, db: AsyncSession, seeded):
        await _link_account(db, seeded["ali"])
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        from uuid import uuid4

        bad = encode_callback("done", "task", uuid4())
        r = await adapter.handle_update(
            {
                "update_id": 950,
                "callback_query": {
                    "id": "cq-done-miss",
                    "data": bad,
                    "from": {"id": 9001},
                    "message": {"message_id": 60, "chat": {"id": 1001}, "text": "t"},
                },
            }
        )
        assert r.ok is False

        hando = encode_callback("hando", "task", uuid4())
        r2 = await adapter.handle_update(
            {
                "update_id": 951,
                "callback_query": {
                    "id": "cq-hando",
                    "data": hando,
                    "from": {"id": 9001},
                    "message": {"message_id": 61, "chat": {"id": 1001}, "text": "t"},
                },
            }
        )
        assert r2.ok is True

    @pytest.mark.asyncio
    async def test_complete_task_callback(self, db: AsyncSession, seeded):
        await _link_account(db, seeded["ali"])
        work = WorkService(db)
        wi = await work.create_work_item(
            organization_id=seeded["ali"].organization_id,
            title="TG WI",
            owner_id=seeded["ali"].id,
        )
        task = await work.create_task(
            organization_id=seeded["ali"].organization_id,
            title="TG Task",
            owner_id=seeded["ali"].id,
            work_item_id=wi.id,
            assignee_ids=[seeded["ali"].id],
        )
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        data = encode_callback("done", "task", task.id)
        r = await adapter.handle_update(
            {
                "update_id": 952,
                "callback_query": {
                    "id": "cq-done",
                    "data": data,
                    "from": {"id": 9001},
                    "message": {
                        "message_id": 62,
                        "chat": {"id": 1001},
                        "text": task.title,
                    },
                },
            }
        )
        assert r.ok is True
        await db.refresh(task)
        from app.models.enums import TaskStatus

        assert task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_free_text_assistant_mocked(self, db: AsyncSession, seeded, monkeypatch):
        await _link_account(db, seeded["ali"])
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)

        async def fake_ask(self, user, text, chat_id, reply_to, lang, stored_id):  # noqa: ANN001
            from app.integrations.telegram.adapter import AdapterResult

            await self.client.send_message(chat_id, "پاسخ آزمایشی")
            return AdapterResult(ok=True, reply_text="پاسخ آزمایشی", stored_message_id=stored_id)

        monkeypatch.setattr(TelegramAdapter, "_ask_assistant", fake_ask)
        r = await adapter.handle_update(
            {
                "update_id": 960,
                "message": {
                    "message_id": 70,
                    "text": "قیمت کمری چقدر است؟",
                    "chat": {"id": 1001},
                    "from": {"id": 9001, "username": "ali_mgr"},
                },
            }
        )
        assert r.ok is True
        assert "آزمایشی" in (r.reply_text or "")

    @pytest.mark.asyncio
    async def test_kar_lists_open_tasks(self, db: AsyncSession, seeded):
        await _link_account(db, seeded["ali"])
        work = WorkService(db)
        wi = await work.create_work_item(
            organization_id=seeded["ali"].organization_id,
            title="List WI",
            owner_id=seeded["ali"].id,
        )
        await work.create_task(
            organization_id=seeded["ali"].organization_id,
            title="Open for /kar",
            owner_id=seeded["ali"].id,
            work_item_id=wi.id,
            assignee_ids=[seeded["ali"].id],
        )
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        r = await adapter.handle_update(
            {
                "update_id": 970,
                "message": {
                    "message_id": 80,
                    "text": "/kar",
                    "chat": {"id": 1001},
                    "from": {"id": 9001, "username": "ali_mgr"},
                },
            }
        )
        assert r.ok is True
        assert any("Open for /kar" in (m.text or "") for m in client.sent)

    @pytest.mark.asyncio
    async def test_payam_waiting_and_khodro_empty(self, db: AsyncSession, seeded):
        from app.models.enums import Channel as Chan
        from app.services import CommunicationService

        await _link_account(db, seeded["ali"])
        # conversation where reza sent last message → ali is waiting
        comms = CommunicationService(db)
        conv = await comms.create_conversation(
            organization_id=seeded["ali"].organization_id,
            channel=Chan.WEB,
            participant_ids=[seeded["ali"].id, seeded["reza"].id],
            topic="wait-me",
        )
        await comms.post_message(
            organization_id=seeded["ali"].organization_id,
            conversation_id=conv.id,
            sender_id=seeded["reza"].id,
            text="جواب بده",
            channel=Chan.WEB,
        )
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        r = await adapter.handle_update(
            {
                "update_id": 971,
                "message": {
                    "message_id": 81,
                    "text": "/payam",
                    "chat": {"id": 1001},
                    "from": {"id": 9001, "username": "ali_mgr"},
                },
            }
        )
        assert r.ok is True
        assert any("wait-me" in (m.text or "") or "جواب" in (m.text or "") for m in client.sent)

        client.sent.clear()
        r2 = await adapter.handle_update(
            {
                "update_id": 972,
                "message": {
                    "message_id": 82,
                    "text": "/khodro",
                    "chat": {"id": 1001},
                    "from": {"id": 9001, "username": "ali_mgr"},
                },
            }
        )
        assert r2.ok is True
        assert client.sent

    @pytest.mark.asyncio
    async def test_show_callback_and_conf_cancel(self, db: AsyncSession, seeded):
        await _link_account(db, seeded["ali"])
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        from uuid import uuid4

        show = encode_callback("show", "task", uuid4())
        r = await adapter.handle_update(
            {
                "update_id": 980,
                "callback_query": {
                    "id": "cq-show",
                    "data": show,
                    "from": {"id": 9001},
                    "message": {"message_id": 90, "chat": {"id": 1001}, "text": "x"},
                },
            }
        )
        assert r.ok is True

        # cancel confirm with no pending row
        no = encode_callback("no", "conf", uuid4())
        r2 = await adapter.handle_update(
            {
                "update_id": 981,
                "callback_query": {
                    "id": "cq-no",
                    "data": no,
                    "from": {"id": 9001},
                    "message": {"message_id": 91, "chat": {"id": 1001}, "text": "x"},
                },
            }
        )
        assert r2.ok is True

    @pytest.mark.asyncio
    async def test_route_reply_to_outbox_conversation(self, db: AsyncSession, seeded):
        from app.models.enums import Channel as Chan
        from app.models.telegram import TelegramOutbox
        from app.services import CommunicationService

        await _link_account(db, seeded["ali"])
        comms = CommunicationService(db)
        conv = await comms.create_conversation(
            organization_id=seeded["ali"].organization_id,
            channel=Chan.TELEGRAM,
            participant_ids=[seeded["ali"].id, seeded["reza"].id],
            topic="routed",
        )
        db.add(
            TelegramOutbox(
                organization_id=seeded["ali"].organization_id,
                user_id=seeded["ali"].id,
                provider="telegram",
                event_type="message",
                text="notif",
                status="sent",
                telegram_message_id=555,
                conversation_id=conv.id,
            )
        )
        await db.flush()
        client = FakeTelegramClient()
        adapter = TelegramAdapter(db, client=client)
        r = await adapter.handle_update(
            {
                "update_id": 990,
                "message": {
                    "message_id": 99,
                    "text": "جواب از تلگرام",
                    "chat": {"id": 1001},
                    "from": {"id": 9001, "username": "ali_mgr"},
                    "reply_to_message": {"message_id": 555},
                },
            }
        )
        assert r.ok is True
        assert "ارسال" in (r.reply_text or "") or "Sent" in (r.reply_text or "")
