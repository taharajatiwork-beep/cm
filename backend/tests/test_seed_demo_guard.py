import pytest


@pytest.mark.asyncio
async def test_seed_refuses_production(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    from scripts import seed_demo

    with pytest.raises(RuntimeError, match="production"):
        await seed_demo.seed()
    get_settings.cache_clear()
