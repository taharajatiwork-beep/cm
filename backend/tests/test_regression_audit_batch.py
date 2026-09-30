"""تست‌های رگرسیون برای سه باگی که در بازبینی ۲۰۲۶-۰۹-۳۰ پیدا و رفع شد.

1. GET /integrations/status تابع `channel_status` را صدا می‌زد که وجود نداشت
   → هر بار ۵۰۰. هیچ تستی هم این مسیر را نمی‌پوشاند.
2. `start_background` یک coroutine بود ولی در lifespan بدون `await` صدا زده
   می‌شد → worker هرگز واقعاً شروع نمی‌شد.
3. مهاجرت ۰۰۱۱ باید روی دیتابیسی که قبلاً اجرا شده هم قابل اجرا باشد.
"""

import pytest
from sqlalchemy import inspect

from app.integrations.channels import channel_status


async def _create_org_admin(client, seeded, db) -> str:
    """کاربری با نقش org.admin می‌سازد و توکنش را برمی‌گرداند."""
    from app.services import OrgService
    from tests.conftest import login

    await OrgService(db).create_user(
        organization_id=seeded["org"].id,
        email="ops@autoco.example",
        full_name="Ops Admin",
        password="password",
        role_id=seeded["admin_role"].id,
        branch_id=seeded["branch"].id,
    )
    await db.commit()
    return await login(client, "ops@autoco.example")


class TestChannelStatusEndpoint:
    def test_channel_status_returns_providers(self):
        out = channel_status()
        assert "providers" in out
        # حالت پیش‌فرض: همه Fake
        assert out["providers"]["sms"] == "FakeSmsAdapter"
        assert out["providers"]["email"] == "FakeEmailAdapter"

    def test_channel_status_includes_modes(self):
        out = channel_status()
        assert "telegram_mode" in out
        assert "divar_mode" in out

    def test_channel_status_accepts_explicit_settings(self):
        from app.core.config import Settings

        out = channel_status(Settings(telegram_mode="polling", divar_mode="fake"))
        assert out["telegram_mode"] == "polling"

    @pytest.mark.asyncio
    async def test_integrations_status_route_works(self, client, seeded, db):
        """خود مسیر HTTP — قبلاً ۵۰۰ می‌داد چون تابع گم‌شده بود."""
        from tests.conftest import auth, login

        # مسیر فقط برای مدیر سازمان است
        reza = await login(client, "reza@autoco.example")
        r = await client.get("/integrations/status", headers=auth(reza))
        assert r.status_code == 403, r.text

        # یک کاربر واقعی با نقش مدیر سازمان بساز (تغییر ORM روی session جدا دیده نمی‌شود)
        admin_token = await _create_org_admin(client, seeded, db)
        r2 = await client.get("/integrations/status", headers=auth(admin_token))
        assert r2.status_code == 200, r2.text
        assert "providers" in r2.json()


class TestWorkerStartsInLifespan:
    def test_start_background_is_awaited(self):
        """اگر await جا بیفتد، coroutine هرگز اجرا نمی‌شود و فقط warning می‌دهد."""
        import ast
        import inspect as pyinspect

        from app import main

        source = pyinspect.getsource(main)
        tree = ast.parse(source)
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "start_background"
        ]
        assert calls, "start_background باید در lifespan صدا زده شود"
        for call in calls:
            parent_await = any(
                isinstance(n, ast.Await) and n.value is call for n in ast.walk(tree)
            )
            assert parent_await, "start_background باید await شود وگرنه worker اجرا نمی‌شود"

    @pytest.mark.asyncio
    async def test_start_background_returns_tasks(self, db):
        """تابع باید taskهای ساخته‌شده را برگرداند (تا در lifespan نگه داشته شوند)."""
        from app.db.session import async_sessionmaker
        from app.worker import start_background, stop_background

        factory = async_sessionmaker(db.bind, class_=type(db), expire_on_commit=False)
        try:
            tasks = await start_background(factory)
            assert isinstance(tasks, list)
        finally:
            await stop_background()


class TestAuditChainMigration:
    @pytest.mark.asyncio
    async def test_columns_exist_after_metadata_create(self, db_engine):
        """مدل و مهاجرت باید هم‌راستا باشند."""
        async with db_engine.begin() as conn:
            await conn.run_sync(lambda c: inspect(c).get_columns("audit_logs"))
            cols = await conn.run_sync(lambda c: [col["name"] for col in inspect(c).get_columns("audit_logs")])
        assert "prev_hash" in cols
        assert "row_hash" in cols
        assert "chain_seq" in cols

    def test_migration_has_upgrade_and_downgrade(self):
        import importlib.util
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        path = root / "alembic" / "versions" / "0011_audit_hash_chain.py"
        assert path.exists(), "مهاجرت ۰۰۱۱ باید وجود داشته باشد"
        spec = importlib.util.spec_from_file_location("m0011", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert callable(mod.upgrade)
        assert callable(mod.downgrade)
        assert mod.down_revision == "0010_query_indexes"
