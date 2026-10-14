"""تست‌های محافظ تولید: چیزی نباید در production با تنظیمات ناامن بالا بیاید."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.startup import assert_postgres_url, assert_production_safe


def _prod(**overrides) -> Settings:
    """یک تنظیم سالمِ production می‌سازد تا هر تست فقط یک چیز را خراب کند."""
    base = {
        "app_env": "production",
        "debug": False,
        "secret_key": "a" * 48,
        "telegram_webhook_secret": "b" * 48,
        "divar_api_token": "c" * 48,
        "divar_mode": "fake",
        "database_url": "postgresql+asyncpg://u:p@postgres:5432/cm",
        "cookie_secure": True,
        "cors_origins": "https://cm.example.com",
        "worker_mode": "external",
    }
    base.update(overrides)
    return Settings(**base)


def test_healthy_production_config_boots():
    """خط پایه: تنظیم درست نباید جلوی بالا آمدن را بگیرد."""
    assert_production_safe(_prod())


def test_debug_true_is_rejected():
    with pytest.raises(RuntimeError, match="DEBUG"):
        assert_production_safe(_prod(debug=True))


def test_insecure_cookie_is_rejected():
    """کوکی بدون Secure روی HTTP قابل ربودن است."""
    with pytest.raises(RuntimeError, match="COOKIE_SECURE"):
        assert_production_safe(_prod(cookie_secure=False))


def test_https_cors_with_secure_cookie_is_enforced():
    """اگر کوکی Secure است، origin ها هم باید https باشند."""
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        assert_production_safe(_prod(cors_origins="http://cm.example.com"))


def test_embedded_worker_is_rejected_in_production():
    with pytest.raises(RuntimeError, match="WORKER_MODE"):
        assert_production_safe(_prod(worker_mode="embedded"))


def test_short_secret_key_is_rejected():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        assert_production_safe(_prod(secret_key="short"))


def test_placeholder_secrets_are_rejected():
    with pytest.raises(RuntimeError):
        assert_production_safe(_prod(secret_key="dev-secret-change-me"))


def test_sqlite_is_rejected_in_production():
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        assert_production_safe(_prod(database_url="sqlite+aiosqlite:///./cm.db"))


def test_sqlite_is_rejected_in_any_env():
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        assert_postgres_url(Settings(database_url="sqlite+aiosqlite:///./cm_dev.db"))


def test_all_problems_are_reported_at_once():
    """رفع یکی‌یکی آزاردهنده است؛ همه باید با هم گفته شوند."""
    with pytest.raises(RuntimeError) as exc:
        assert_production_safe(
            _prod(debug=True, cookie_secure=False, worker_mode="embedded")
        )
    message = str(exc.value)
    for expected in ("DEBUG", "COOKIE_SECURE", "WORKER_MODE"):
        assert expected in message


def test_ai_lab_webhook_requires_secrets_in_production():
    with pytest.raises(RuntimeError, match="AI_LAB"):
        assert_production_safe(
            _prod(
                ai_lab_enabled=True,
                ai_lab_mode="webhook",
                ai_lab_outbound_url="",
            )
        )


def test_development_is_never_blocked():
    """توسعهٔ محلی نباید به تنظیمات تولید نیاز داشته باشد."""
    assert_production_safe(
        Settings(
            app_env="development",
            debug=True,
            secret_key="dev-secret-change-me",
            cookie_secure=False,
            worker_mode="embedded",
        )
    )
