from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "cm"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 1440
    database_url: str = "sqlite+aiosqlite:///./cm_dev.db"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    algorithm: str = "HS256"

    # Telegram (adapter only — never source of truth)
    # telegram_mode: off | polling | webhook
    telegram_mode: str = "off"
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""  # without @ — for deep links
    telegram_webhook_secret: str = "dev-telegram-webhook-secret"
    telegram_api_base: str = "https://api.telegram.org"
    telegram_webhook_url: str = ""  # full HTTPS URL for setWebhook
    telegram_link_code_ttl_minutes: int = 10
    telegram_outbox_poll_seconds: float = 2.0
    telegram_sla_poll_seconds: float = 300.0
    telegram_digest_hour_utc: int = 5  # ~08:30 Iran
    telegram_ask_rate_per_minute: int = 8
    web_app_base_url: str = "http://localhost:5173"

    # Optional Bale provider (Telegram-compatible API)
    bale_bot_token: str = ""
    bale_bot_username: str = ""
    bale_api_base: str = "https://tapi.bale.ai"
    bale_mode: str = "off"  # off | polling | webhook
    bale_webhook_secret: str = ""
    bale_webhook_url: str = ""

    # Embeddings / RAG memory (structured truth stays in SQL)
    embedding_provider: str = "hash"  # hash | openai
    embedding_model: str = "hash-v1"
    embedding_dims: int = 64
    embedding_api_key: str = ""
    embedding_api_base: str = "https://api.openai.com/v1"

    # Assignment engine business rule
    assignment_auto_assign_enabled: bool = False

    # Inventory agent
    inventory_aging_days: int = 30
    inventory_min_branch_requests: int = 2
    inventory_auto_create_opportunity: bool = True

    # Sales agent
    sales_stale_days: int = 3
    sales_auto_create_follow_up: bool = True

    # Purchase agent
    purchase_stale_days: int = 3
    purchase_auto_create_opportunity: bool = True

    # Divar assisted pilot (external Node service at C:\taha\projects\divar)
    # mode: fake (tests/offline) | http (talk to DIVAR_API_BASE)
    divar_mode: str = "fake"
    divar_api_base: str = "http://localhost:3000"
    divar_api_token: str = "tok-admin-xyz"
    divar_auto_prepare: bool = True

    # LLM planner (9Router OpenAI-compatible). Default rules = no external calls in tests.
    # llm_provider: rules | openai | 9router | fake
    llm_provider: str = "rules"
    llm_api_base: str = "http://localhost:20128/v1"
    llm_api_key: str = ""
    llm_model: str = "taha"


@lru_cache
def get_settings() -> Settings:
    return Settings()
