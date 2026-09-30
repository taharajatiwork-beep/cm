"""Tests for channel adapters — fake implementations by default."""

import pytest

from app.integrations.channels import (
    ChannelRegistry,
    DeliveryResult,
    FakeEmailAdapter,
    FakeErpAdapter,
    FakeSmsAdapter,
    FakeVoipAdapter,
    get_divar_adapter,
    get_email_adapter,
    get_erp_adapter,
    get_sms_adapter,
    get_voip_adapter,
)


class TestRealAdapters:
    """Real adapters talk HTTP only when configured. Tests use a fake client."""

    @pytest.mark.asyncio
    async def test_kavenegar_posts(self, monkeypatch):
        seen = {}

        class Dummy:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, url, data=None, json=None):
                seen["url"] = url
                seen["data"] = data

                class Response:
                    status_code = 200
                    text = "ok"

                return Response()

        monkeypatch.setattr("app.integrations.channels.httpx.AsyncClient", Dummy)
        from app.integrations.channels import KavenegarSmsAdapter

        result = await KavenegarSmsAdapter(api_key="test-key", sender="1000").send(
            "09120000000", "سلام"
        )
        assert result.ok is True
        assert "send.json" in seen["url"]
        assert seen["data"]["receptor"] == "09120000000"

    @pytest.mark.asyncio
    async def test_erp_reads_inventory(self, monkeypatch):
        class Dummy:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, url, headers=None):
                class Response:
                    status_code = 200

                    def raise_for_status(self):
                        return None

                    def json(self):
                        return [{"sku": "1"}]

                return Response()

        monkeypatch.setattr("app.integrations.channels.httpx.AsyncClient", Dummy)
        from app.integrations.channels import HttpErpAdapter

        rows = await HttpErpAdapter(api_base="http://erp.test", api_token="t").fetch_inventory()
        assert rows == [{"sku": "1"}]

    @pytest.mark.asyncio
    async def test_divar_retries_then_records_error(self, monkeypatch):
        calls = {"n": 0}

        class Dummy:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def request(self, method, url, headers=None, **kwargs):
                calls["n"] += 1

                class Response:
                    status_code = 500
                    text = "upstream down"

                return Response()

        monkeypatch.setattr("app.integrations.divar.client.httpx.AsyncClient", Dummy)
        from app.integrations.divar.client import HttpDivarClient

        client = HttpDivarClient(base_url="http://divar.test", token="t")
        with pytest.raises(ValueError):
            await client.create_task("p1")
        assert calls["n"] == 3
        assert client.last_error == "upstream down"


class TestFakeAdapters:
    """All fake adapters should work without configuration."""

    @pytest.mark.asyncio
    async def test_fake_sms_returns_delivery_result(self):
        adapter = FakeSmsAdapter()
        result = await adapter.send("09123456789", "Test message")
        assert isinstance(result, DeliveryResult)
        assert result.ok is True
        assert result.provider == "fake"
        assert "09123456789" in result.detail

    @pytest.mark.asyncio
    async def test_fake_email_returns_delivery_result(self):
        adapter = FakeEmailAdapter()
        result = await adapter.send("test@example.com", "Subject", "Body")
        assert isinstance(result, DeliveryResult)
        assert result.ok is True
        assert result.provider == "fake"

    @pytest.mark.asyncio
    async def test_fake_voip_returns_delivery_result(self):
        adapter = FakeVoipAdapter()
        result = await adapter.click_to_call("100", "09123456789")
        assert isinstance(result, DeliveryResult)
        assert result.ok is True
        assert result.provider == "fake"

    @pytest.mark.asyncio
    async def test_fake_erp_returns_empty_list(self):
        adapter = FakeErpAdapter()
        result = await adapter.fetch_inventory()
        assert result == []


