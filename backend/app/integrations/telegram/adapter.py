"""Telegram adapter — thin edge that calls Communication / Work / Search / RAG services.

Telegram is never the source of truth.
"""

from __future__ import annotations

import json
import secrets
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.permissions import PermissionCode
from app.core.timeutil import as_utc, utc_now
from app.integrations.telegram import messages as msg
from app.integrations.telegram.callbacks import encode_callback, is_approval_callback, match_uuid_prefix, verify_callback
from app.integrations.telegram.client import FakeTelegramClient, TelegramClient
from app.integrations.telegram.outbox import inline_keyboard
from app.integrations.telegram.resolver import EntityResolver
from app.models import Conversation, Message, Task, TaskAssignee, User
from app.models.enterprise import ApprovalRequest
from app.models.enums import Channel, MessageType, Priority, TaskStatus
from app.models.inventory import Vehicle
from app.models.telegram import (
    TelegramAccount,
    TelegramOutbox,
    TelegramPendingConfirm,
    TelegramProcessedUpdate,
)
from app.services import CommunicationService, WorkService, get_user_permissions
from app.services.search import SearchService

log = get_logger(__name__)

# In-memory rate limit: user_id -> timestamps of assistant asks (per process)
_ask_times: dict[str, list[float]] = defaultdict(list)


@dataclass
class AdapterResult:
    ok: bool
    reply_text: str
    work_item_id: UUID | None = None
    task_ids: list[UUID] | None = None
    clarification: bool = False
    stored_message_id: UUID | None = None


def _lang_for_user(_user: User | None) -> str:
    # Future: read user locale preference. Default Persian for CM.
    return "fa"


