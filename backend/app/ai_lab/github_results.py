"""Fetch Grok results from a private GitHub repo."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError

from app.ai_lab.schemas import BotCallbackIn
from app.ai_lab.signing import verify_github_result_signature

GITHUB_API = "https://api.github.com"


class GithubResultEnvelope(BaseModel):
    task_id: UUID
    timestamp: str | int
    signature: str
    body: str


@dataclass
class GithubFetchResult:
    found: bool
    transient_error: str | None = None
    payload: dict[str, Any] | None = None
    apply_error: str | None = None


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.raw",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def fetch_result_file(repo: str, task_id: UUID, token: str) -> GithubFetchResult:
    url = f"{GITHUB_API}/repos/{repo}/contents/results/{task_id}.json"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.get(url, headers=_headers(token))
    except httpx.HTTPError as exc:
        return GithubFetchResult(found=False, transient_error=str(exc))
    if res.status_code == 404:
        return GithubFetchResult(found=False)
    if res.status_code >= 500:
        return GithubFetchResult(found=False, transient_error=f"GitHub HTTP {res.status_code}")
    if res.status_code >= 400:
        return GithubFetchResult(found=False, apply_error=f"GitHub HTTP {res.status_code}")
    try:
        raw = res.text
        envelope = GithubResultEnvelope.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        return GithubFetchResult(found=True, apply_error=f"Invalid envelope: {exc}")
    return GithubFetchResult(found=True, payload=envelope.model_dump(mode="json"))


def envelope_to_callback(
    envelope: dict[str, Any],
    expected_task_id: UUID,
    inbound_secret: str,
) -> tuple[BotCallbackIn | None, str | None]:
    """Validate signature and parse body into BotCallbackIn. Returns (parsed, error)."""
    try:
        parsed_env = GithubResultEnvelope.model_validate(envelope)
    except ValidationError as exc:
        return None, f"Invalid envelope: {exc}"
    if parsed_env.task_id != expected_task_id:
        return None, "task_id mismatch"
    if not verify_github_result_signature(
        inbound_secret,
        parsed_env.timestamp,
        parsed_env.signature,
        parsed_env.body,
    ):
        return None, "invalid signature"
    try:
        inner = json.loads(parsed_env.body)
    except json.JSONDecodeError:
        return None, "invalid body JSON"
    if inner.get("task_id") and str(inner.get("task_id")) != str(expected_task_id):
        return None, "task_id mismatch in body"
    try:
        callback = BotCallbackIn.model_validate(inner)
    except ValidationError as exc:
        return None, f"Invalid bot payload: {exc}"
    if str(callback.task_id) != str(expected_task_id):
        return None, "task_id mismatch in body"
    return callback, None
