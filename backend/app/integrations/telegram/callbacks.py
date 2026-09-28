"""Signed short callback payloads for inline buttons."""

from __future__ import annotations

import hashlib
import hmac
from uuid import UUID

from app.core.config import get_settings


def _secret() -> bytes:
    return get_settings().secret_key.encode("utf-8")


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:8]


def encode_callback(action: str, entity_type: str, entity_id: UUID | str) -> str:
    """Format: action:etype:shortid:sig  (Telegram limit 64 bytes)."""
    eid = str(entity_id).replace("-", "")[:12]
    et = entity_type[:4]
    base = f"{action}:{et}:{eid}"
    return f"{base}:{_sign(base)}"


def verify_callback(data: str) -> tuple[str, str, str] | None:
    """Returns (action, entity_type_prefix, short_id) or None if invalid."""
    parts = (data or "").split(":")
    if len(parts) != 4:
        return None
    action, et, eid, sig = parts
    base = f"{action}:{et}:{eid}"
    if not hmac.compare_digest(sig, _sign(base)):
        return None
    return action, et, eid


def match_uuid_prefix(short_id: str, full_id: UUID | str) -> bool:
    cleaned = str(full_id).replace("-", "")
    return cleaned.startswith(short_id)


# Approval decisions ride on the same signed format. entity_type is truncated
# to 4 chars by encode_callback, so "approval" verifies back as "appr".
APPROVAL_ENTITY_TYPE = "approval"
APPROVAL_ENTITY_PREFIX = APPROVAL_ENTITY_TYPE[:4]
APPROVAL_ACTIONS = ("approve", "reject")


def encode_approval_callback(action: str, entity_id: UUID | str) -> str:
    """Signed payload for the «تأیید» / «رد» inline buttons."""
    if action not in APPROVAL_ACTIONS:
        raise ValueError("action must be approve or reject")
    return encode_callback(action, APPROVAL_ENTITY_TYPE, entity_id)


def is_approval_callback(action: str, entity_type_prefix: str) -> bool:
    return action in APPROVAL_ACTIONS and entity_type_prefix == APPROVAL_ENTITY_PREFIX
