from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CommunicationCase, SlaPolicy, Task, User
from app.models.enums import CaseStatus, NotificationChannel, Priority, SlaState, TaskStatus
from app.services.audit import emit_event
from app.services.notifications import notify


class SlaService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_policy(
        self,
        *,
        organization_id: UUID,
        name: str,
        priority: Priority,
        response_minutes: int,
        warning_minutes: int,
        escalate_on_breach: bool = True,
    ) -> SlaPolicy:
        policy = SlaPolicy(
            organization_id=organization_id,
            name=name,
            priority=priority,
            response_minutes=response_minutes,
            warning_minutes=warning_minutes,
            escalate_on_breach=escalate_on_breach,
        )
        self.db.add(policy)
        await self.db.flush()
        return policy

    async def evaluate_task(self, task_id: UUID, now: datetime | None = None) -> Task:
        now = now or datetime.now(UTC)
        task = await self.db.get(Task, task_id)
        if not task:
            raise ValueError("Task not found")
        if task.status == TaskStatus.COMPLETED or task.sla_state == SlaState.NONE:
            return task

        deadline = task.deadline
        warning_at = None
        if task.sla_policy_id:
            policy = await self.db.get(SlaPolicy, task.sla_policy_id)
            if policy:
                from datetime import timedelta

                created = task.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                from app.core.config import get_settings

                if get_settings().sla_use_business_calendar:
                    from app.core.calendar import add_business_minutes, to_business_time

                    # یا از policy ساخته می‌شود یا از deadline موجود؛ در هر دو حالت
                    # روی تقویم کاری (شنبه تا پنجشنبه ۸ تا ۱۷، بدون تعطیلات) جابه‌جا می‌شود.
                    deadline = deadline or add_business_minutes(created, policy.response_minutes)
                    deadline = to_business_time(deadline)
                    warning_at = add_business_minutes(created, policy.warning_minutes)
                    # جابه‌جایی را ذخیره می‌کنیم تا در گزارش‌ها و UI هم دیده شود (پشت پرچم،
                    # پیش‌فرض false است و رفتار بدون تقویم دست نمی‌خورد).
                    task.deadline = deadline
                else:
                    deadline = deadline or (created + timedelta(minutes=policy.response_minutes))
                    warning_at = created + timedelta(minutes=policy.warning_minutes)

        if deadline and deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)

        prev = task.sla_state
        if deadline and now >= deadline:
            task.sla_state = SlaState.BREACHED
            if task.sla_policy_id:
                policy = await self.db.get(SlaPolicy, task.sla_policy_id)
                if policy and policy.escalate_on_breach:
                    task.sla_state = SlaState.ESCALATED
                    await emit_event(
                        self.db,
                        organization_id=task.organization_id,
                        event_type="sla.breached",
                        entity_type="task",
                        entity_id=task.id,
                    )
                    await emit_event(
                        self.db,
                        organization_id=task.organization_id,
                        event_type="sla.escalated",
                        entity_type="task",
                        entity_id=task.id,
                    )
                    await notify(
                        self.db,
                        organization_id=task.organization_id,
                        user_id=task.owner_id,
                        title="SLA breached — escalated",
                        body=task.title,
                        channel=NotificationChannel.SYSTEM,
                        entity_type="task",
                        entity_id=task.id,
                    )
                    from app.core.config import get_settings as _sla_settings

                    if _sla_settings().sla_chain_escalation and task.owner_id:
                        owner = await self.db.get(User, task.owner_id)
                        if owner and owner.manager_id:
                            await notify(
                                self.db,
                                organization_id=task.organization_id,
                                user_id=owner.manager_id,
                                title="SLA escalated to you",
                                body=task.title,
                                channel=NotificationChannel.SYSTEM,
                                entity_type="task",
                                entity_id=task.id,
                            )
            elif prev != SlaState.BREACHED:
                await emit_event(
                    self.db,
                    organization_id=task.organization_id,
                    event_type="sla.breached",
                    entity_type="task",
                    entity_id=task.id,
                )
                await notify(
                    self.db,
                    organization_id=task.organization_id,
                    user_id=task.owner_id,
                    title="SLA breached",
                    body=task.title,
                    channel=NotificationChannel.SYSTEM,
                    entity_type="task",
                    entity_id=task.id,
                )
        elif warning_at and now >= warning_at and task.sla_state == SlaState.ACTIVE:
            task.sla_state = SlaState.WARNING
            await emit_event(
                self.db,
                organization_id=task.organization_id,
                event_type="sla.warning",
                entity_type="task",
                entity_id=task.id,
            )
            await notify(
                self.db,
                organization_id=task.organization_id,
                user_id=task.owner_id,
                title="SLA warning",
                body=task.title,
                channel=NotificationChannel.SYSTEM,
                entity_type="task",
                entity_id=task.id,
            )
        await self.db.flush()
        return task

    async def evaluate_case(self, case_id: UUID, now: datetime | None = None) -> CommunicationCase:
        now = now or datetime.now(UTC)
        case = await self.db.get(CommunicationCase, case_id)
        if not case:
            raise ValueError("Case not found")
        if case.status in (CaseStatus.COMPLETED, CaseStatus.CANCELLED) or case.sla_state == SlaState.NONE:
            return case
        deadline = case.deadline
        warning_at = None
        if case.sla_policy_id:
            policy = await self.db.get(SlaPolicy, case.sla_policy_id)
            if policy:
                from datetime import timedelta

                created = case.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                deadline = deadline or (created + timedelta(minutes=policy.response_minutes))
                warning_at = created + timedelta(minutes=policy.warning_minutes)
        if deadline and deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
        if deadline and now >= deadline:
            case.sla_state = SlaState.BREACHED
            case.status = CaseStatus.ESCALATED
            await emit_event(
                self.db,
                organization_id=case.organization_id,
                event_type="case.escalated",
                entity_type="case",
                entity_id=case.id,
            )
            if case.owner_id:
                await notify(
                    self.db,
                    organization_id=case.organization_id,
                    user_id=case.owner_id,
                    title=f"پیگیری {case.case_number} — مهلت SLA گذشت",
                    body=case.subject,
                    channel=NotificationChannel.SYSTEM,
                    entity_type="case",
                    entity_id=case.id,
                )
        elif warning_at and now >= warning_at and case.sla_state == SlaState.ACTIVE:
            case.sla_state = SlaState.WARNING
            await emit_event(
                self.db,
                organization_id=case.organization_id,
                event_type="sla.warning",
                entity_type="case",
                entity_id=case.id,
            )
        await self.db.flush()
        return case
