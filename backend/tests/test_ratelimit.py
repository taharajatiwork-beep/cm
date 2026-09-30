"""تست rate limit ورود: با Redis مشترک، و بدون Redis به‌صورت محلی."""

from __future__ import annotations

from typing import Any

import pytest

from app.core import ratelimit
from app.services.sessions import login_allowed


class FakeRedis:
    """کلاینت Redis کافی برای منطق شمارنده، بدون سرور واقعی.

    کلیدهای شمارنده با `cm:rl:` شروع می‌شوند و TTL آن‌ها `-1` است
    (یعنی هنوز expire نشده‌اند) — مثل Redis واقعی پیش از اولین EXPIRE.
    """

    def __init__(self) -> None:
        self.store: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    def ttl(self, key: str) -> int:
        return -1  # هنوز TTL ندارد

    def expire(self, key: str, seconds: int) -> bool:
        return True

    def ping(self) -> bool:
        return True

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)


class FakePipeline:
    """پیپ‌لاین INCR + TTL.

    هر فرمان جداگانه ثبت می‌شود تا `execute` بتواند بین INCR (که شمارنده را
    زیاد می‌کند) و TTL (که فقط می‌خواند) فرق بگذارد.
    """

    def __init__(self, client: FakeRedis) -> None:
        self._client = client
        self._commands: list[tuple[str, str]] = []

    def incr(self, key: str) -> FakePipeline:
        self._commands.append(("incr", key))
        return self

    def ttl(self, key: str) -> FakePipeline:
        self._commands.append(("ttl", key))
        return self

    def execute(self) -> list[int]:
        results: list[int] = []
        for op, key in self._commands:
            results.append(self._client.incr(key) if op == "incr" else self._client.ttl(key))
        return results


@pytest.fixture(autouse=True)
def _clean():
    ratelimit.reset()
    ratelimit._client = None
    ratelimit._client_failed = False
    yield
    ratelimit.reset()
    ratelimit._client = None
    ratelimit._client_failed = False


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    client = FakeRedis()
    monkeypatch.setattr(ratelimit, "_get_client", lambda: client)
    return client


def test_allows_up_to_the_limit(fake_redis):
    for _ in range(3):
        assert login_allowed("1.2.3.4", "a@b.com", limit=3) is True


def test_blocks_past_the_limit(fake_redis):
    for _ in range(3):
        login_allowed("1.2.3.4", "a@b.com", limit=3)
    assert login_allowed("1.2.3.4", "a@b.com", limit=3) is False


def test_counter_is_shared_across_replicas(fake_redis):
    """مهم‌ترین رفتار: دو «سرور» باید یک شمارنده ببینند.

    هر دو فراخوانی از همان کلاینت Redis استفاده می‌کنند، دقیقاً مثل دو
    replica که به یک Redis وصل‌اند. قبل از این تغییر، هر کدام شمارندهٔ
    خودشان را داشتند و سقف واقعی چند برابر می‌شد.
    """
    assert login_allowed("1.2.3.4", "a@b.com", limit=2) is True  # replica 1
    assert login_allowed("1.2.3.4", "a@b.com", limit=2) is True  # replica 2
    # سومی از هر دو زده می‌شود ولی هر دو مجاز نیستند
    assert login_allowed("1.2.3.4", "a@b.com", limit=2) is False


def test_redis_key_is_namespaced(fake_redis):
    login_allowed("1.2.3.4", "a@b.com", limit=5)
    assert any(k.startswith("cm:rl:") for k in fake_redis.store)


def test_different_email_has_own_budget(fake_redis):
    for _ in range(2):
        login_allowed("1.2.3.4", "a@b.com", limit=2)
    # کاربر دیگر نباید تحت تأثیر باشد
    assert login_allowed("1.2.3.4", "other@b.com", limit=2) is True


def test_different_host_has_own_budget(fake_redis):
    for _ in range(2):
        login_allowed("1.2.3.4", "a@b.com", limit=2)
    assert login_allowed("5.6.7.8", "a@b.com", limit=2) is True


def test_email_case_is_normalised(fake_redis):
    for _ in range(2):
        login_allowed("1.2.3.4", "a@b.com", limit=2)
    # همان ایمیل با حروف بزرگ نباید شمارندهٔ تازه بسازد
    assert login_allowed("1.2.3.4", "A@B.com", limit=2) is False


def test_falls_back_to_memory_without_redis(monkeypatch):
    """نبود Redis نباید سرویس را متوقف کند."""
    monkeypatch.setattr(ratelimit, "_get_client", lambda: None)
    for _ in range(3):
        assert login_allowed("9.9.9.9", "c@d.com", limit=3) is True
    assert login_allowed("9.9.9.9", "c@d.com", limit=3) is False


def test_falls_back_when_redis_raises(monkeypatch):
    """اگر Redis وسط کار قطع شود، باید به حافظه برگردد نه خطا بدهد."""

    class Broken(FakeRedis):
        def pipeline(self) -> Any:
            raise RuntimeError("connection reset")

    monkeypatch.setattr(ratelimit, "_get_client", lambda: Broken())
    assert login_allowed("8.8.8.8", "e@f.com", limit=2) is True
    assert login_allowed("8.8.8.8", "e@f.com", limit=2) is True
    assert login_allowed("8.8.8.8", "e@f.com", limit=2) is False


def test_expire_is_set_for_a_fresh_key(fake_redis):
    """کلید تازه باید TTL بگیرد وگرنه هرگز پاک نمی‌شود."""
    calls: list[tuple[str, int]] = []
    original = fake_redis.expire

    def spy(key: str, seconds: int) -> bool:
        calls.append((key, seconds))
        return original(key, seconds)

    fake_redis.expire = spy  # type: ignore[method-assign]
    login_allowed("7.7.7.7", "g@h.com", limit=5)
    assert calls and calls[0][1] == 60  # window پیش‌فرض
