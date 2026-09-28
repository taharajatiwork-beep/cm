"""Refuse to boot production with placeholder secrets."""

from app.core.config import Settings

_PLACEHOLDERS = {
    "dev-secret-change-me",
    "change-me-in-production-use-a-long-random-string",
    "dev-telegram-webhook-secret",
    "tok-admin-xyz",
}


def assert_production_safe(settings: Settings) -> None:
    if settings.app_env != "production":
        return
    problems: list[str] = []
    if settings.debug:
        problems.append("DEBUG must be false")
    if settings.secret_key in _PLACEHOLDERS or len(settings.secret_key) < 24:
        problems.append("SECRET_KEY is a placeholder")
    if settings.telegram_webhook_secret in _PLACEHOLDERS:
        problems.append("TELEGRAM_WEBHOOK_SECRET is a placeholder")
    if settings.divar_api_token in _PLACEHOLDERS and settings.divar_mode == "http":
        problems.append("DIVAR_API_TOKEN is a placeholder")
    if settings.database_url.startswith("sqlite"):
        problems.append("DATABASE_URL must be PostgreSQL in production")
    if problems:
        raise RuntimeError("Refusing to start: " + "; ".join(problems))
