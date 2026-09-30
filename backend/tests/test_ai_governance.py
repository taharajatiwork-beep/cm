"""Tests for AI Governance — human approval for sensitive tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai.governance import (
    SENSITIVE_TOOLS,
    is_ai_governance_enabled,
    is_sensitive_tool,
    request_ai_approval,
)
from app.ai.tools import ToolContext, ToolExecutor, TOOL_SPECS


class TestAIGovernanceFlags:
    """Test governance flag detection."""

    def test_is_sensitive_tool_known(self):
        assert is_sensitive_tool("create_case") is True
        assert is_sensitive_tool("create_task") is True
        assert is_sensitive_tool("create_work_item") is True
        assert is_sensitive_tool("assign_task") is True
        assert is_sensitive_tool("search_inventory") is False
        assert is_sensitive_tool("get_vehicle") is False

    def test_sensitive_tools_subset_of_specs(self):
        """All sensitive tools must be defined in TOOL_SPECS."""
        for tool in SENSITIVE_TOOLS:
            assert tool in TOOL_SPECS, f"SENSITIVE_TOOLS contains unknown tool: {tool}"

    def test_is_ai_governance_enabled_default_false(self, monkeypatch):
        monkeypatch.setenv("REQUIRE_HUMAN_APPROVAL_FOR_SENSITIVE_AI", "false")
        from app.core.config import get_settings
        get_settings.cache_clear()
        assert is_ai_governance_enabled() is False


class TestToolExecutorGovernance:
    """ToolExecutor should request approval for sensitive tools when flag is enabled."""

    @pytest.mark.asyncio
    async def test_execute_requests_approval_for_sensitive_tool(self, seeded, db, monkeypatch):
        from app.core.permissions import PermissionCode

        monkeypatch.setenv("REQUIRE_HUMAN_APPROVAL_FOR_SENSITIVE_AI", "true")
        from app.core.config import get_settings
        get_settings.cache_clear()

        ali = seeded["ali"]
        # ali در فیکسچر مدیر ندارد؛ سناریوی معتبر: مدیرش را تعیین می‌کنیم
        ali.manager_id = seeded["sara"].id
        db.add(ali)
        await db.flush()

        ctx = ToolContext(
            db=db,
            organization_id=seeded["org"].id,
            user=ali,
            permissions={PermissionCode.WORK_ITEM_WRITE, PermissionCode.TASK_ASSIGN},
            request_id="test-req-123",
        )
        executor = ToolExecutor(ctx)

        # Mock the approval request
        with patch("app.ai.tools.request_ai_approval", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = MagicMock(id="approval-123")
            result = await executor.execute("create_work_item", {"title": "Test item"})

        assert result["ok"] is True
        assert result["data"]["status"] == "pending_approval"
        assert "approval_id" in result["data"]

    @pytest.mark.asyncio
    async def test_execute_no_approval_when_disabled(self, seeded, db, monkeypatch):
        from app.core.permissions import PermissionCode

        monkeypatch.setenv("REQUIRE_HUMAN_APPROVAL_FOR_SENSITIVE_AI", "false")
        from app.core.config import get_settings
        get_settings.cache_clear()

        ctx = ToolContext(
            db=db,
            organization_id=seeded["org"].id,
            user=seeded["ali"],
            permissions={PermissionCode.WORK_ITEM_WRITE, PermissionCode.TASK_ASSIGN},
            request_id="test-req-456",
        )
        executor = ToolExecutor(ctx)

        # Should execute normally, not request approval
        with patch("app.ai.tools.request_ai_approval", new_callable=AsyncMock) as mock_req:
            result = await executor.execute("create_work_item", {"title": "Test item"})

        assert result["ok"] is True
        assert "id" in result["data"]  # actual work item created
        assert result["data"]["title"] == "Test item"
        mock_req.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_no_approval_for_read_tools(self, seeded, db, monkeypatch):
        """Read-only tools should not trigger approval even when governance is on."""
        from app.core.permissions import PermissionCode

        monkeypatch.setenv("REQUIRE_HUMAN_APPROVAL_FOR_SENSITIVE_AI", "true")
        from app.core.config import get_settings
        get_settings.cache_clear()

        ctx = ToolContext(
            db=db,
            organization_id=seeded["org"].id,
            user=seeded["ali"],
            permissions={PermissionCode.INVENTORY_READ},
            request_id="test-req-789",
        )
        executor = ToolExecutor(ctx)

        with patch("app.ai.tools.request_ai_approval", new_callable=AsyncMock) as mock_req:
            result = await executor.execute("search_inventory", {"q": "Camry"})

        assert result["ok"] is True
        mock_req.assert_not_called()


class TestGovernanceHelperFunctions:
    """Test request_ai_approval and related helpers."""

    @pytest.mark.asyncio
    async def test_request_ai_approval_creates_record(self, seeded, db):
        row = await request_ai_approval(
            db,
            organization_id=seeded["org"].id,
            requester_id=seeded["ali"].id,
            tool_name="create_case",
            title="Test Case",
            payload={"subject": "Test"},
            approver_ids=[seeded["reza"].id],
        )
        assert row is not None
        assert hasattr(row, "id")

    @pytest.mark.asyncio
    async def test_check_ai_approval(self, seeded, db):
        from app.ai.governance import check_ai_approval

        # Create approval request first
        row = await request_ai_approval(
            db,
            organization_id=seeded["org"].id,
            requester_id=seeded["ali"].id,
            tool_name="create_case",
            title="Test Case",
            payload={"subject": "Test"},
            approver_ids=[seeded["reza"].id],
        )
        
        # Check status (should be pending)
        status = await check_ai_approval(db, row.id, seeded["reza"].id)
        assert status["status"] == "pending"


class TestAiQuotaAndEvals:
    @pytest.mark.asyncio
    async def test_daily_quota_blocks(self, db, seeded, monkeypatch):
        monkeypatch.setenv("AI_DAILY_TOKEN_QUOTA", "10")
        from app.core.config import get_settings
        from app.services.enterprise_ops import EnterpriseService

        get_settings.cache_clear()
        try:
            svc = EnterpriseService(db)
            with pytest.raises(PermissionError):
                await svc.record_ai_usage(
                    seeded["org"].id, seeded["ali"].id, "test", 8, 8
                )
        finally:
            monkeypatch.delenv("AI_DAILY_TOKEN_QUOTA", raising=False)
            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_rules_planner_evals(self, db, seeded):
        from app.ai.evals import evaluate_rules

        rows = await evaluate_rules(db, seeded["org"].id)
        assert len(rows) >= 5
        failed = [row["text"] for row in rows if not row["ok"]]
        assert failed == []