class TelegramAdapter:
    def __init__(
        self,
        db: AsyncSession,
        client: TelegramClient | None = None,
        *,
        provider: str = "telegram",
    ):
        self.db = db
        self.client = client or FakeTelegramClient()
        self.provider = provider
        self.resolver = EntityResolver(db)
        self.comms = CommunicationService(db)
        self.work = WorkService(db)

    # ----- linking -----

    async def create_link_code(self, user: User, *, provider: str | None = None) -> str:
        provider = provider or self.provider
        settings = get_settings()
        code = secrets.token_hex(4)
        expires = utc_now() + timedelta(minutes=settings.telegram_link_code_ttl_minutes)
        existing = await self.db.scalar(
            select(TelegramAccount).where(
                TelegramAccount.user_id == user.id,
                TelegramAccount.provider == provider,
            )
        )
        if existing:
            existing.link_code = code
            existing.link_code_expires_at = expires
            existing.telegram_user_id = None
            existing.telegram_chat_id = None
            existing.telegram_username = None
            existing.disabled_at = None
        else:
            self.db.add(
                TelegramAccount(
                    organization_id=user.organization_id,
                    user_id=user.id,
                    provider=provider,
                    link_code=code,
                    link_code_expires_at=expires,
                )
            )
        await self.db.flush()
        return code

    async def get_status(self, user: User, *, provider: str | None = None) -> dict[str, Any]:
        provider = provider or self.provider
        account = await self.db.scalar(
            select(TelegramAccount).where(
                TelegramAccount.user_id == user.id,
                TelegramAccount.provider == provider,
            )
        )
        settings = get_settings()
        bot_user = (
            settings.telegram_bot_username
            if provider == "telegram"
            else settings.bale_bot_username
        )
        if not account:
            return {
                "linked": False,
                "provider": provider,
                "bot_username": bot_user or None,
                "username": None,
                "disabled": False,
                "notify_prefs": None,
                "quiet_start_hour": None,
                "quiet_end_hour": None,
                "digest_enabled": True,
            }
        linked = bool(account.telegram_user_id and account.telegram_chat_id and not account.disabled_at)
        prefs = None
        if account.notify_prefs:
            try:
                prefs = json.loads(account.notify_prefs)
            except Exception:
                prefs = None
        return {
            "linked": linked,
            "provider": provider,
            "bot_username": bot_user or None,
            "username": account.telegram_username,
            "disabled": bool(account.disabled_at),
            "notify_prefs": prefs,
            "quiet_start_hour": account.quiet_start_hour,
            "quiet_end_hour": account.quiet_end_hour,
            "digest_enabled": bool(account.digest_enabled),
        }

    async def unlink(self, user: User, *, provider: str | None = None) -> None:
        provider = provider or self.provider
        account = await self.db.scalar(
            select(TelegramAccount).where(
                TelegramAccount.user_id == user.id,
                TelegramAccount.provider == provider,
            )
        )
        if not account:
            return
        account.telegram_user_id = None
        account.telegram_chat_id = None
        account.telegram_username = None
        account.link_code = None
        account.link_code_expires_at = None
        account.disabled_at = utc_now()
        await self.db.flush()

    async def update_prefs(
        self,
        user: User,
        *,
        notify_prefs: dict[str, bool] | None = None,
        quiet_start_hour: int | None = None,
        quiet_end_hour: int | None = None,
        digest_enabled: bool | None = None,
        clear_quiet: bool = False,
        provider: str | None = None,
    ) -> TelegramAccount | None:
        provider = provider or self.provider
        account = await self.db.scalar(
            select(TelegramAccount).where(
                TelegramAccount.user_id == user.id,
                TelegramAccount.provider == provider,
            )
        )
        if not account:
            return None
        if notify_prefs is not None:
            account.notify_prefs = json.dumps(notify_prefs, ensure_ascii=False)
        if clear_quiet:
            account.quiet_start_hour = None
            account.quiet_end_hour = None
        else:
            if quiet_start_hour is not None:
                account.quiet_start_hour = quiet_start_hour
            if quiet_end_hour is not None:
                account.quiet_end_hour = quiet_end_hour
        if digest_enabled is not None:
            account.digest_enabled = digest_enabled
        await self.db.flush()
        return account

    async def link_by_code(
        self,
        *,
        link_code: str,
        telegram_user_id: int,
        telegram_chat_id: int,
        telegram_username: str | None = None,
    ) -> TelegramAccount | None:
        account = await self.db.scalar(
            select(TelegramAccount).where(
                TelegramAccount.link_code == link_code,
                TelegramAccount.provider == self.provider,
            )
        )
        if not account:
            return None
        expires = as_utc(account.link_code_expires_at)
        if expires and expires < utc_now():
            return None
        conflict = await self.db.scalar(
            select(TelegramAccount).where(
                TelegramAccount.provider == self.provider,
                TelegramAccount.telegram_user_id == telegram_user_id,
                TelegramAccount.id != account.id,
            )
        )
        if conflict:
            return None
        account.telegram_user_id = telegram_user_id
        account.telegram_chat_id = telegram_chat_id
        account.telegram_username = telegram_username
        account.link_code = None
        account.link_code_expires_at = None
        account.disabled_at = None
        await self.db.flush()
        return account

    async def resolve_account(self, telegram_user_id: int) -> TelegramAccount | None:
        return await self.db.scalar(
            select(TelegramAccount).where(
                TelegramAccount.provider == self.provider,
                TelegramAccount.telegram_user_id == telegram_user_id,
                TelegramAccount.disabled_at.is_(None),
            )
        )

    async def _mark_update(self, update_id: int) -> bool:
        """Return True if this update is new; False if duplicate."""
        existing = await self.db.scalar(
            select(TelegramProcessedUpdate).where(
                TelegramProcessedUpdate.provider == self.provider,
                TelegramProcessedUpdate.update_id == update_id,
            )
        )
        if existing:
            return False
        self.db.add(
            TelegramProcessedUpdate(provider=self.provider, update_id=update_id)
        )
        await self.db.flush()
        return True

    async def _get_or_create_dm_conversation(self, user: User, chat_id: int) -> Conversation:
        topic = f"telegram:{self.provider}:{user.id}"
        existing = await self.db.scalar(
            select(Conversation).where(
                Conversation.organization_id == user.organization_id,
                Conversation.channel == Channel.TELEGRAM,
                Conversation.topic == topic,
            )
        )
        if existing:
            return existing
        return await self.comms.create_conversation(
            organization_id=user.organization_id,
            channel=Channel.TELEGRAM,
            participant_ids=[user.id],
            topic=topic,
            actor_id=user.id,
        )

    def _web_url(self, path: str) -> str:
        base = get_settings().web_app_base_url.rstrip("/")
        return f"{base}{path}"

    def _task_buttons(self, task_id: UUID, *, lang: str) -> list[list[dict[str, str]]]:
        return [
            [
                {"text": msg.btn_done(lang=lang), "callback_data": encode_callback("done", "task", task_id)},
                {"text": msg.btn_open(lang=lang), "url": self._web_url("/my-work")},
            ],
            [
                {
                    "text": msg.btn_hand_over(lang=lang),
                    "callback_data": encode_callback("hando", "task", task_id),
                },
            ],
        ]

    # ----- main entry -----

    async def handle_update(self, update: dict[str, Any]) -> AdapterResult:
        update_id = update.get("update_id")
        if update_id is not None:
            is_new = await self._mark_update(int(update_id))
            if not is_new:
                return AdapterResult(ok=True, reply_text="")

        if update.get("callback_query"):
            return await self._handle_callback(update["callback_query"])

        message = update.get("message") or update.get("edited_message")
        if not message:
            return AdapterResult(ok=True, reply_text="")

        return await self._handle_message(message)

    async def _handle_callback(self, cq: dict[str, Any]) -> AdapterResult:
        cq_id = str(cq.get("id") or "")
        data = str(cq.get("data") or "")
        from_user = cq.get("from") or {}
        message = cq.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = int(chat.get("id") or 0)
        message_id = message.get("message_id")
        tg_user_id = int(from_user.get("id") or 0)
        lang = "fa"

        account = await self.resolve_account(tg_user_id)
        if not account:
            await self.client.answer_callback_query(cq_id, text=msg.not_linked(lang=lang), show_alert=True)
            return AdapterResult(ok=False, reply_text=msg.not_linked(lang=lang))

        user = await self.db.get(User, account.user_id)
        if not user:
            await self.client.answer_callback_query(cq_id, text=msg.not_linked(lang=lang), show_alert=True)
            return AdapterResult(ok=False, reply_text=msg.not_linked(lang=lang))
        lang = _lang_for_user(user)

        parsed = verify_callback(data)
        if not parsed:
            await self.client.answer_callback_query(cq_id, text="Invalid", show_alert=True)
            return AdapterResult(ok=False, reply_text="Invalid callback")

        action, et_prefix, short_id = parsed

        if is_approval_callback(action, et_prefix):
            return await self._handle_approval_decision(
                user,
                account,
                action,
                short_id,
                cq_id,
                chat_id,
                message_id,
                lang,
                original_text=str(message.get("text") or ""),
            )

        if action == "done" and et_prefix == "task":
            task = await self._find_task_by_prefix(user.organization_id, short_id)
            if not task:
                await self.client.answer_callback_query(cq_id, text=msg.task_done_fail("not found", lang=lang), show_alert=True)
                return AdapterResult(ok=False, reply_text="task not found")
            try:
                await self.work.complete_task(task.id, user.id)
                reply = msg.task_done_ok(lang=lang)
                await self.client.answer_callback_query(cq_id, text=reply)
                if message_id and chat_id:
                    await self.client.edit_message_text(
                        chat_id,
                        int(message_id),
                        f"{message.get('text') or task.title}\n\n{reply}",
                        reply_markup={"inline_keyboard": []},
                    )
                return AdapterResult(ok=True, reply_text=reply)
            except Exception as e:
                err = msg.task_done_fail(str(e), lang=lang)
                await self.client.answer_callback_query(cq_id, text=err, show_alert=True)
                return AdapterResult(ok=False, reply_text=err)

        if action == "hando" and et_prefix == "task":
            hint = msg.hand_over_hint(lang=lang)
            await self.client.answer_callback_query(cq_id, text=hint, show_alert=True)
            return AdapterResult(ok=True, reply_text=hint)

        if action == "ok" and et_prefix == "conf":
            return await self._confirm_create(user, short_id, cq_id, chat_id, message_id, lang)

        if action == "no" and et_prefix == "conf":
            pending = await self._find_confirm_by_prefix(user.id, short_id)
            if pending:
                await self.db.delete(pending)
                await self.db.flush()
            text = msg.confirm_cancelled(lang=lang)
            await self.client.answer_callback_query(cq_id, text=text)
            if message_id and chat_id:
                await self.client.edit_message_text(chat_id, int(message_id), text, reply_markup={"inline_keyboard": []})
            return AdapterResult(ok=True, reply_text=text)

        if action == "show":
            await self.client.answer_callback_query(cq_id)
            return await self._cmd_kar(user, chat_id, lang)

        await self.client.answer_callback_query(cq_id)
        return AdapterResult(ok=True, reply_text="")

    async def _find_task_by_prefix(self, organization_id: UUID, short_id: str) -> Task | None:
        rows = (
            await self.db.execute(
                select(Task).where(Task.organization_id == organization_id).order_by(Task.created_at.desc()).limit(200)
            )
        ).scalars().all()
        for t in rows:
            if match_uuid_prefix(short_id, t.id):
                return t
        return None

    async def _find_approval_by_prefix(
        self, organization_id: UUID, short_id: str
    ) -> ApprovalRequest | None:
        rows = (
            await self.db.execute(
                select(ApprovalRequest)
                .where(ApprovalRequest.organization_id == organization_id)
                .order_by(ApprovalRequest.created_at.desc())
                .limit(200)
            )
        ).scalars().all()
        for row in rows:
            if match_uuid_prefix(short_id, row.id):
                return row
        return None

    async def _handle_approval_decision(
        self,
        user: User,
        account: TelegramAccount,
        action: str,
        short_id: str,
        cq_id: str,
        chat_id: int,
        message_id: Any,
        lang: str,
        original_text: str = "",
    ) -> AdapterResult:
        """Approve / reject from an inline button. Telegram is not the source of truth."""
        from app.services.enterprise_ops import EnterpriseService

        organization_id = account.organization_id
        row = await self._find_approval_by_prefix(organization_id, short_id)
        if not row:
            text = msg.approval_not_found(lang=lang)
            await self.client.answer_callback_query(cq_id, text=text, show_alert=True)
            return AdapterResult(ok=False, reply_text=text)

        decision = "approved" if action == "approve" else "rejected"
        try:
            decided = await EnterpriseService(self.db).decide(
                organization_id=organization_id,
                request_id=row.id,
                actor_id=user.id,
                decision=decision,
            )
        except ValueError as exc:
            reason = str(exc)
            if "approver" in reason.lower():
                text = msg.approval_not_approver(lang=lang)
            elif "already" in reason.lower():
                text = msg.approval_already_decided(lang=lang)
            else:
                text = msg.approval_not_found(lang=lang)
            await self.client.answer_callback_query(cq_id, text=text, show_alert=True)
            return AdapterResult(ok=False, reply_text=text)

        final = decided.status != "pending"
        if decision == "rejected":
            reply = msg.approval_rejected(lang=lang)
        else:
            reply = msg.approval_step_recorded(final, lang=lang)
            if not final:
                from app.services.enterprise_ops import notify_current_approver

                await notify_current_approver(self.db, decided)
        await self.client.answer_callback_query(cq_id, text=reply)
        if message_id and chat_id and final:
            # Drop the buttons once the request is decided.
            await self.client.edit_message_text(
                chat_id,
                int(message_id),
                f"{original_text}\n\n{reply}".strip(),
                reply_markup={"inline_keyboard": []},
            )
        return AdapterResult(ok=True, reply_text=reply)
    async def _find_confirm_by_prefix(self, user_id: UUID, short_id: str) -> TelegramPendingConfirm | None:
        rows = (
            await self.db.execute(
                select(TelegramPendingConfirm).where(TelegramPendingConfirm.user_id == user_id)
            )
        ).scalars().all()
        for p in rows:
            if match_uuid_prefix(short_id, p.id):
                return p
        return None

    async def _confirm_create(
        self,
        user: User,
        short_id: str,
        cq_id: str,
        chat_id: int,
        message_id: Any,
        lang: str,
    ) -> AdapterResult:
        pending = await self._find_confirm_by_prefix(user.id, short_id)
        if not pending or as_utc(pending.expires_at) < utc_now():
            await self.client.answer_callback_query(cq_id, text=msg.link_invalid(lang=lang), show_alert=True)
            return AdapterResult(ok=False, reply_text="expired")
        payload = json.loads(pending.payload_json)
        result = await self._execute_create_work(user, payload, lang)
        await self.db.delete(pending)
        await self.db.flush()
        await self.client.answer_callback_query(cq_id, text=msg.btn_confirm(lang=lang))
        if message_id and chat_id:
            await self.client.edit_message_text(
                chat_id,
                int(message_id),
                result.reply_text,
                reply_markup={"inline_keyboard": []},
            )
        return result

    async def _handle_message(self, message: dict[str, Any]) -> AdapterResult:
        chat = message.get("chat") or {}
        from_user = message.get("from") or {}
        chat_id = int(chat.get("id"))
        tg_user_id = int(from_user.get("id"))
        username = from_user.get("username")
        text = (message.get("text") or "").strip()
        tg_message_id = str(message.get("message_id")) if message.get("message_id") else None
        reply_to = message.get("message_id")
        reply_to_tg = message.get("reply_to_message")
        lang = "fa"

        if not text:
            reply = msg.text_only(lang=lang)
            await self.client.send_message(chat_id, reply)
            return AdapterResult(ok=True, reply_text=reply)

        # /start <code> deep link
        if text.startswith("/start"):
            parts = text.split(maxsplit=1)
            if len(parts) >= 2 and parts[1].strip():
                return await self._do_link(parts[1].strip(), tg_user_id, chat_id, username, lang)
            account = await self.resolve_account(tg_user_id)
            if account:
                user = await self.db.get(User, account.user_id)
                reply = msg.already_linked(lang=lang)
                if user:
                    reply = msg.linked_ok(user.full_name.split()[0], lang=_lang_for_user(user))
                await self.client.send_message(chat_id, reply)
                return AdapterResult(ok=True, reply_text=reply)
            reply = msg.welcome_unlinked(lang=lang)
            await self.client.send_message(chat_id, reply)
            return AdapterResult(ok=True, reply_text=reply)

        if text.startswith("/link"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                reply = msg.link_usage(lang=lang)
                await self.client.send_message(chat_id, reply)
                return AdapterResult(ok=True, reply_text=reply)
            return await self._do_link(parts[1].strip(), tg_user_id, chat_id, username, lang)

        account = await self.resolve_account(tg_user_id)
        if not account:
            reply = msg.not_linked(lang=lang)
            await self.client.send_message(chat_id, reply)
            return AdapterResult(ok=False, reply_text=reply)

        account.telegram_chat_id = chat_id
        if username:
            account.telegram_username = username
        await self.db.flush()

        user = await self.db.get(User, account.user_id)
        if not user:
            reply = msg.not_linked(lang=lang)
            await self.client.send_message(chat_id, reply)
            return AdapterResult(ok=False, reply_text=reply)
        lang = _lang_for_user(user)

        # Reply to a notification → post into CM conversation
        if reply_to_tg and reply_to_tg.get("message_id"):
            routed = await self._try_route_reply(user, chat_id, text, int(reply_to_tg["message_id"]), lang)
            if routed:
                return routed

        conv = await self._get_or_create_dm_conversation(user, chat_id)
        stored = await self.comms.post_message(
            organization_id=user.organization_id,
            conversation_id=conv.id,
            sender_id=user.id,
            text=text,
            channel=Channel.TELEGRAM,
            message_type=MessageType.TEXT,
            channel_message_id=tg_message_id,
        )

        cmd = text.split()[0].split("@")[0].lower()
        if cmd in ("/help", "help"):
            reply = msg.help_text(lang=lang)
            await self.client.send_message(chat_id, reply, reply_to_message_id=reply_to)
            return AdapterResult(ok=True, reply_text=reply, stored_message_id=stored.id)

        if cmd in ("/unlink",):
            await self.unlink(user, provider=self.provider)
            reply = msg.unlinked_ok(lang=lang)
            await self.client.send_message(chat_id, reply)
            return AdapterResult(ok=True, reply_text=reply, stored_message_id=stored.id)

        if cmd in ("/kar", "/tasks", "کارهای من"):
            return await self._cmd_kar(user, chat_id, lang, stored_id=stored.id, reply_to=reply_to)

        if cmd in ("/payam", "/messages", "منتظر"):
            return await self._cmd_payam(user, chat_id, lang, stored_id=stored.id, reply_to=reply_to)

        if cmd in ("/khodro", "/car", "/vehicle"):
            q = text.split(maxsplit=1)[1] if " " in text else ""
            return await self._cmd_khodro(user, chat_id, q, lang, stored_id=stored.id, reply_to=reply_to)

        # Natural language: create work or ask assistant
        resolution = await self.resolver.resolve(user.organization_id, text)
        if resolution.ambiguous:
            reply = resolution.clarification or "Ambiguous request."
            await self.client.send_message(chat_id, reply, reply_to_message_id=reply_to)
            return AdapterResult(
                ok=True,
                reply_text=reply,
                clarification=True,
                stored_message_id=stored.id,
            )

        if resolution.intent == "create_work" and resolution.users:
            if not resolution.vehicles:
                reply = resolution.clarification or msg.need_vehicle(lang=lang)
                await self.client.send_message(chat_id, reply, reply_to_message_id=reply_to)
                return AdapterResult(
                    ok=True,
                    reply_text=reply,
                    clarification=True,
                    stored_message_id=stored.id,
                )
            return await self._offer_create_work(user, text, resolution, chat_id, reply_to, lang, stored.id)

        # Free text → Hybrid RAG (with rate limit)
        return await self._ask_assistant(user, text, chat_id, reply_to, lang, stored.id)

    async def _do_link(
        self,
        code: str,
        tg_user_id: int,
        chat_id: int,
        username: str | None,
        lang: str,
    ) -> AdapterResult:
        account = await self.link_by_code(
            link_code=code,
            telegram_user_id=tg_user_id,
            telegram_chat_id=chat_id,
            telegram_username=username,
        )
        if not account:
            reply = msg.link_invalid(lang=lang)
            await self.client.send_message(chat_id, reply)
            return AdapterResult(ok=False, reply_text=reply)
        user = await self.db.get(User, account.user_id)
        name = user.full_name.split()[0] if user else ""
        reply = msg.linked_ok(name, lang=lang)
        await self.client.send_message(chat_id, reply)
        return AdapterResult(ok=True, reply_text=reply)

    async def _try_route_reply(
        self,
        user: User,
        chat_id: int,
        text: str,
        reply_to_message_id: int,
        lang: str,
    ) -> AdapterResult | None:
        outbox = await self.db.scalar(
            select(TelegramOutbox).where(
                TelegramOutbox.user_id == user.id,
                TelegramOutbox.provider == self.provider,
                TelegramOutbox.telegram_message_id == reply_to_message_id,
            )
        )
        if not outbox or not outbox.conversation_id:
            return None
        stored = await self.comms.post_message(
            organization_id=user.organization_id,
            conversation_id=outbox.conversation_id,
            sender_id=user.id,
            text=text,
            channel=Channel.TELEGRAM,
            message_type=MessageType.TEXT,
        )
        # Notify other participants
        from app.models import ConversationParticipant
        from app.integrations.telegram.outbox import enqueue_telegram

        parts = (
            await self.db.execute(
                select(ConversationParticipant).where(
                    ConversationParticipant.conversation_id == outbox.conversation_id
                )
            )
        ).scalars().all()
        conv = await self.db.get(Conversation, outbox.conversation_id)
        topic = (conv.topic if conv else "") or msg.t("گفتگو", "Conversation", lang=lang)
        for p in parts:
            if p.user_id == user.id:
                continue
            await enqueue_telegram(
                self.db,
                organization_id=user.organization_id,
                user_id=p.user_id,
                event_type="message",
                text=msg.notify_message(topic, text[:200], user.full_name.split()[0], lang=lang),
                entity_type="message",
                entity_id=stored.id,
                conversation_id=outbox.conversation_id,
                buttons=[
                    [{"text": msg.btn_open(lang=lang), "url": self._web_url("/communication")}],
                ],
            )
        reply = msg.t("ارسال شد ✓", "Sent ✓", lang=lang)
        await self.client.send_message(chat_id, reply)
        return AdapterResult(ok=True, reply_text=reply, stored_message_id=stored.id)

    async def _cmd_kar(
        self,
        user: User,
        chat_id: int,
        lang: str,
        *,
        stored_id: UUID | None = None,
        reply_to: int | None = None,
    ) -> AdapterResult:
        tasks = await self.work.list_tasks(
            user.organization_id,
            assignee_id=user.id,
            status=None,
            limit=30,
        )
        open_tasks = [t for t in tasks if t.status != TaskStatus.COMPLETED][:10]
        if not open_tasks:
            reply = msg.no_open_tasks(lang=lang)
            await self.client.send_message(chat_id, reply, reply_to_message_id=reply_to)
            return AdapterResult(ok=True, reply_text=reply, stored_message_id=stored_id)
        lines = [msg.t("کارهای باز شما:", "Your open to-dos:", lang=lang)]
        for i, t in enumerate(open_tasks, 1):
            lines.append(f"{i}. {t.title}")
        reply = "\n".join(lines)
        # Send each with a done button (first 5)
        await self.client.send_message(chat_id, reply, reply_to_message_id=reply_to)
        for t in open_tasks[:5]:
            await self.client.send_message(
                chat_id,
                t.title,
                reply_markup=inline_keyboard(self._task_buttons(t.id, lang=lang)),
            )
        return AdapterResult(ok=True, reply_text=reply, stored_message_id=stored_id)

    async def _cmd_payam(
        self,
        user: User,
        chat_id: int,
        lang: str,
        *,
        stored_id: UUID | None = None,
        reply_to: int | None = None,
    ) -> AdapterResult:
        from app.models import ConversationParticipant

        conv_ids = (
            await self.db.execute(
                select(ConversationParticipant.conversation_id).where(
                    ConversationParticipant.user_id == user.id
                )
            )
        ).scalars().all()
        waiting: list[tuple[Conversation, Message]] = []
        for cid in conv_ids[:40]:
            msgs = await self.comms.list_messages(cid)
            if not msgs:
                continue
            last = msgs[-1]
            if last.sender_id and last.sender_id != user.id:
                conv = await self.db.get(Conversation, cid)
                if conv:
                    waiting.append((conv, last))
        if not waiting:
            reply = msg.no_waiting_messages(lang=lang)
            await self.client.send_message(chat_id, reply, reply_to_message_id=reply_to)
            return AdapterResult(ok=True, reply_text=reply, stored_message_id=stored_id)
        lines = [msg.t("منتظر جواب شما:", "Waiting for your reply:", lang=lang)]
        for conv, m in waiting[:8]:
            lines.append(f"• {conv.topic or '—'}: {m.text[:80]}")
        reply = "\n".join(lines)
        await self.client.send_message(
            chat_id,
            reply,
            reply_to_message_id=reply_to,
            reply_markup=inline_keyboard(
                [[{"text": msg.btn_open(lang=lang), "url": self._web_url("/communication")}]]
            ),
        )
        return AdapterResult(ok=True, reply_text=reply, stored_message_id=stored_id)

    async def _cmd_khodro(
        self,
        user: User,
        chat_id: int,
        query: str,
        lang: str,
        *,
        stored_id: UUID | None = None,
        reply_to: int | None = None,
    ) -> AdapterResult:
        if not query.strip():
            reply = msg.t("مثال: /khodro النترا ۲۰۲۱", "Example: /khodro Elantra 2021", lang=lang)
            await self.client.send_message(chat_id, reply, reply_to_message_id=reply_to)
            return AdapterResult(ok=True, reply_text=reply, stored_message_id=stored_id)
        from app.services.search import SearchEntityType

        perms = await get_user_permissions(self.db, user)
        try:
            hits = await SearchService(self.db).search(
                organization_id=user.organization_id,
                actor_permissions=perms,
                q=query,
                types=[SearchEntityType.VEHICLE],
                limit=5,
            )
        except Exception as e:
            reply = str(e)
            await self.client.send_message(chat_id, reply)
            return AdapterResult(ok=False, reply_text=reply, stored_message_id=stored_id)
        if not hits:
            reply = msg.t("خودرویی پیدا نشد.", "No vehicles found.", lang=lang)
            await self.client.send_message(chat_id, reply, reply_to_message_id=reply_to)
            return AdapterResult(ok=True, reply_text=reply, stored_message_id=stored_id)
        lines = []
        for h in hits[:5]:
            lines.append(f"• {h.title}")
            if h.entity_id:
                lines.append(f"  {self._web_url(f'/vehicles/{h.entity_id}')}")
        reply = "\n".join(lines)
        await self.client.send_message(chat_id, reply, reply_to_message_id=reply_to)
        return AdapterResult(ok=True, reply_text=reply, stored_message_id=stored_id)

    async def _offer_create_work(
        self,
        user: User,
        text: str,
        resolution: Any,
        chat_id: int,
        reply_to: int | None,
        lang: str,
        stored_id: UUID,
    ) -> AdapterResult:
        perms = await get_user_permissions(self.db, user)
        if (
            PermissionCode.WORK_ITEM_WRITE not in perms
            and PermissionCode.ORG_ADMIN not in perms
        ):
            reply = msg.no_permission(lang=lang)
            await self.client.send_message(chat_id, reply)
            return AdapterResult(ok=False, reply_text=reply, stored_message_id=stored_id)

        vehicle = resolution.vehicles[0]
        title = f"Sell {vehicle.brand} {vehicle.model}"
        if vehicle.stock_number:
            title += f" #{vehicle.stock_number}"
        task_lines = []
        assignees = []
        for ru in resolution.users:
            task_title = self._infer_task_title(text, ru.matched_token, ru.user.full_name)
            assignees.append({"user_id": str(ru.user.id), "title": task_title, "name": ru.user.full_name})
            task_lines.append(f"• {ru.user.full_name.split()[0]}: {task_title}")

        payload = {
            "title": title,
            "text": text,
            "vehicle_id": str(vehicle.id),
            "branch_id": str(vehicle.branch_id) if vehicle.branch_id else None,
            "assignees": assignees,
        }
        pending = TelegramPendingConfirm(
            organization_id=user.organization_id,
            user_id=user.id,
            provider=self.provider,
            kind="create_work",
            payload_json=json.dumps(payload),
            expires_at=utc_now() + timedelta(minutes=15),
        )
        self.db.add(pending)
        await self.db.flush()

        preview = msg.confirm_create_preview(title, task_lines, lang=lang)
        keyboard = inline_keyboard(
            [
                [
                    {
                        "text": msg.btn_confirm(lang=lang),
                        "callback_data": encode_callback("ok", "conf", pending.id),
                    },
                    {
                        "text": msg.btn_cancel(lang=lang),
                        "callback_data": encode_callback("no", "conf", pending.id),
                    },
                ]
            ]
        )
        await self.client.send_message(chat_id, preview, reply_to_message_id=reply_to, reply_markup=keyboard)
        return AdapterResult(ok=True, reply_text=preview, clarification=True, stored_message_id=stored_id)

    async def _execute_create_work(self, user: User, payload: dict[str, Any], lang: str) -> AdapterResult:
        perms = await get_user_permissions(self.db, user)
        vehicle = await self.db.get(Vehicle, UUID(payload["vehicle_id"]))
        if not vehicle:
            return AdapterResult(ok=False, reply_text=msg.need_vehicle(lang=lang))
        title = payload["title"]
        wi = await self.work.create_work_item(
            organization_id=user.organization_id,
            title=title,
            owner_id=user.id,
            description=payload.get("text"),
            priority=Priority.HIGH,
            branch_id=UUID(payload["branch_id"]) if payload.get("branch_id") else None,
            vehicle_id=vehicle.id,
            participant_ids=[UUID(a["user_id"]) for a in payload["assignees"]],
        )
        task_ids: list[UUID] = []
        lines = [
            msg.t(f"خودرو: {vehicle.brand} {vehicle.model}", f"Vehicle: {vehicle.brand} {vehicle.model}", lang=lang),
            "",
        ]
        for a in payload["assignees"]:
            task = await self.work.create_task(
                organization_id=user.organization_id,
                title=a["title"],
                owner_id=user.id,
                work_item_id=wi.id,
                assignee_ids=[UUID(a["user_id"])],
                priority=Priority.HIGH,
                actor_permissions=perms | {PermissionCode.TASK_WRITE},
            )
            task_ids.append(task.id)
            lines.append(f"• {a['name'].split()[0]}: {a['title']}")
        reply = msg.project_created(title, lines, lang=lang)
        return AdapterResult(ok=True, reply_text=reply, work_item_id=wi.id, task_ids=task_ids)

    def _rate_ok(self, user_id: UUID) -> bool:
        import time

        settings = get_settings()
        key = str(user_id)
        now = time.time()
        window = [t for t in _ask_times[key] if now - t < 60]
        _ask_times[key] = window
        if len(window) >= settings.telegram_ask_rate_per_minute:
            return False
        window.append(now)
        _ask_times[key] = window
        return True

    async def _ask_assistant(
        self,
        user: User,
        text: str,
        chat_id: int,
        reply_to: int | None,
        lang: str,
        stored_id: UUID,
    ) -> AdapterResult:
        if not self._rate_ok(user.id):
            reply = msg.rate_limited(lang=lang)
            await self.client.send_message(chat_id, reply, reply_to_message_id=reply_to)
            return AdapterResult(ok=True, reply_text=reply, stored_message_id=stored_id)

        perms = await get_user_permissions(self.db, user)
        if PermissionCode.RAG_READ not in perms and PermissionCode.ORG_ADMIN not in perms:
            # Fall back to stored-only
            reply = msg.stored_only(lang=lang)
            await self.client.send_message(chat_id, reply, reply_to_message_id=reply_to)
            return AdapterResult(ok=True, reply_text=reply, stored_message_id=stored_id)

        from app.services.hybrid_rag import HybridRagService

        try:
            result = await HybridRagService(self.db).run(
                organization_id=user.organization_id,
                query=text,
                actor_permissions=perms,
                top_k=5,
            )
        except Exception as e:
            reply = msg.t(f"نتوانست جواب بدهد: {e}", f"Could not answer: {e}", lang=lang)
            await self.client.send_message(chat_id, reply, reply_to_message_id=reply_to)
            return AdapterResult(ok=False, reply_text=reply, stored_message_id=stored_id)

        answer = result.answer or msg.t("جوابی نبود.", "No answer.", lang=lang)
        sources = []
        for h in (result.hits or [])[:3]:
            sources.append(f"• {h.title}")
        if sources:
            answer += "\n\n" + msg.t("بر اساس:", "Based on:", lang=lang) + "\n" + "\n".join(sources)
        await self.client.send_message(chat_id, answer, reply_to_message_id=reply_to)
        return AdapterResult(ok=True, reply_text=answer, stored_message_id=stored_id)

    @staticmethod
    def _infer_task_title(text: str, matched_token: str, full_name: str) -> str:
        lower = text.lower()
        name = full_name.split()[0]
        if matched_token in ("رضا", "reza") or name.lower() == "reza":
            if "مشتری" in text or "contact" in lower or "پیگیری" in text:
                return "Contact customers"
            return "Follow up (seller)"
        if matched_token in ("سارا", "sara") or name.lower() == "sara":
            if "آگهی" in text or "تبلیغ" in text or "listing" in lower or "marketing" in lower:
                return "Prepare marketing material"
            return "Marketing task"
        return f"Task for {name}"

    async def notify_user(self, user_id: UUID, text: str) -> bool:
        account = await self.db.scalar(
            select(TelegramAccount).where(
                TelegramAccount.user_id == user_id,
                TelegramAccount.provider == self.provider,
                TelegramAccount.disabled_at.is_(None),
            )
        )
        if not account or not account.telegram_chat_id:
            return False
        await self.client.send_message(int(account.telegram_chat_id), text)
        return True
