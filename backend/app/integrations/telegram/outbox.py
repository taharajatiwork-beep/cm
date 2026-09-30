"""Telegram notification outbox — enqueue in-transaction, dispatch asynchronously."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.timeutil import as_utc, utc_now
from app.integrations.telegram.client import TelegramApiError, TelegramClient
from app.models.telegram import TelegramAccount, TelegramOutbox

log = get_logger(__name__)

DEFAULT_PREFS = {
    "task_assigned": True,
    "message": True,
    "sla": True,
    "task_done": True,
    "branch": True,
}

# Map notify entity/title heuristics → preference key
EVENT_PREF = {
    "task_assigned": "task_assigned",
    "task_done": "task_done",
    "message": "message",
    "sla": "sla",
    "branch": "branch",
    "digest": "task_assigned",  # digest always if digest_enabled
}


def parse_prefs(raw: str | None) -> dict[str, bool]:
    prefs = dict(DEFAULT_PREFS)
    if not raw:
        return prefs
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            for k, v in data.items():
                if k in prefs:
                    prefs[k] = bool(v)
    except (ValueError, TypeError):
        log.warning("telegram_prefs_unparseable")
    return prefs


def is_quiet_now(account: TelegramAccount, now=None) -> bool:
    now = as_utc(now or utc_now())
    start = account.quiet_start_hour
    end = account.quiet_end_hour
    if start is None or end is None:
        return False
    hour = now.hour
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    # wraps midnight e.g. 22 → 8
    return hour >= start or hour < end


def inline_keyboard(rows: list[list[dict[str, str]]]) -> dict[str, Any]:
    return {"inline_keyboard": rows}


async def get_active_account(
    db: AsyncSession,
    user_id: UUID,
    *,
    provider: str = "telegram",
) -> TelegramAccount | None:
    account = await db.scalar(
        select(TelegramAccount).where(
            TelegramAccount.user_id == user_id,
            TelegramAccount.provider == provider,
            TelegramAccount.disabled_at.is_(None),
            TelegramAccount.telegram_chat_id.is_not(None),
        )
    )
    return account


async def enqueue_telegram(
    db: AsyncSession,
    *,
    organization_id: UUID,
    user_id: UUID,
    event_type: str,
    text: str,
    buttons: list[list[dict[str, str]]] | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    conversation_id: UUID | None = None,
    provider: str = "telegram",
) -> TelegramOutbox | None:
    """Create an outbox row if the user has Telegram linked and wants this event."""
    account = await get_active_account(db, user_id, provider=provider)
    if not account:
        # Also try bale if telegram missing
        if provider == "telegram":
            return await enqueue_telegram(
                db,
                organization_id=organization_id,
                user_id=user_id,
                event_type=event_type,
                text=text,
                buttons=buttons,
                entity_type=entity_type,
                entity_id=entity_id,
                conversation_id=conversation_id,
                provider="bale",
            )
        return None

    prefs = parse_prefs(account.notify_prefs)
    pref_key = EVENT_PREF.get(event_type, event_type)
    if event_type == "digest":
        if not account.digest_enabled:
            return None
    elif not prefs.get(pref_key, True):
        return None

    now = utc_now()
    next_at = now
    if is_quiet_now(account, now) and event_type != "digest":
        # push to end of quiet window
        end = account.quiet_end_hour or 8
        next_at = now.replace(hour=end, minute=0, second=0, microsecond=0)
        if next_at <= now:
            next_at = next_at + timedelta(days=1)

    row = TelegramOutbox(
        organization_id=organization_id,
        user_id=user_id,
        provider=account.provider,
        event_type=event_type,
        text=text,
        buttons_json=json.dumps(buttons, ensure_ascii=False) if buttons else None,
        entity_type=entity_type,
        entity_id=entity_id,
        conversation_id=conversation_id,
        status="pending",
        attempts=0,
        next_attempt_at=next_at,
    )
    db.add(row)
    await db.flush()
    return row


async def dispatch_pending(
    db: AsyncSession,
    clients: dict[str, TelegramClient],
    *,
    limit: int = 20,
) -> int:
    """Send pending outbox rows. Returns number sent."""
    now = utc_now()
    rows = list(
        (
            await db.execute(
                select(TelegramOutbox)
                .where(
                    TelegramOutbox.status == "pending",
                    or_(
                        TelegramOutbox.next_attempt_at.is_(None),
                        TelegramOutbox.next_attempt_at <= now,
                    ),
                )
                .order_by(TelegramOutbox.created_at.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    sent = 0
    for row in rows:
        account = await get_active_account(db, row.user_id, provider=row.provider)
        if not account or not account.telegram_chat_id:
            row.status = "failed"
            row.last_error = "no_active_account"
            continue
        client = clients.get(row.provider)
        if not client:
            row.status = "failed"
            row.last_error = "no_client"
            continue
        markup = None
        if row.buttons_json:
            try:
                markup = inline_keyboard(json.loads(row.buttons_json))
            except Exception:
                markup = None
        try:
            result = await client.send_message(
                int(account.telegram_chat_id),
                row.text,
                reply_markup=markup,
            )
            mid = None
            if isinstance(result, dict):
                mid = (result.get("result") or {}).get("message_id")
            row.telegram_message_id = int(mid) if mid is not None else None
            row.status = "sent"
            row.sent_at = utc_now()
            row.last_error = None
            sent += 1
        except TelegramApiError as e:
            row.attempts = (row.attempts or 0) + 1
            row.last_error = str(e)[:500]
            if e.status_code == 403:
                account.disabled_at = utc_now()
                row.status = "failed"
                log.warning("telegram_blocked", user_id=str(row.user_id), provider=row.provider)
            elif e.status_code == 429:
                delay = e.retry_after or min(60, 2 ** min(row.attempts, 5))
                row.next_attempt_at = utc_now() + timedelta(seconds=delay)
                row.status = "pending"
            elif row.attempts >= 5:
                row.status = "failed"
            else:
                row.next_attempt_at = utc_now() + timedelta(seconds=min(120, 2**row.attempts))
        except Exception as e:
            row.attempts = (row.attempts or 0) + 1
            row.last_error = str(e)[:500]
            if row.attempts >= 5:
                row.status = "failed"
            else:
                row.next_attempt_at = utc_now() + timedelta(seconds=min(120, 2**row.attempts))
    await db.flush()
    return sent


def classify_notify_event(
    *,
    title: str,
    entity_type: str | None,
) -> str:
    t = (title or "").lower()
    et = (entity_type or "").lower()
    if "escalat" in t or "sla" in t or "deadline" in t or "مهلت" in title or "دیر" in title:
        return "sla"
    if "branch" in t or "شعبه" in title:
        return "branch"
    if et == "message" or "message" in t or "پیام" in title:
        return "message"
    if "completed" in t or "done" in t or "انجام" in title:
        return "task_done"
    if et == "task" or "task" in t or "assigned" in t or "کار" in title:
        return "task_assigned"
    if et == "case":
        return "branch"
    return "task_assigned"
