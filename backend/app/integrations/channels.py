"""Channel adapter protocols and fake implementations.

Each channel has a Protocol + Fake + Real implementation.
Default is Fake (no external credentials needed).
"""

from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Protocol

import httpx

from app.core.config import get_settings

# ============================================================
# SMS
# ============================================================

class SmsAdapter(Protocol):
    async def send(self, phone: str, text: str) -> DeliveryResult: ...


@dataclass
class DeliveryResult:
    ok: bool
    provider: str
    detail: str


class FakeSmsAdapter:
    """Logs the SMS instead of sending. Default for dev/test."""

    async def send(self, phone: str, text: str) -> DeliveryResult:
        return DeliveryResult(
            ok=True, provider="fake", detail=f"sms to {phone}: {text[:80]}"
        )


class KavenegarSmsAdapter:
    """Real Kavenegar integration (requires KAVENEGAR_API_KEY)."""

    def __init__(self, api_key: str | None = None, sender: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.sms_api_key
        self.sender = sender or settings.sms_sender

    async def send(self, phone: str, text: str) -> DeliveryResult:
        if not self.api_key:
            return DeliveryResult(False, "kavenegar", "API key not configured")
        url = f"https://api.kavenegar.com/v1/{self.api_key}/sms/send.json"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                data={"receptor": phone, "sender": self.sender, "message": text},
            )
        if resp.status_code >= 400:
            return DeliveryResult(False, "kavenegar", resp.text[:200])
        return DeliveryResult(True, "kavenegar", "sent")


def get_sms_adapter() -> SmsAdapter:
    settings = get_settings()
    if settings.sms_provider == "kavenegar" and settings.sms_api_key:
        return KavenegarSmsAdapter()
    return FakeSmsAdapter()


# ============================================================
# Email
# ============================================================

class EmailAdapter(Protocol):
    async def send(self, to: str, subject: str, body: str) -> DeliveryResult: ...


class FakeEmailAdapter:
    """Logs the email instead of sending. Default for dev/test."""

    async def send(self, to: str, subject: str, body: str) -> DeliveryResult:
        return DeliveryResult(
            ok=True, provider="fake", detail=f"email to {to}: {subject}"
        )


