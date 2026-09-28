"""Cursor pagination helper. List endpoints keep returning arrays unless envelope=1."""

from __future__ import annotations

import base64
from typing import Any


def encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str | None) -> str | None:
    if not cursor:
        return None
    try:
        return base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
    except Exception:
        return None


def envelope(items: list[Any], *, total: int, next_cursor: str | None) -> dict[str, Any]:
    return {"items": items, "total": total, "next_cursor": next_cursor}


def page(items: list[Any], *, cursor: str | None, limit: int) -> dict[str, Any]:
    """Offset cursor. Callers keep returning the raw list unless envelope=1."""
    start = 0
    decoded = decode_cursor(cursor)
    if decoded and decoded.isdigit():
        start = int(decoded)
    limit = max(1, min(limit, 100))
    chunk = items[start : start + limit]
    nxt = encode_cursor(str(start + limit)) if start + limit < len(items) else None
    return envelope(chunk, total=len(items), next_cursor=nxt)
