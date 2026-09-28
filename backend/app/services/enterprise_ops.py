"""Approvals, reports, audit queries, retention, and AI quota."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import PermissionCode, require_permission
from app.models import AuditLog, CommunicationCase, Task, User, WorkItem
from app.models.enums import TaskStatus
from app.models.enterprise import AiUsage, ApprovalRequest, ApprovalStep, ReportSchedule, UserTeam
from app.models.inventory import Vehicle
from app.models.telegram import TelegramAccount
from app.services import write_audit


async def notify_current_approver(db: AsyncSession, approval: ApprovalRequest) -> None:
    """Queue an inline «تأیید»/«رد» message to the current step approver.

    Only when the requester has a linked Telegram account. Delivery goes through
    the existing outbox — never a direct send from the API request.
    """
    from app.integrations.telegram.callbacks import encode_approval_callback
    from app.integrations.telegram.messages import btn_approve, btn_reject, notify_approval
    from app.integrations.telegram.outbox import enqueue_telegram

    requester_linked = await db.scalar(
        select(TelegramAccount).where(
            TelegramAccount.user_id == approval.requester_id,
            TelegramAccount.disabled_at.is_(None),
            TelegramAccount.telegram_chat_id.is_not(None),
        )
    )
    if not requester_linked:
        return
    step = await db.scalar(
        select(ApprovalStep).where(
            ApprovalStep.request_id == approval.id,
            ApprovalStep.step_no == approval.current_step,
        )
    )
    if not step:
        return
    await enqueue_telegram(
        db,
        organization_id=approval.organization_id,
        user_id=step.approver_id,
        event_type="approval",
        text=notify_approval(approval.title),
        entity_type="approval",
        entity_id=approval.id,
        buttons=[
            [
                {"text": btn_approve(), "callback_data": encode_approval_callback("approve", approval.id)},
                {"text": btn_reject(), "callback_data": encode_approval_callback("reject", approval.id)},
            ]
        ],
    )


class EnterpriseService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_audit(
        self,
        organization_id: UUID,
        *,
        actor_permissions: set[str],
        actor_id: UUID | None = None,
        entity_type: str | None = None,
        limit: int = 50,
    ) -> list[AuditLog]:
        if PermissionCode.ORG_ADMIN not in actor_permissions:
            require_permission(actor_permissions, PermissionCode.EVENT_READ)
        q = select(AuditLog).where(AuditLog.organization_id == organization_id)
        if actor_id:
            q = q.where(AuditLog.actor_id == actor_id)
        if entity_type:
            q = q.where(AuditLog.entity_type == entity_type)
        q = q.order_by(AuditLog.created_at.desc()).limit(limit)
        return list((await self.db.execute(q)).scalars().all())

    async def request_approval(
        self,
        *,
        organization_id: UUID,
        requester_id: UUID,
        kind: str,
        title: str,
        payload: dict,
        approver_ids: list[UUID],
    ) -> ApprovalRequest:
        row = ApprovalRequest(
            organization_id=organization_id,
            kind=kind,
            title=title,
            payload_json=json.dumps(payload),
            requester_id=requester_id,
        )
        self.db.add(row)
        await self.db.flush()
        for i, approver_id in enumerate(approver_ids, start=1):
            self.db.add(ApprovalStep(request_id=row.id, step_no=i, approver_id=approver_id))
        await write_audit(
            self.db,
            organization_id=organization_id,
            actor_id=requester_id,
            action="approval.requested",
            entity_type="approval",
            entity_id=row.id,
            details={"kind": kind},
        )
        await self.db.flush()
        return row

    async def decide(
        self,
        *,
        organization_id: UUID,
        request_id: UUID,
        actor_id: UUID,
        decision: str,
        comment: str | None = None,
    ) -> ApprovalRequest:
        row = await self.db.get(ApprovalRequest, request_id)
        if not row or row.organization_id != organization_id:
            raise ValueError("Approval not found")
        if row.status != "pending":
            raise ValueError("Approval already decided")
        step = await self.db.scalar(
            select(ApprovalStep).where(
                ApprovalStep.request_id == row.id,
                ApprovalStep.step_no == row.current_step,
            )
        )
        if not step or step.approver_id != actor_id:
            raise ValueError("Not the current approver")
        step.decision = decision
        step.comment = comment
        step.decided_at = datetime.now(UTC)
        if decision == "rejected":
            row.status = "rejected"
            row.decided_at = datetime.now(UTC)
        else:
            nxt = await self.db.scalar(
                select(ApprovalStep).where(
                    ApprovalStep.request_id == row.id,
                    ApprovalStep.step_no == row.current_step + 1,
                )
            )
            if nxt:
                row.current_step += 1
            else:
                row.status = "approved"
                row.decided_at = datetime.now(UTC)
        await write_audit(
            self.db,
            organization_id=organization_id,
            actor_id=actor_id,
            action=f"approval.{decision}",
            entity_type="approval",
            entity_id=row.id,
        )
        await self.db.flush()
        return row

    async def kpis(self, organization_id: UUID) -> dict:
        open_tasks = await self.db.scalar(
            select(func.count()).select_from(Task).where(
                Task.organization_id == organization_id,
                Task.status.notin_([TaskStatus.COMPLETED, TaskStatus.CANCELLED]),
            )
        )
        vehicles = await self.db.scalar(
            select(func.count()).select_from(Vehicle).where(Vehicle.organization_id == organization_id)
        )
        cases = await self.db.scalar(
            select(func.count()).select_from(CommunicationCase).where(
                CommunicationCase.organization_id == organization_id
            )
        )
        work_items = await self.db.scalar(
            select(func.count()).select_from(WorkItem).where(WorkItem.organization_id == organization_id)
        )
        return {
            "open_tasks": int(open_tasks or 0),
            "vehicles": int(vehicles or 0),
            "cases": int(cases or 0),
            "work_items": int(work_items or 0),
        }

    async def add_team_membership(self, organization_id: UUID, user_id: UUID, team_id: UUID) -> UserTeam:
        user = await self.db.get(User, user_id)
        if not user or user.organization_id != organization_id:
            raise ValueError("User not found")
        row = UserTeam(organization_id=organization_id, user_id=user_id, team_id=team_id)
        self.db.add(row)
        await self.db.flush()
        return row

    async def schedule_report(self, organization_id: UUID, name: str, channel: str, hour_utc: int) -> ReportSchedule:
        row = ReportSchedule(
            organization_id=organization_id, name=name, channel=channel, hour_utc=hour_utc
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def record_ai_usage(
        self, organization_id: UUID, user_id: UUID, model: str, prompt_tokens: int, completion_tokens: int
    ) -> None:
        from app.core.config import get_settings

        settings = get_settings()
        start = datetime.now(UTC) - timedelta(days=1)
        used = await self.db.scalar(
            select(func.coalesce(func.sum(AiUsage.prompt_tokens + AiUsage.completion_tokens), 0)).where(
                AiUsage.user_id == user_id, AiUsage.created_at >= start
            )
        )
        incoming = prompt_tokens + completion_tokens
        if int(used or 0) + incoming > settings.ai_daily_token_quota:
            raise PermissionError("AI daily quota exceeded")
        self.db.add(
            AiUsage(
                organization_id=organization_id,
                user_id=user_id,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        )
        await self.db.flush()

    async def get_approval_status(self, approval_id: UUID, actor_id: UUID) -> dict:
        """Get the current status of an approval request."""
        row = await self.db.get(ApprovalRequest, approval_id)
        if not row:
            return {"status": "not_found"}
        if row.organization_id != row.organization_id:
            return {"status": "not_found"}
        
        steps = list(
            (await self.db.execute(
                select(ApprovalStep).where(ApprovalStep.request_id == row.id).order_by(ApprovalStep.step_no)
            )).scalars().all()
        )
        
        current_step = None
        if row.current_step <= len(steps):
            current_step = steps[row.current_step - 1]
        
        return {
            "status": row.status,
            "kind": row.kind,
            "title": row.title,
            "current_step": row.current_step,
            "total_steps": len(steps),
            "current_approver_id": str(current_step.approver_id) if current_step else None,
            "is_current_approver": current_step.approver_id == actor_id if current_step else False,
            "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        }