class SmtpEmailAdapter:
    """Real SMTP integration."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        from_addr: str | None = None,
    ):
        settings = get_settings()
        self.host = host or settings.smtp_host
        self.port = port or settings.smtp_port
        self.user = user or settings.smtp_user
        self.password = password or settings.smtp_password
        self.from_addr = from_addr or settings.smtp_from

    async def send(self, to: str, subject: str, body: str) -> DeliveryResult:
        if not self.host:
            return DeliveryResult(False, "smtp", "SMTP host not configured")

        def _send() -> None:
            msg = EmailMessage()
            msg["From"] = self.from_addr
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(body)
            with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
                smtp.starttls()
                if self.user:
                    smtp.login(self.user, self.password or "")
                smtp.send_message(msg)

        await asyncio.to_thread(_send)
        return DeliveryResult(True, "smtp", f"sent {subject} to {to}")


def get_email_adapter() -> EmailAdapter:
    settings = get_settings()
    if settings.smtp_host:
        return SmtpEmailAdapter()
    return FakeEmailAdapter()


# ============================================================
# VoIP / Click-to-Call
# ============================================================

class VoipAdapter(Protocol):
    async def click_to_call(self, extension: str, phone: str) -> DeliveryResult: ...


class FakeVoipAdapter:
    """Simulates call origination. Default for dev/test."""

    async def click_to_call(self, extension: str, phone: str) -> DeliveryResult:
        return DeliveryResult(
            ok=True, provider="fake", detail=f"call simulated {extension} -> {phone}"
        )


class AsteriskVoipAdapter:
    """Real Asterisk AMI integration."""

    def __init__(self, ami_url: str | None = None):
        settings = get_settings()
        self.ami_url = ami_url or settings.voip_ami_url

    async def click_to_call(self, extension: str, phone: str) -> DeliveryResult:
        if not self.ami_url:
            return DeliveryResult(False, "asterisk", "AMI URL not configured")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                self.ami_url,
                json={"action": "originate", "extension": extension, "phone": phone},
            )
        if resp.status_code >= 400:
            return DeliveryResult(False, "asterisk", resp.text[:200])
        return DeliveryResult(True, "asterisk", f"originate {extension} -> {phone}")


def get_voip_adapter() -> VoipAdapter:
    settings = get_settings()
    if settings.voip_mode == "asterisk" and settings.voip_ami_url:
        return AsteriskVoipAdapter()
    return FakeVoipAdapter()


# ============================================================
# ERP
# ============================================================

class ErpAdapter(Protocol):
    async def fetch_inventory(self) -> list[dict[str, Any]]: ...


class FakeErpAdapter:
    """Returns empty list. Default for dev/test."""

    async def fetch_inventory(self) -> list[dict[str, Any]]:
        return []


class HttpErpAdapter:
    """Real HTTP ERP integration."""

    def __init__(
        self,
        api_base: str | None = None,
        api_token: str | None = None,
    ):
        settings = get_settings()
        self.api_base = (api_base or settings.erp_api_base).rstrip("/")
        self.api_token = api_token or settings.erp_api_token

    async def fetch_inventory(self) -> list[dict[str, Any]]:
        if not self.api_base or not self.api_token:
            return []
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{self.api_base}/inventory",
                headers={"Authorization": f"Bearer {self.api_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, list):
            return data
        return list(data.get("items") or [])


def get_erp_adapter() -> ErpAdapter:
    settings = get_settings()
    if settings.erp_mode == "http" and settings.erp_api_base and settings.erp_api_token:
        return HttpErpAdapter()
    return FakeErpAdapter()


# ============================================================
# Divar (existing — keep but align with protocol pattern)
# ============================================================

class DivarAdapter(Protocol):
    async def health(self) -> dict[str, Any]: ...
    async def create_product(self, product: dict[str, Any]) -> dict[str, Any]: ...
    async def create_task(self, product_id: str) -> dict[str, Any]: ...
    async def get_prefill(self, task_id: str) -> dict[str, Any]: ...
    async def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]: ...


def get_divar_adapter() -> DivarAdapter:
    """Re-export from divar module for unified access."""
    from app.integrations.divar.client import get_divar_client as _orig

    return _orig()


# ============================================================
# Unified channel registry
# ============================================================

class ChannelRegistry:
    """Central access to all channel adapters."""

    def __init__(self):
        self._sms: SmsAdapter | None = None
        self._email: EmailAdapter | None = None
        self._voip: VoipAdapter | None = None
        self._erp: ErpAdapter | None = None
        self._divar: DivarAdapter | None = None

    @property
    def sms(self) -> SmsAdapter:
        if self._sms is None:
            self._sms = get_sms_adapter()
        return self._sms

    @property
    def email(self) -> EmailAdapter:
        if self._email is None:
            self._email = get_email_adapter()
        return self._email

    @property
    def voip(self) -> VoipAdapter:
        if self._voip is None:
            self._voip = get_voip_adapter()
        return self._voip

    @property
    def erp(self) -> ErpAdapter:
        if self._erp is None:
            self._erp = get_erp_adapter()
        return self._erp

    @property
    def divar(self) -> DivarAdapter:
        if self._divar is None:
            self._divar = get_divar_adapter()
        return self._divar

    def status(self) -> dict[str, str]:
        """Returns the active provider name for each channel."""
        return {
            "sms": type(self.sms).__name__,
            "email": type(self.email).__name__,
            "voip": type(self.voip).__name__,
            "erp": type(self.erp).__name__,
            "divar": type(self.divar).__name__,
        }


def channel_status(settings: Any | None = None) -> dict[str, Any]:
    """وضعیت هر کانال: ارائه‌دهندهٔ فعال + حالت پیکربندی.

    مسیر GET /integrations/status این را صدا می‌زند؛ قبلاً تابعی به این نام
    وجود نداشت و هر بار ۵۰۰ می‌داد.
    """
    from app.core.config import get_settings

    cfg = settings if settings is not None else get_settings()
    out: dict[str, Any] = {"providers": channels.status()}
    for name in (
        "sms_mode",
        "email_mode",
        "voip_mode",
        "erp_mode",
        "divar_mode",
        "telegram_mode",
        "bale_mode",
        "worker_mode",
    ):
        value = getattr(cfg, name, None)
        if value is not None:
            out[name] = value
    return out


# Singleton instance
channels = ChannelRegistry()