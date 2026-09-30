from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.integrations.telegram.adapter import TelegramAdapter
from app.integrations.telegram.client import FakeTelegramClient, HttpTelegramClient
from app.integrations.telegram.messages import BOT_COMMANDS
from app.integrations.telegram.runtime import build_clients

router = APIRouter(prefix="/telegram", tags=["telegram"])

# Shared fake client for tests / when no token configured
_test_client: FakeTelegramClient | None = None


def get_telegram_client(provider: str = "telegram"):
    global _test_client
    settings = get_settings()
    if provider == "bale":
        if settings.bale_bot_token:
            return HttpTelegramClient(token=settings.bale_bot_token, api_base=settings.bale_api_base)
    else:
        if settings.telegram_bot_token:
            return HttpTelegramClient()
    if _test_client is None:
        _test_client = FakeTelegramClient()
    return _test_client


def set_test_telegram_client(client: FakeTelegramClient | None) -> None:
    global _test_client
    _test_client = client


class LinkCodeOut(BaseModel):
    link_code: str
    deep_link: str | None = None
    instructions: str
    expires_in_minutes: int = 10
    provider: str = "telegram"


class StatusOut(BaseModel):
    linked: bool
    provider: str
    bot_username: str | None = None
    username: str | None = None
    disabled: bool = False
    notify_prefs: dict[str, bool] | None = None
    quiet_start_hour: int | None = None
    quiet_end_hour: int | None = None
    digest_enabled: bool = True
    deep_link_template: str | None = None


class PrefsIn(BaseModel):
    notify_prefs: dict[str, bool] | None = None
    quiet_start_hour: int | None = Field(default=None, ge=0, le=23)
    quiet_end_hour: int | None = Field(default=None, ge=0, le=23)
    clear_quiet: bool = False
    digest_enabled: bool | None = None
    provider: str = "telegram"


class WebhookResult(BaseModel):
    ok: bool
    reply_text: str = ""
    work_item_id: str | None = None
    clarification: bool = False


class SetupResult(BaseModel):
    ok: bool
    mode: str
    detail: str = ""


def _deep_link(bot_username: str | None, code: str) -> str | None:
    if not bot_username:
        return None
    return f"https://t.me/{bot_username.lstrip('@')}?start={code}"


@router.get("/status", response_model=StatusOut)
async def telegram_status(
    provider: str = "telegram",
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    adapter = TelegramAdapter(db, client=get_telegram_client(provider), provider=provider)
    st = await adapter.get_status(ctx.user, provider=provider)
    bot = st.get("bot_username")
    return StatusOut(
        **st,
        deep_link_template=f"https://t.me/{bot.lstrip('@')}?start={{code}}" if bot else None,
    )


@router.post("/link-code", response_model=LinkCodeOut)
async def create_link_code(
    provider: str = "telegram",
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    adapter = TelegramAdapter(db, client=get_telegram_client(provider), provider=provider)
    code = await adapter.create_link_code(ctx.user, provider=provider)
    bot = settings.telegram_bot_username if provider == "telegram" else settings.bale_bot_username
    deep = _deep_link(bot, code)
    instructions = (
        f"در تلگرام باز کنید یا بفرستید: /link {code}"
        if not deep
        else "دکمه «باز کردن در تلگرام» را بزنید؛ اتصال خودکار انجام می‌شود."
    )
    return LinkCodeOut(
        link_code=code,
        deep_link=deep,
        instructions=instructions,
        expires_in_minutes=settings.telegram_link_code_ttl_minutes,
        provider=provider,
    )


@router.post("/unlink")
async def unlink_telegram(
    provider: str = "telegram",
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    adapter = TelegramAdapter(db, client=get_telegram_client(provider), provider=provider)
    await adapter.unlink(ctx.user, provider=provider)
    return {"ok": True}


@router.patch("/prefs", response_model=StatusOut)
async def update_telegram_prefs(
    body: PrefsIn,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    adapter = TelegramAdapter(db, client=get_telegram_client(body.provider), provider=body.provider)
    await adapter.update_prefs(
        ctx.user,
        notify_prefs=body.notify_prefs,
        quiet_start_hour=body.quiet_start_hour,
        quiet_end_hour=body.quiet_end_hour,
        digest_enabled=body.digest_enabled,
        clear_quiet=body.clear_quiet,
        provider=body.provider,
    )
    st = await adapter.get_status(ctx.user, provider=body.provider)
    bot = st.get("bot_username")
    return StatusOut(
        **st,
        deep_link_template=f"https://t.me/{bot.lstrip('@')}?start={{code}}" if bot else None,
    )


@router.post("/webhook", response_model=WebhookResult)
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    settings = get_settings()
    if (
        settings.telegram_webhook_secret
        and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret
    ):
        raise HTTPException(403, "Invalid webhook secret")

    update: dict[str, Any] = await request.json()
    adapter = TelegramAdapter(db, client=get_telegram_client("telegram"), provider="telegram")
    result = await adapter.handle_update(update)
    return WebhookResult(
        ok=result.ok,
        reply_text=result.reply_text,
        work_item_id=str(result.work_item_id) if result.work_item_id else None,
        clarification=result.clarification,
    )


@router.post("/webhook/bale", response_model=WebhookResult)
async def bale_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    settings = get_settings()
    if (
        settings.bale_webhook_secret
        and x_telegram_bot_api_secret_token != settings.bale_webhook_secret
    ):
        raise HTTPException(403, "Invalid webhook secret")
    update: dict[str, Any] = await request.json()
    adapter = TelegramAdapter(db, client=get_telegram_client("bale"), provider="bale")
    result = await adapter.handle_update(update)
    return WebhookResult(
        ok=result.ok,
        reply_text=result.reply_text,
        work_item_id=str(result.work_item_id) if result.work_item_id else None,
        clarification=result.clarification,
    )


@router.post("/setup", response_model=SetupResult)
async def telegram_setup(
    ctx: AuthContext = Depends(get_current_user),
):
    """Admin helper: setWebhook / deleteWebhook + setMyCommands for current mode."""
    from app.core.permissions import PermissionCode, require_permission

    require_permission(ctx.permissions, PermissionCode.ORG_ADMIN)
    settings = get_settings()
    clients = build_clients()
    if "telegram" not in clients and not _test_client:
        # Allow setup with fake in tests
        client = get_telegram_client("telegram")
    else:
        client = clients.get("telegram") or get_telegram_client("telegram")
    try:
        await client.set_my_commands(BOT_COMMANDS)
        if settings.telegram_mode == "webhook":
            if not settings.telegram_webhook_url:
                return SetupResult(ok=False, mode="webhook", detail="telegram_webhook_url is empty")
            await client.set_webhook(
                settings.telegram_webhook_url,
                secret_token=settings.telegram_webhook_secret or None,
            )
            return SetupResult(ok=True, mode="webhook", detail=settings.telegram_webhook_url)
        if settings.telegram_mode == "polling":
            await client.delete_webhook()
            return SetupResult(ok=True, mode="polling", detail="webhook deleted; polling will run")
        return SetupResult(ok=True, mode="off", detail="telegram_mode=off")
    except Exception as e:  # noqa: BLE001 - admin setup endpoint reports any provider error
        return SetupResult(ok=False, mode=settings.telegram_mode, detail=str(e))
