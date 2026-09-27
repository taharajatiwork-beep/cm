"""Background loops: outbox dispatcher, Telegram long-polling, SLA + morning digest."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.timeutil import utc_now
from app.integrations.telegram.adapter import TelegramAdapter
from app.integrations.telegram.client import HttpTelegramClient, TelegramClient
from app.integrations.telegram.messages import BOT_COMMANDS, digest_text, btn_show
from app.integrations.telegram.callbacks import encode_callback
from app.integrations.telegram.outbox import dispatch_pending, enqueue_telegram, inline_keyboard
from app.models import Task, User
from app.models.enums import TaskStatus
from app.models.telegram import TelegramAccount
from app.services import SlaService, WorkService

log = get_logger(__name__)

_tasks: list[asyncio.Task[Any]] = []
_poll_offsets: dict[str, int] = {}
_last_digest_date: str | None = None


def build_clients() -> dict[str, TelegramClient]:
    settings = get_settings()
    clients: dict[str, TelegramClient] = {}
    if settings.telegram_bot_token and settings.telegram_mode != "off":
        clients["telegram"] = HttpTelegramClient(
            token=settings.telegram_bot_token,
            api_base=settings.telegram_api_base,
        )
    if settings.bale_bot_token and settings.bale_mode != "off":
        clients["bale"] = HttpTelegramClient(
            token=settings.bale_bot_token,
            api_base=settings.bale_api_base,
        )
    return clients


async def setup_telegram(clients: dict[str, TelegramClient]) -> None:
    settings = get_settings()
    if "telegram" in clients:
        client = clients["telegram"]
        try:
            await client.set_my_commands(BOT_COMMANDS)
            if settings.telegram_mode == "webhook" and settings.telegram_webhook_url:
                await client.set_webhook(
                    settings.telegram_webhook_url,
                    secret_token=settings.telegram_webhook_secret or None,
                )
                log.info("telegram_webhook_set", url=settings.telegram_webhook_url)
            elif settings.telegram_mode == "polling":
                await client.delete_webhook()
                log.info("telegram_polling_mode")
        except Exception as e:
            log.warning("telegram_setup_failed", error=str(e))
    if "bale" in clients:
        client = clients["bale"]
        try:
            await client.set_my_commands(BOT_COMMANDS)
            if settings.bale_mode == "webhook" and settings.bale_webhook_url:
                await client.set_webhook(
                    settings.bale_webhook_url,
                    secret_token=settings.bale_webhook_secret or None,
                )
            elif settings.bale_mode == "polling":
                await client.delete_webhook()
        except Exception as e:
            log.warning("bale_setup_failed", error=str(e))


async def _outbox_loop(session_factory: async_sessionmaker[AsyncSession]) -> None:
    settings = get_settings()
    while True:
        try:
            clients = build_clients()
            if clients:
                async with session_factory() as db:
                    n = await dispatch_pending(db, clients)
                    if n:
                        await db.commit()
                        log.info("telegram_outbox_sent", count=n)
                    else:
                        await db.rollback()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("telegram_outbox_loop_error", error=str(e))
        await asyncio.sleep(settings.telegram_outbox_poll_seconds)


async def _poll_provider(
    provider: str,
    client: TelegramClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    offset = _poll_offsets.get(provider, 0)
    while True:
        try:
            updates = await client.get_updates(offset=offset or None, timeout=25)
            for upd in updates:
                uid = int(upd.get("update_id", 0))
                offset = uid + 1
                _poll_offsets[provider] = offset
                async with session_factory() as db:
                    try:
                        adapter = TelegramAdapter(db, client=client, provider=provider)
                        await adapter.handle_update(upd)
                        await db.commit()
                    except Exception as e:
                        await db.rollback()
                        log.warning("telegram_poll_handle_error", provider=provider, error=str(e))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("telegram_poll_error", provider=provider, error=str(e))
            await asyncio.sleep(3)


async def _sla_and_digest_loop(session_factory: async_sessionmaker[AsyncSession]) -> None:
    global _last_digest_date
    settings = get_settings()
    while True:
        try:
            async with session_factory() as db:
                # Evaluate open tasks with active SLA
                tasks = (
                    await db.execute(
                        select(Task).where(Task.status != TaskStatus.COMPLETED).limit(200)
                    )
                ).scalars().all()
                sla = SlaService(db)
                for t in tasks:
                    try:
                        await sla.evaluate_task(t.id)
                    except Exception:
                        continue
                await db.commit()

            # Morning digest once per UTC day at configured hour
            now = utc_now()
            day_key = now.date().isoformat()
            if now.hour == settings.telegram_digest_hour_utc and _last_digest_date != day_key:
                async with session_factory() as db:
                    await _send_digests(db)
                    await db.commit()
                _last_digest_date = day_key
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("telegram_sla_loop_error", error=str(e))
        await asyncio.sleep(settings.telegram_sla_poll_seconds)


async def _send_digests(db: AsyncSession) -> None:
    accounts = (
        await db.execute(
            select(TelegramAccount).where(
                TelegramAccount.disabled_at.is_(None),
                TelegramAccount.telegram_chat_id.is_not(None),
                TelegramAccount.digest_enabled.is_(True),
            )
        )
    ).scalars().all()
    work = WorkService(db)
    for account in accounts:
        user = await db.get(User, account.user_id)
        if not user:
            continue
        tasks = await work.list_tasks(
            user.organization_id, assignee_id=user.id, limit=100
        )
        open_tasks = [t for t in tasks if t.status != TaskStatus.COMPLETED]
        late = 0
        for t in open_tasks:
            if t.deadline and t.deadline < utc_now() and t.status != TaskStatus.COMPLETED:
                late += 1
        # Waiting messages approximate: skip heavy scan — use 0 if costly; light scan
        waiting = 0
        text = digest_text(len(open_tasks), late, waiting, lang="fa")
        await enqueue_telegram(
            db,
            organization_id=user.organization_id,
            user_id=user.id,
            event_type="digest",
            text=text,
            buttons=[
                [
                    {
                        "text": btn_show(lang="fa"),
                        "callback_data": encode_callback("show", "menu", user.id),
                    }
                ]
            ],
            provider=account.provider,
        )


def start_background(session_factory: async_sessionmaker[AsyncSession]) -> list[asyncio.Task[Any]]:
    settings = get_settings()
    clients = build_clients()
    started: list[asyncio.Task[Any]] = []

    async def _boot():
        await setup_telegram(clients)

    started.append(asyncio.create_task(_boot(), name="telegram-setup"))

    if clients:
        started.append(
            asyncio.create_task(_outbox_loop(session_factory), name="telegram-outbox")
        )
        started.append(
            asyncio.create_task(_sla_and_digest_loop(session_factory), name="telegram-sla")
        )

    if settings.telegram_mode == "polling" and "telegram" in clients:
        started.append(
            asyncio.create_task(
                _poll_provider("telegram", clients["telegram"], session_factory),
                name="telegram-poll",
            )
        )
    if settings.bale_mode == "polling" and "bale" in clients:
        started.append(
            asyncio.create_task(
                _poll_provider("bale", clients["bale"], session_factory),
                name="bale-poll",
            )
        )

    global _tasks
    _tasks = started
    log.info("telegram_background_started", tasks=[t.get_name() for t in started])
    return started


async def stop_background() -> None:
    global _tasks
    for t in _tasks:
        t.cancel()
    for t in _tasks:
        try:
            await t
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
    _tasks = []
