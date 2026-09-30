"""شمارندهٔ سر rate با پشتیبانی Redis و fallback به حافظه.

وقتی چند replica از API پشت nginx اجرا شوند، یک شمارندهٔ in-process
برای هر پروسه جدا است و در نتیجه سقف واقعی چند برابر می‌شود
(مثلاً با ۳ replica، محدودیت ۱۰ یعنی ۳۰ تلاش). این ماژول شمارنده را در
Redis نگه می‌دارد تا بین همهٔ replicaها مشترک باشد.

اگر Redis در دسترس نباشد به شمارندهٔ حافظه‌ای برمی‌گردیم — یعنی رفتار
قدیمی حفظ می‌شود و سیستم هرگز به خاطر نبود Redis از کار نمی‌افتد.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.config import get_settings

# هر فرایند یک کلاینت Redis می‌سازد و نگه می‌دارد.
_client: Any = None
_client_failed = False

# شمارندهٔ حافظه‌ای برای حالتی که Redis نیست.
_local_hits: dict[str, list[float]] = {}


def _get_client() -> Any | None:
    """کلاینت Redis، یا None اگر در دسترس نبود."""
    global _client, _client_failed
    if _client is not None:
        return _client
    if _client_failed:
        return None
    try:
        import redis  # type: ignore
    except ImportError:
        _client_failed = True
        return None
    url = get_settings().redis_url
    if not url:
        _client_failed = True
        return None
    try:
        _client = redis.from_url(url, encoding="utf-8", decode_responses=True)
        _client.ping()
    except Exception:  # noqa: BLE001 — نبود Redis نباید سرویس را متوقف کند
        _client = None
        _client_failed = True
        return None
    return _client


def _local_allows(key: str, limit: int, window: int) -> bool:
    now = time.time()
    recent = [t for t in _local_hits.get(key, []) if now - t < window]
    if len(recent) >= limit:
        _local_hits[key] = recent
        return False
    recent.append(now)
    _local_hits[key] = recent
    return True


def _redis_allows(client: Any, key: str, limit: int, window: int) -> bool:
    """INCR + EXPIRE اتمیک با پیپ‌لاین.

    اگر INCR از سقف رد شود False برمی‌گرداند. فقط وقتی کلید تازه ساخته شده
    TTL می‌گذاریم تا پنجره از اولین تلاش شروع شود، نه از هر تلاش.
    """
    redis_key = f"cm:rl:{key}"
    pipe = client.pipeline()
    pipe.incr(redis_key)
    pipe.ttl(redis_key)
    count, ttl = pipe.execute()
    if ttl is None or ttl < 0:
        client.expire(redis_key, window)
    return int(count) <= limit


def allow_hit(key: str, limit: int, window: int) -> bool:
    """یک تلاش را ثبت می‌کند؛ False یعنی از سقف عبور کرده."""
    client = _get_client()
    if client is None:
        return _local_allows(key, limit, window)
    try:
        return _redis_allows(client, key, limit, window)
    except Exception:  # noqa: BLE001 — Redis در حین کار هم می‌تواند قطع شود
        return _local_allows(key, limit, window)


def reset() -> None:
    """پاک‌کردن شمارنده‌ها — فقط برای تست."""
    _local_hits.clear()
