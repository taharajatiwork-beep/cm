"""خود-تأییدی ممنوع — درخواست‌دهنده نباید بتواند خودش را تأییدکننده کند.

ریشهٔ باگ: ai/tools.py برای کاربری که مدیر ندارد، خودِ او را به‌عنوان
تأییدکننده می‌گذاشت (`else [self.ctx.user.id]`) و حاکمیت AI را بی‌اثر می‌کرد.
همچنین POST /approvals فهرست approver_ids را از کلاینت می‌گرفت و
هیچ بررسی‌ای روی آن نمی‌کرد.

چیدمان فیکسچر: ali = مدیر (بدون manager_id)، reza = فروشنده با manager_id=ali،
admin_role = نقش با همهٔ مجوزها از جمله org.admin.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai.tools import ToolContext, ToolExecutor
from app.core.permissions import PermissionCode
from app.services.enterprise_ops import EnterpriseService


def _work_perms() -> set[str]:
    # همان مجوزهایی که تست موجودِ حاکمیت AI استفاده می‌کند
    return {PermissionCode.WORK_ITEM_WRITE, PermissionCode.TASK_ASSIGN}


class TestRequesterCannotBeApprover:
    """سرویس باید خود-تأییدی را رد کند."""

    @pytest.mark.asyncio
    async def test_service_rejects_requester_in_approver_ids(self, seeded, db):
        svc = EnterpriseService(db)
        ali = seeded["ali"]

        with pytest.raises(ValueError, match="cannot be an approver"):
            await svc.request_approval(
                organization_id=seeded["org"].id,
                requester_id=ali.id,
                kind="discount",
                title="تخفیف ویژه",
                payload={"amount": 100},
                approver_ids=[ali.id],
            )

    @pytest.mark.asyncio
    async def test_service_rejects_requester_anywhere_in_chain(self, seeded, db):
        """درخواست‌دهنده در هیچ مرحله‌ای از زنجیره نباید باشد."""
        svc = EnterpriseService(db)
        ali = seeded["ali"]
        reza = seeded["reza"]

        with pytest.raises(ValueError, match="cannot be an approver"):
            await svc.request_approval(
                organization_id=seeded["org"].id,
                requester_id=ali.id,
                kind="discount",
                title="تخفیف",
                payload={},
                approver_ids=[reza.id, ali.id],
            )

    @pytest.mark.asyncio
    async def test_other_approver_is_allowed(self, seeded, db):
        """رفتار عادی نباید بشکند — درخواست‌دهنده ≠ تأییدکننده."""
        svc = EnterpriseService(db)
        ali = seeded["ali"]
        reza = seeded["reza"]

        row = await svc.request_approval(
            organization_id=seeded["org"].id,
            requester_id=ali.id,
            kind="discount",
            title="تخفیف",
            payload={},
            approver_ids=[reza.id],
        )
        assert row.requester_id == ali.id


class TestPostApprovalsEndpoint:
    """مسیر HTTP هم باید ۴۰۰ بدهد، نه اینکه رد شود."""

    @pytest.mark.asyncio
    async def test_api_rejects_self_approval(self, seeded, client):
        from tests.conftest import auth, login

        ali = seeded["ali"]
        headers = auth(await login(client, "ali@autoco.example"))
        r = await client.post(
            "/approvals",
            headers=headers,
            json={
                "kind": "discount",
                "title": "تخفیف",
                "payload": {},
                "approver_ids": [str(ali.id)],
            },
        )
        assert r.status_code == 400, r.text
        assert "approver" in r.text


class TestToolExecutorApproverResolution:
    """ابزارهای AI حساس نباید به خودِ کاربر برسند."""

    @pytest.mark.asyncio
    async def test_falls_back_to_org_admin_not_self(self, seeded, db, monkeypatch):
        monkeypatch.setenv("REQUIRE_HUMAN_APPROVAL_FOR_SENSITIVE_AI", "true")
        from app.core.config import get_settings
        get_settings.cache_clear()

        from app.services import OrgService

        ali = seeded["ali"]
        # ali مدیر است و manager_id ندارد → باید به ادمین سازمان برسد.
        # در فیکسچر کاربری با نقش admin وجود ندارد، پس یکی می‌سازیم.
        admin = await OrgService(db).create_user(
            organization_id=seeded["org"].id,
            email="root@autoco.example",
            full_name="Org Admin",
            password="password",
            role_id=seeded["admin_role"].id,
            branch_id=seeded["branch"].id,
        )
        ali.manager_id = None
        db.add(ali)
        await db.flush()

        ctx = ToolContext(
            db=db,
            organization_id=seeded["org"].id,
            user=ali,
            permissions=_work_perms(),
            request_id="req-self-approval",
        )
        executor = ToolExecutor(ctx)

        with patch("app.ai.tools.request_ai_approval", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = MagicMock(id="ap-1")
            await executor.execute("create_work_item", {"title": "کار جدید"})

        assert mock_req.await_count == 1
        kwargs = (mock_req.await_args.kwargs if mock_req.await_args else {}) or {}
        approver_ids = kwargs.get("approver_ids", [])
        assert ali.id not in approver_ids, "کاربر نباید تأییدکنندهٔ عملیات خودش باشد"
        assert admin.id in approver_ids, "باید به ادمین سازمان ارجاع شود"

    @pytest.mark.asyncio
    async def test_prefers_manager_when_present(self, seeded, db, monkeypatch):
        monkeypatch.setenv("REQUIRE_HUMAN_APPROVAL_FOR_SENSITIVE_AI", "true")
        from app.core.config import get_settings
        get_settings.cache_clear()

        reza = seeded["reza"]
        ali = seeded["ali"]
        assert reza.manager_id == ali.id  # چیدمان فیکسچر

        ctx = ToolContext(
            db=db,
            organization_id=seeded["org"].id,
            user=reza,
            permissions=_work_perms(),
            request_id="req-mgr",
        )
        executor = ToolExecutor(ctx)

        with patch("app.ai.tools.request_ai_approval", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = MagicMock(id="ap-2")
            await executor.execute("create_work_item", {"title": "کار جدید"})

        kwargs = (mock_req.await_args.kwargs if mock_req.await_args else {}) or {}
        approver_ids = kwargs.get("approver_ids", [])
        assert approver_ids == [ali.id]

    @pytest.mark.asyncio
    async def test_refuses_when_no_approver_exists(self, seeded, db, monkeypatch):
        """نه مدیر، نه ادمین → باید رد شود، نه خودکار اجرا."""
        monkeypatch.setenv("REQUIRE_HUMAN_APPROVAL_FOR_SENSITIVE_AI", "true")
        from app.core.config import get_settings
        get_settings.cache_clear()

        ali = seeded["ali"]
        ali.manager_id = None
        db.add(ali)
        await db.flush()

        ctx = ToolContext(
            db=db,
            organization_id=seeded["org"].id,
            user=ali,
            permissions=_work_perms(),
            request_id="req-none",
        )
        executor = ToolExecutor(ctx)

        with patch.object(executor, "_org_admin_ids", new_callable=AsyncMock) as mock_admins:
            mock_admins.return_value = []
            result = await executor.execute("create_work_item", {"title": "کار جدید"})

        assert result.get("ok") is False, result
        assert "تأییدکننده" in str(result)
