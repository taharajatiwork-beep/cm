"""OpenAI-compatible LLM client (9Router / OpenCode Zen models)."""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any, Protocol
from uuid import UUID

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

# Set only on a request that has a DB session. Absent context keeps the old path.
_usage_ctx: ContextVar[tuple[Any, UUID, UUID] | None] = ContextVar("llm_usage", default=None)


def bind_llm_usage(db: Any, organization_id: UUID, user_id: UUID):
    """Record token use for this task. Returns the context token for reset()."""
    return _usage_ctx.set((db, organization_id, user_id))


def reset_llm_usage(token) -> None:
    _usage_ctx.reset(token)


class LLMClient(Protocol):
    async def chat_json(
        self, *, system: str, user: str, temperature: float = 0.1
    ) -> dict[str, Any]: ...

    async def chat_text(
        self, *, system: str, user: str, temperature: float = 0.2
    ) -> str: ...


class FakeLLMClient:
    """Deterministic planner output for tests."""

    def __init__(self, response: dict[str, Any] | None = None):
        self.response = response or {
            "intent": "create_work",
            "clarification": None,
            "tools": [
                {"name": "search_inventory", "args": {"q": "Camry", "model": "Camry"}},
                {"name": "find_users", "args": {"q": "رضا"}},
                {"name": "find_users", "args": {"q": "سارا"}},
                {"name": "_compose_work", "args": {"text": ""}},
            ],
        }
        self.text_response = "Fake grounded answer from context."

    async def chat_json(
        self, *, system: str, user: str, temperature: float = 0.1
    ) -> dict[str, Any]:
        out = dict(self.response)
        for t in out.get("tools") or []:
            if t.get("name") == "_compose_work":
                t["args"] = {**(t.get("args") or {}), "text": user}
        return out

    async def chat_text(
        self, *, system: str, user: str, temperature: float = 0.2
    ) -> str:
        return self.text_response


class OpenAICompatibleLLM:
    """Chat Completions against 9Router (or any OpenAI-compatible gateway)."""

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        model: str | None = None,
    ):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.llm_api_key
        self.api_base = (api_base or settings.llm_api_base).rstrip("/")
        self.model = model or settings.llm_model

    async def chat_json(
        self, *, system: str, user: str, temperature: float = 0.1
    ) -> dict[str, Any]:
        content = await self._complete(
            system=system, user=user, temperature=temperature, json_mode=True
        )
        return _parse_json_content(content)

    async def chat_text(
        self, *, system: str, user: str, temperature: float = 0.2
    ) -> str:
        return await self._complete(
            system=system, user=user, temperature=temperature, json_mode=False
        )

    async def _complete(
        self, *, system: str, user: str, temperature: float, json_mode: bool
    ) -> str:
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is required")
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{self.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code >= 400:
                if json_mode and resp.status_code in (400, 422) and "response_format" in (
                    resp.text or ""
                ):
                    payload.pop("response_format", None)
                    resp = await client.post(
                        f"{self.api_base}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                if resp.status_code >= 400:
                    log.warning("llm_error", status=resp.status_code, body=resp.text[:500])
                    raise RuntimeError(f"LLM error {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            await _record_usage(data.get("usage") or {}, self.model)
            return str(data["choices"][0]["message"]["content"] or "")


async def _record_usage(usage: dict[str, Any], model: str) -> None:
    ctx = _usage_ctx.get()
    if not ctx:
        return
    db, organization_id, user_id = ctx
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    if prompt + completion <= 0:
        return
    from app.services.enterprise_ops import EnterpriseService

    await EnterpriseService(db).record_ai_usage(
        organization_id, user_id, model, prompt, completion
    )


def _parse_json_content(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Extract first JSON object/array from noisy model output
        for opener, closer in (("{", "}"), ("[", "]")):
            start = text.find(opener)
            end = text.rfind(closer)
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    continue
        raise


def get_llm_client() -> LLMClient | None:
    settings = get_settings()
    if settings.llm_provider in ("off", "rules", ""):
        return None
    if settings.llm_provider == "fake":
        return FakeLLMClient()
    if settings.llm_provider in ("openai", "9router", "opencode"):
        return OpenAICompatibleLLM()
    return None
