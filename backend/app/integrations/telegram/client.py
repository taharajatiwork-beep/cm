"""Telegram Bot API client abstraction.

Real HTTP client for production; FakeTelegramClient for tests.
Business logic must never live here. Token is never logged in clear text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_TOKEN_IN_URL = re.compile(r"/bot([^/]+)/")


def mask_token(text: str) -> str:
    return _TOKEN_IN_URL.sub("/bot***/", text)


@dataclass
class OutboundMessage:
    chat_id: int
    text: str
    reply_to_message_id: int | None = None
    reply_markup: dict[str, Any] | None = None
    kind: str = "send"  # send | edit | answer_callback


class TelegramApiError(Exception):
    def __init__(self, status_code: int, body: dict[str, Any] | str):
        self.status_code = status_code
        self.body = body
        self.retry_after: int | None = None
        if isinstance(body, dict):
            params = body.get("parameters") or {}
            if "retry_after" in params:
                self.retry_after = int(params["retry_after"])
        super().__init__(f"Telegram API {status_code}: {mask_token(str(body))}")


class TelegramClient(Protocol):
    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> dict[str, Any]: ...

    async def get_updates(
        self,
        offset: int | None = None,
        timeout: int = 25,
    ) -> list[dict[str, Any]]: ...

    async def set_webhook(
        self,
        url: str,
        secret_token: str | None = None,
    ) -> dict[str, Any]: ...

    async def delete_webhook(self) -> dict[str, Any]: ...

    async def set_my_commands(self, commands: list[dict[str, str]]) -> dict[str, Any]: ...

    async def get_me(self) -> dict[str, Any]: ...


class HttpTelegramClient:
    def __init__(self, token: str | None = None, api_base: str | None = None):
        settings = get_settings()
        self.token = token if token is not None else settings.telegram_bot_token
        self.api_base = (api_base or settings.telegram_api_base).rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def _url(self, method: str) -> str:
        return f"{self.api_base}/bot{self.token}/{method}"

    async def _post(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.enabled:
            log.warning("telegram_call_skipped_no_token", method=method)
            return {"ok": False, "skipped": True}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(35.0, connect=10.0)) as client:
                resp = await client.post(self._url(method), json=payload or {})
                try:
                    data = resp.json()
                except Exception:
                    data = {"description": resp.text}
                if resp.status_code == 429 or (isinstance(data, dict) and data.get("error_code") == 429):
                    err = TelegramApiError(429, data if isinstance(data, dict) else {"description": str(data)})
                    raise err
                if resp.status_code >= 400 or (isinstance(data, dict) and data.get("ok") is False):
                    raise TelegramApiError(resp.status_code, data if isinstance(data, dict) else str(data))
                return data if isinstance(data, dict) else {"ok": True, "result": data}
        except TelegramApiError:
            raise
        except httpx.HTTPError as e:
            raise TelegramApiError(0, mask_token(str(e))) from e

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self._post("sendMessage", payload)

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self._post("editMessageText", payload)

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id, "show_alert": show_alert}
        if text:
            payload["text"] = text
        return await self._post("answerCallbackQuery", payload)

    async def get_updates(
        self,
        offset: int | None = None,
        timeout: int = 25,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            payload["offset"] = offset
        data = await self._post("getUpdates", payload)
        result = data.get("result") if isinstance(data, dict) else None
        return list(result or [])

    async def set_webhook(self, url: str, secret_token: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "url": url,
            "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": False,
        }
        if secret_token:
            payload["secret_token"] = secret_token
        return await self._post("setWebhook", payload)

    async def delete_webhook(self) -> dict[str, Any]:
        return await self._post("deleteWebhook", {"drop_pending_updates": False})

    async def set_my_commands(self, commands: list[dict[str, str]]) -> dict[str, Any]:
        return await self._post("setMyCommands", {"commands": commands})

    async def get_me(self) -> dict[str, Any]:
        return await self._post("getMe", {})


@dataclass
class FakeTelegramClient:
    """In-memory client for tests — records outbound messages."""

    sent: list[OutboundMessage] = field(default_factory=list)
    edited: list[OutboundMessage] = field(default_factory=list)
    answered_callbacks: list[dict[str, Any]] = field(default_factory=list)
    updates: list[dict[str, Any]] = field(default_factory=list)
    commands: list[dict[str, str]] = field(default_factory=list)
    webhook_url: str | None = None
    fail_status: int | None = None
    retry_after: int = 1
    bot_username: str = "cm_test_bot"
    _msg_id: int = 0

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.fail_status == 429:
            err = TelegramApiError(429, {"ok": False, "error_code": 429, "parameters": {"retry_after": self.retry_after}})
            raise err
        if self.fail_status == 403:
            raise TelegramApiError(403, {"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked"})
        if self.fail_status:
            raise TelegramApiError(self.fail_status, {"ok": False, "error_code": self.fail_status})
        self._msg_id += 1
        self.sent.append(
            OutboundMessage(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=reply_to_message_id,
                reply_markup=reply_markup,
                kind="send",
            )
        )
        return {"ok": True, "result": {"message_id": self._msg_id, "chat": {"id": chat_id}, "text": text}}

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.edited.append(
            OutboundMessage(chat_id=chat_id, text=text, reply_markup=reply_markup, kind="edit")
        )
        return {"ok": True, "result": {"message_id": message_id, "text": text}}

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> dict[str, Any]:
        self.answered_callbacks.append(
            {"id": callback_query_id, "text": text, "show_alert": show_alert}
        )
        return {"ok": True, "result": True}

    async def get_updates(
        self,
        offset: int | None = None,
        timeout: int = 25,
    ) -> list[dict[str, Any]]:
        if offset is None:
            return list(self.updates)
        return [u for u in self.updates if int(u.get("update_id", 0)) >= offset]

    async def set_webhook(self, url: str, secret_token: str | None = None) -> dict[str, Any]:
        self.webhook_url = url
        return {"ok": True, "result": True}

    async def delete_webhook(self) -> dict[str, Any]:
        self.webhook_url = None
        return {"ok": True, "result": True}

    async def set_my_commands(self, commands: list[dict[str, str]]) -> dict[str, Any]:
        self.commands = list(commands)
        return {"ok": True, "result": True}

    async def get_me(self) -> dict[str, Any]:
        return {"ok": True, "result": {"username": self.bot_username, "id": 1, "is_bot": True}}