class TestAdapterFactories:
    """Factory functions should return fake adapters by default."""

    def test_get_sms_adapter_returns_fake_by_default(self, monkeypatch):
        monkeypatch.setenv("SMS_PROVIDER", "fake")
        monkeypatch.setenv("SMS_API_KEY", "")
        from app.core.config import get_settings
        get_settings.cache_clear()
        adapter = get_sms_adapter()
        assert type(adapter).__name__ == "FakeSmsAdapter"

    def test_get_email_adapter_returns_fake_by_default(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "")
        from app.core.config import get_settings
        get_settings.cache_clear()
        adapter = get_email_adapter()
        assert type(adapter).__name__ == "FakeEmailAdapter"

    def test_get_voip_adapter_returns_fake_by_default(self, monkeypatch):
        monkeypatch.setenv("VOIP_MODE", "fake")
        monkeypatch.setenv("VOIP_AMI_URL", "")
        from app.core.config import get_settings
        get_settings.cache_clear()
        adapter = get_voip_adapter()
        assert type(adapter).__name__ == "FakeVoipAdapter"

    def test_get_erp_adapter_returns_fake_by_default(self, monkeypatch):
        monkeypatch.setenv("ERP_MODE", "fake")
        monkeypatch.setenv("ERP_API_BASE", "")
        monkeypatch.setenv("ERP_API_TOKEN", "")
        from app.core.config import get_settings
        get_settings.cache_clear()
        adapter = get_erp_adapter()
        assert type(adapter).__name__ == "FakeErpAdapter"

    def test_get_divar_adapter_returns_fake_by_default(self, monkeypatch):
        monkeypatch.setenv("DIVAR_MODE", "off")
        from app.core.config import get_settings
        get_settings.cache_clear()
        adapter = get_divar_adapter()
        # Should be FakeDivarClient
        assert "Fake" in type(adapter).__name__


class TestChannelRegistry:
    """ChannelRegistry provides unified access."""

    def test_registry_status_all_fake(self, monkeypatch):
        monkeypatch.setenv("SMS_PROVIDER", "fake")
        monkeypatch.setenv("SMTP_HOST", "")
        monkeypatch.setenv("VOIP_MODE", "fake")
        monkeypatch.setenv("ERP_MODE", "fake")
        monkeypatch.setenv("DIVAR_MODE", "off")
        from app.core.config import get_settings
        get_settings.cache_clear()
        
        registry = ChannelRegistry()
        status = registry.status()
        assert status["sms"] == "FakeSmsAdapter"
        assert status["email"] == "FakeEmailAdapter"
        assert status["voip"] == "FakeVoipAdapter"
        assert status["erp"] == "FakeErpAdapter"
        assert "Fake" in status["divar"]

    @pytest.mark.asyncio
    async def test_registry_sms_send(self, monkeypatch):
        monkeypatch.setenv("SMS_PROVIDER", "fake")
        from app.core.config import get_settings
        get_settings.cache_clear()
        
        registry = ChannelRegistry()
        result = await registry.sms.send("09123456789", "Test")
        assert result.ok is True
        assert result.provider == "fake"

    @pytest.mark.asyncio
    async def test_registry_email_send(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "")
        from app.core.config import get_settings
        get_settings.cache_clear()
        
        registry = ChannelRegistry()
        result = await registry.email.send("test@example.com", "Subject", "Body")
        assert result.ok is True
        assert result.provider == "fake"


class TestRealAdaptersRequireConfig:
    """Real adapters should fail gracefully when not configured."""

    @pytest.mark.asyncio
    async def test_kavenegar_without_key_returns_error(self):
        from app.integrations.channels import KavenegarSmsAdapter
        adapter = KavenegarSmsAdapter(api_key=None)
        result = await adapter.send("09123456789", "Test")
        assert result.ok is False
        assert result.provider == "kavenegar"

    @pytest.mark.asyncio
    async def test_smtp_without_host_returns_error(self):
        from app.integrations.channels import SmtpEmailAdapter
        adapter = SmtpEmailAdapter(host=None)
        result = await adapter.send("test@example.com", "Subject", "Body")
        assert result.ok is False
        assert result.provider == "smtp"

    @pytest.mark.asyncio
    async def test_asterisk_without_url_returns_error(self):
        from app.integrations.channels import AsteriskVoipAdapter
        adapter = AsteriskVoipAdapter(ami_url=None)
        result = await adapter.click_to_call("100", "09123456789")
        assert result.ok is False
        assert result.provider == "asterisk"