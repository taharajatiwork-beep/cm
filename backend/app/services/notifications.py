from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Notification
from app.models.enums import NotificationChannel

_log = get_logger(__name__)

async def notify(
    db: AsyncSession,
    *,
    organization_id: UUID,
    user_id: UUID,
    title: str,
    body: str,
    channel: NotificationChannel = NotificationChannel.WEB,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
) -> Notification:
    n = Notification(
        organization_id=organization_id,
        user_id=user_id,
        channel=channel,
        title=title,
        body=body,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(n)
    await db.flush()

    # Mirror to Telegram/Bale outbox when the user has linked an account
    try:
        from app.core.config import get_settings
        from app.integrations.telegram.callbacks import encode_callback
        from app.integrations.telegram.messages import (
            btn_done,
            btn_open,
            btn_reply,
            notify_branch,
            notify_message,
            notify_sla,
            notify_task_assigned,
            notify_task_done,
        )
        from app.integrations.telegram.outbox import classify_notify_event, enqueue_telegram

        event = classify_notify_event(title=title, entity_type=entity_type)
        lang = "fa"
        settings = get_settings()
        web = settings.web_app_base_url.rstrip("/")

        if event == "task_assigned":
            text = notify_task_assigned(body or title, lang=lang)
            buttons = None
            if entity_id:
                buttons = [
                    [
                        {"text": btn_done(lang=lang), "callback_data": encode_callback("done", "task", entity_id)},
                        {"text": btn_open(lang=lang), "url": f"{web}/my-work"},
                    ]
                ]
        elif event == "task_done":
            text = notify_task_done(body or title, lang=lang)
            buttons = [[{"text": btn_open(lang=lang), "url": f"{web}/my-work"}]]
        elif event == "sla":
            late = "breach" in title.lower() or "escalat" in title.lower() or "گذشت" in title or "دیر" in title
            text = notify_sla(body or title, late=late, lang=lang)
            buttons = None
            if entity_type == "task" and entity_id:
                buttons = [
                    [
                        {"text": btn_done(lang=lang), "callback_data": encode_callback("done", "task", entity_id)},
                        {"text": btn_open(lang=lang), "url": f"{web}/my-work"},
                    ]
                ]
        elif event == "branch":
            text = notify_branch(body or title, lang=lang)
            buttons = [[{"text": btn_open(lang=lang), "url": f"{web}/cases"}]]
        elif event == "message":
            text = notify_message(title, (body or "")[:200], "", lang=lang)
            buttons = [
                [
                    {"text": btn_reply(lang=lang), "url": f"{web}/communication"},
                    {"text": btn_open(lang=lang), "url": f"{web}/communication"},
                ]
            ]
        else:
            text = f"{title}\n{body}" if body else title
            buttons = [[{"text": btn_open(lang=lang), "url": f"{web}/"}]]

        await enqueue_telegram(
            db,
            organization_id=organization_id,
            user_id=user_id,
            event_type=event,
            text=text,
            buttons=buttons,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    except Exception as exc:  # noqa: BLE001
        # Never break the core write path because of Telegram
        _log.warning("telegram_enqueue_failed", event=event, error=str(exc))

    return n
