"""HMAC signing for CM ↔ Grok Bot webhook traffic."""

from __future__ import annotations

import hashlib
import hmac
import time

WINDOW_SECONDS = 300


def sign(secret: str, timestamp: str, body: bytes) -> str:
    msg = timestamp.encode("utf-8") + b"." + body
    digest = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify(secret: str, timestamp: str, signature: str, body: bytes) -> bool:
    if not secret or not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    now = int(time.time())
    if abs(now - ts) > WINDOW_SECONDS:
        return False
    expected = sign(secret, timestamp, body)
    return hmac.compare_digest(expected, signature.strip())
