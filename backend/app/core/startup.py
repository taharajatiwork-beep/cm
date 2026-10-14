"""Refuse to boot production with placeholder secrets."""

from app.core.config import Settings

_PLACEHOLDERS = {
    "dev-secret-change-me",
    "change-me-in-production-use-a-long-random-string",
    "dev-telegram-webhook-secret",
    "tok-admin-xyz",
}


def assert_postgres_url(settings: Settings) -> None:
    url = settings.database_url
    if url.startswith("sqlite") or "postgresql" not in url:
        raise RuntimeError(
            "DATABASE_URL must be PostgreSQL (docker compose postgres). SQLite is not supported."
        )


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
    if "postgresql" not in settings.database_url or settings.database_url.startswith("sqlite"):
        problems.append("DATABASE_URL must be PostgreSQL in production")
    # بدون Secure، کوکی نشست روی هر اتصال HTTP (از جمله داخل شبکهٔ محلی)
    # قابل ربودن است؛ nginx همه را به HTTPS می‌فرستد ولی دفاع چندلایه لازم است.
    if not settings.cookie_secure:
        problems.append("COOKIE_SECURE must be true behind HTTPS")
    # اگر TLS در مسیر نیست (روی localhost مستقیم اجرا می‌شود) الزام سخت است
    elif "https://" not in settings.cors_origins.lower():
        problems.append("CORS_ORIGINS should list https origins when COOKIE_SECURE is on")
    # worker نباید در همان پروسهٔ API اجرا شود مگر صریحاً خواسته شده باشد
    if settings.worker_mode == "embedded" and settings.app_env == "production":
        problems.append("WORKER_MODE should be 'external' in production")
    if settings.ai_lab_enabled and settings.ai_lab_mode == "webhook":
        if not settings.ai_lab_outbound_url.strip():
            problems.append("AI_LAB_OUTBOUND_URL is required when AI lab webhook mode is on")
        if not settings.ai_lab_outbound_secret or len(settings.ai_lab_outbound_secret) < 24:
            problems.append("AI_LAB_OUTBOUND_SECRET is too short")
        if not settings.ai_lab_inbound_secret or len(settings.ai_lab_inbound_secret) < 24:
            problems.append("AI_LAB_INBOUND_SECRET is too short")
        has_callback = bool(settings.ai_lab_callback_base.strip())
        if not has_callback:
            has_callback = any(
                o.strip().startswith("https://") for o in settings.cors_origins.split(",")
            )
        if not has_callback:
            problems.append("AI_LAB_CALLBACK_BASE or https CORS_ORIGINS is required for inbound results")
        if (
            "cursor.sh/automations/webhook" in settings.ai_lab_outbound_url
            and not (settings.ai_lab_outbound_bearer or "").strip()
        ):
            problems.append("AI_LAB_OUTBOUND_BEARER is required for Cursor automation webhooks")
    if problems:
        raise RuntimeError("Refusing to start: " + "; ".join(problems))
