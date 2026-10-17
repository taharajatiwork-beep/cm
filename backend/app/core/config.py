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
    field_encryption_key: str = ""  # Fernet key; در production الزامی
    llm_external_enabled: bool = True  # خاموش = بدون ارسال به LLM بیرونی
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 14
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    login_max_failures: int = 8
    login_lock_minutes: int = 15
    upload_max_bytes: int = 5_000_000
    file_storage_dir: str = "var/files"
    file_backend: str = "local"  # local | s3
    s3_endpoint: str = ""
    s3_bucket: str = "cm"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    worker_mode: str = "embedded"  # embedded | external
    sla_use_business_calendar: bool = False
    sla_chain_escalation: bool = False
    ldap_enabled: bool = False
    ldap_url: str = ""
    sms_provider: str = "fake"  # fake | kavenegar
    sms_api_key: str = ""
    sms_sender: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "cm@localhost"
    voip_mode: str = "fake"  # fake | asterisk
    voip_ami_url: str = ""
    erp_mode: str = "fake"  # fake | http
    erp_api_base: str = ""
    erp_api_token: str = ""
    ai_daily_token_quota: int = 200_000
    require_human_approval_for_sensitive_ai: bool = False
    database_url: str = "postgresql+asyncpg://cm:cm@localhost:5432/cm"
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
    embedding_backend: str = "json"  # json | pgvector (ANN only on PostgreSQL)

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

    # Performance marketing. External calls stay off until a panel or webhook is set.
    isms_send_url: str = "https://panel.isms.ir/sendWS"
    isms_credit_url: str = "https://panel.isms.ir/creditWS"
    # پیشگامان (pishgamrayan). مسیرهای رسمی از swagger خود سرویس: smsapi.pishgamrayan.com/swagger
    pishgam_send_path: str = "/Messages/Send"
    pishgam_balance_path: str = "/Messages/GetCredit"
    pishgam_lines_path: str = "/Messages/PrivateNumberList"
    pishgam_report_path: str = "/Messages/GetDelivery"
    # توکن پیشگامان در .env است (PISHGAM_SMS_*). فقط خواندن موجودی/گزارش؛ ارسال از CM ممنوع تا اطلاع بعدی.
    pishgam_sms_api_url: str = ""
    pishgam_sms_token: str = ""
    perf_sheets_webhook: str = ""
    # Google Sheet. Both are required before a write. The id is the /d/{id}/ part of the URL.
    perf_sheets_spreadsheet_id: str = ""
    perf_sheets_credentials_file: str = ""
    # Copies of the three source workbooks. Rows are appended; existing rows stay.
    perf_sheets_register_campaign_id: str = ""
    perf_sheets_cost_tracking_id: str = ""
    perf_sheets_reporter_id: str = ""
    # Mizito session. Empty token means no network call. Read-only.
    perf_mizito_base: str = "https://app.mizito.ir"
    perf_mizito_token: str = ""
    # Mizito triage: an active card unchanged for more than this many days is "stuck" (1..365).
    perf_mizito_stuck_days: int = 14
    # Optional: the Mizito workspace id, only used to build "open in Mizito" links (no API call).
    perf_mizito_web: str = "https://office.mizito.ir"
    perf_mizito_workspace_id: str = ""
    # درخواست‌های تبلیغ از میزیتو (فقط خواندن). «اسم گفتگو=نقش» (cards|texts|both) جدا با ویرگول؛ بردها "<board_id>=circular,<board_id>=sms".
    perf_mizito_request_dialogs: str = "پرفورمنس مارکتینگ=cards,بخشنامه های فروش=texts"
    perf_mizito_task_boards: str = ""
    perf_mizito_requester_ids: str = ""
    perf_mizito_ignore_ids: str = ""
    perf_mizito_car_models: str = ""
    perf_mizito_branches: str = ""
    perf_mizito_lookback_days: int = 7
    perf_mizito_respect_unread: bool = True
    perf_mizito_history_pages: int = 20
    mizito_sync_enabled: bool = True
    mizito_sync_minutes: int = 15

    # AI Lab (Grok Bot) — isolated marketing analysis pilot; off by default.
    ai_lab_enabled: bool = False
    ai_lab_mode: str = "manual"  # manual | webhook
    ai_lab_outbound_url: str = ""
    ai_lab_outbound_secret: str = ""
    ai_lab_outbound_bearer: str = ""  # e.g. Cursor Automations webhook Authorization bearer
    ai_lab_inbound_secret: str = ""
    ai_lab_callback_base: str = ""  # public API base, e.g. https://cm.example.com/api
    ai_lab_task_ttl_hours: int = 24
    ai_lab_result_source: str = "callback"  # callback | github
    ai_lab_github_repo: str = ""
    ai_lab_github_token_ro: str = ""
    ai_lab_followup_days: int = 14
    ai_lab_weekly_enabled: bool = False
    ai_lab_weekly_weekday: int = 5  # Monday=0 … Saturday=5
    ai_lab_schedule_user_email: str = ""
    ai_lab_anomaly_enabled: bool = False
    ai_lab_anomaly_cpl_ratio: float = 1.5


@lru_cache
def get_settings() -> Settings:
    return Settings()
