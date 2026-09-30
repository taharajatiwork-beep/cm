from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.permissions import PermissionCode, require_permission
from app.core.scope import DataScopeContext, apply_scope
from app.core.timeutil import as_utc, utc_now
from app.models import (
    CommunicationCase,
    Task,
    TaskAssignee,
    TaskDependency,
    TaskParticipant,
    WorkItem,
    WorkItemParticipant,
)
from app.models.enums import (
    AssignmentTargetType,
    CaseStatus,
    CaseType,
    ParticipantRole,
    Priority,
    SlaState,
    TaskRole,
    TaskStatus,
    WorkItemStatus,
)
from app.services.audit import emit_event, write_audit
from app.services.base import UNSET
from app.services.notifications import notify


class WorkService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_work_item(
        self,
        *,
        organization_id: UUID,
        title: str,
        owner_id: UUID,
        description: str | None = None,
        priority: Priority = Priority.MEDIUM,
        branch_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        customer_id: UUID | None = None,
        deadline: datetime | None = None,
        participant_ids: list[UUID] | None = None,
    ) -> WorkItem:
        wi = WorkItem(
            organization_id=organization_id,
            title=title,
            description=description,
            owner_id=owner_id,
            priority=priority,
            branch_id=branch_id,
            vehicle_id=vehicle_id,
            customer_id=customer_id,
            deadline=deadline,
            status=WorkItemStatus.OPEN,
        )
        self.db.add(wi)
        await self.db.flush()
        self.db.add(
            WorkItemParticipant(
                work_item_id=wi.id, user_id=owner_id, role=ParticipantRole.OWNER
            )
        )
        for uid in participant_ids or []:
            if uid != owner_id:
                self.db.add(
                    WorkItemParticipant(
                        work_item_id=wi.id, user_id=uid, role=ParticipantRole.MEMBER
                    )
                )
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=organization_id,
            event_type="work_item.created",
            actor_id=owner_id,
            entity_type="work_item",
            entity_id=wi.id,
            payload={"title": title},
        )
        return wi

    async def create_case(
        self,
        *,
        organization_id: UUID,
        subject: str,
        case_type: CaseType,
        created_by: UUID,
        work_item_id: UUID | None = None,
        owner_id: UUID | None = None,
        priority: Priority = Priority.MEDIUM,
        branch_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        customer_id: UUID | None = None,
        deadline: datetime | None = None,
        sla_policy_id: UUID | None = None,
    ) -> CommunicationCase:
        from sqlalchemy import func as sqlfunc

        existing = await self.db.scalar(
            select(sqlfunc.count())
            .select_from(CommunicationCase)
            .where(CommunicationCase.organization_id == organization_id)
        )
        case_number = f"C-{(existing or 0) + 1:05d}"
        case = CommunicationCase(
            case_number=case_number,
            organization_id=organization_id,
            work_item_id=work_item_id,
            type=case_type,
            subject=subject,
            status=CaseStatus.ASSIGNED if owner_id else CaseStatus.OPEN,
            priority=priority,
            created_by=created_by,
            owner_id=owner_id,
            branch_id=branch_id,
            vehicle_id=vehicle_id,
            customer_id=customer_id,
            deadline=deadline,
            sla_policy_id=sla_policy_id,
            sla_state=SlaState.ACTIVE if sla_policy_id or deadline else SlaState.NONE,
        )
        self.db.add(case)
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=organization_id,
            event_type="case.created",
            actor_id=created_by,
            entity_type="case",
            entity_id=case.id,
            payload={"case_number": case_number, "subject": subject},
        )
        if owner_id:
            await emit_event(
                self.db,
                organization_id=organization_id,
                event_type="case.assigned",
                actor_id=created_by,
                entity_type="case",
                entity_id=case.id,
                payload={"owner_id": str(owner_id)},
            )
            await notify(
                self.db,
                organization_id=organization_id,
                user_id=owner_id,
                title=f"Case {case_number} assigned",
                body=subject,
                entity_type="case",
                entity_id=case.id,
            )
        return case

    async def update_case(
        self,
        *,
        organization_id: UUID,
        case_id: UUID,
        actor_id: UUID,
        status: CaseStatus | None = None,
        owner_id: UUID | None | object = UNSET,
    ) -> CommunicationCase:
        """تغییر وضعیت/مسئول پرونده — فقط فیلدهایی که صریحاً فرستاده شده‌اند."""
        case = await self.db.get(CommunicationCase, case_id)
        if not case or case.organization_id != organization_id:
            raise ValueError("Case not found")

        events: list[tuple[str, dict[str, Any]]] = []
        if status is not None and status != case.status:
            events.append(("case.status_changed", {"from": case.status.value, "to": status.value}))
            case.status = status

        if owner_id is not UNSET and owner_id != case.owner_id:
            new_owner: UUID | None = owner_id  # type: ignore[assignment]
            events.append(("case.assigned" if new_owner else "case.unassigned", {"owner_id": str(new_owner) if new_owner else None}))
            case.owner_id = new_owner
            if new_owner and case.status == CaseStatus.OPEN:
                case.status = CaseStatus.ASSIGNED
            if new_owner:
                await notify(
                    self.db,
                    organization_id=organization_id,
                    user_id=new_owner,
                    title=f"Case {case.case_number} assigned",
                    body=case.subject,
                    entity_type="case",
                    entity_id=case.id,
                )

        for event_type, payload in events:
            await emit_event(
                self.db,
                organization_id=organization_id,
                event_type=event_type,
                actor_id=actor_id,
                entity_type="case",
                entity_id=case.id,
                payload=payload,
            )
        await self.db.flush()
        return case

    async def list_cases(
        self,
        organization_id: UUID,
        *,
        case_type: CaseType | None = None,
        status: CaseStatus | None = None,
        owner_id: UUID | None = None,
        limit: int = 50,
        scope: DataScopeContext | None = None,
    ) -> list[CommunicationCase]:
        q = (
            select(CommunicationCase)
            .where(CommunicationCase.organization_id == organization_id)
            .order_by(CommunicationCase.created_at.desc())
            .limit(limit)
        )
        q = apply_scope(q, CommunicationCase, scope)
        if case_type:
            q = q.where(CommunicationCase.type == case_type)
        if status:
            q = q.where(CommunicationCase.status == status)
        if owner_id:
            q = q.where(CommunicationCase.owner_id == owner_id)
        return list((await self.db.execute(q)).scalars().all())

    async def create_task(
        self,
        *,
        organization_id: UUID,
        title: str,
        owner_id: UUID,
        work_item_id: UUID | None = None,
        case_id: UUID | None = None,
        description: str | None = None,
        priority: Priority = Priority.MEDIUM,
        assignee_ids: list[UUID] | None = None,
        assignment_target_type: AssignmentTargetType | None = None,
        assignment_target_id: UUID | None = None,
        deadline: datetime | None = None,
        sla_policy_id: UUID | None = None,
        actor_permissions: set[str] | None = None,
    ) -> Task:
        if actor_permissions is not None:
            require_permission(actor_permissions, PermissionCode.TASK_WRITE)
        status = TaskStatus.ASSIGNED if assignee_ids else TaskStatus.OPEN
        if assignment_target_type and not assignee_ids:
            status = TaskStatus.ASSIGNED  # owned by team/dept/branch
        task = Task(
            organization_id=organization_id,
            work_item_id=work_item_id,
            case_id=case_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            owner_id=owner_id,
            assignment_target_type=assignment_target_type,
            assignment_target_id=assignment_target_id,
            deadline=deadline,
            sla_policy_id=sla_policy_id,
            sla_state=SlaState.ACTIVE if sla_policy_id or deadline else SlaState.NONE,
        )
        self.db.add(task)
        await self.db.flush()
        self.db.add(
            TaskAssignee(task_id=task.id, user_id=owner_id, role=TaskRole.OWNER)
        )
        for uid in assignee_ids or []:
            self.db.add(
                TaskAssignee(task_id=task.id, user_id=uid, role=TaskRole.ASSIGNEE)
            )
            self.db.add(
                TaskParticipant(task_id=task.id, user_id=uid, role=TaskRole.ASSIGNEE)
            )
            await notify(
                self.db,
                organization_id=organization_id,
                user_id=uid,
                title="New task assigned",
                body=title,
                entity_type="task",
                entity_id=task.id,
            )
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=organization_id,
            event_type="task.created",
            actor_id=owner_id,
            entity_type="task",
            entity_id=task.id,
            payload={"title": title, "work_item_id": str(work_item_id) if work_item_id else None},
        )
        if assignee_ids:
            await emit_event(
                self.db,
                organization_id=organization_id,
                event_type="task.assigned",
                actor_id=owner_id,
                entity_type="task",
                entity_id=task.id,
                payload={"assignee_ids": [str(u) for u in assignee_ids]},
            )
        if work_item_id:
            wi = await self.db.get(WorkItem, work_item_id)
            if wi and wi.status == WorkItemStatus.OPEN:
                wi.status = WorkItemStatus.IN_PROGRESS
        return task

    async def add_dependency(
        self, dependent_task_id: UUID, prerequisite_task_id: UUID, actor_id: UUID | None = None
    ) -> TaskDependency:
        dep = TaskDependency(
            dependent_task_id=dependent_task_id,
            prerequisite_task_id=prerequisite_task_id,
        )
        self.db.add(dep)
        dependent = await self.db.get(Task, dependent_task_id)
        if dependent and dependent.status != TaskStatus.COMPLETED:
            prereq = await self.db.get(Task, prerequisite_task_id)
            if prereq and prereq.status != TaskStatus.COMPLETED:
                dependent.status = TaskStatus.BLOCKED
        await self.db.flush()
        if dependent:
            await emit_event(
                self.db,
                organization_id=dependent.organization_id,
                event_type="task.dependency_added",
                actor_id=actor_id,
                entity_type="task",
                entity_id=dependent_task_id,
                payload={"prerequisite_task_id": str(prerequisite_task_id)},
            )
        return dep

    async def delegate_task(
        self,
        *,
        task_id: UUID,
        actor_id: UUID,
        actor_permissions: set[str],
        to_user_id: UUID | None = None,
        to_target_type: AssignmentTargetType | None = None,
        to_target_id: UUID | None = None,
    ) -> Task:
        require_permission(actor_permissions, PermissionCode.TASK_DELEGATE)
        task = await self.db.get(Task, task_id)
        if not task:
            raise ValueError("Task not found")
        if to_user_id:
            self.db.add(
                TaskAssignee(task_id=task.id, user_id=to_user_id, role=TaskRole.ASSIGNEE)
            )
            self.db.add(
                TaskParticipant(task_id=task.id, user_id=to_user_id, role=TaskRole.ASSIGNEE)
            )
            task.status = TaskStatus.ASSIGNED
            await notify(
                self.db,
                organization_id=task.organization_id,
                user_id=to_user_id,
                title="Task delegated to you",
                body=task.title,
                entity_type="task",
                entity_id=task.id,
            )
        if to_target_type and to_target_id:
            task.assignment_target_type = to_target_type
            task.assignment_target_id = to_target_id
            task.status = TaskStatus.ASSIGNED
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=task.organization_id,
            event_type="task.reassigned",
            actor_id=actor_id,
            entity_type="task",
            entity_id=task.id,
            payload={
                "to_user_id": str(to_user_id) if to_user_id else None,
                "to_target_type": to_target_type.value if to_target_type else None,
                "to_target_id": str(to_target_id) if to_target_id else None,
            },
        )
        await write_audit(
            self.db,
            organization_id=task.organization_id,
            actor_id=actor_id,
            action="task.delegate",
            entity_type="task",
            entity_id=task.id,
            details={
                "to_user_id": str(to_user_id) if to_user_id else None,
                "to_target_type": to_target_type.value if to_target_type else None,
            },
        )
        return task

    async def complete_task(self, task_id: UUID, actor_id: UUID) -> Task:
        task = await self.db.get(Task, task_id)
        if not task:
            raise ValueError("Task not found")
        # Check dependencies
        deps = await self.db.execute(
            select(TaskDependency).where(TaskDependency.dependent_task_id == task_id)
        )
        for dep in deps.scalars().all():
            prereq = await self.db.get(Task, dep.prerequisite_task_id)
            if prereq and prereq.status != TaskStatus.COMPLETED:
                raise ValueError("Cannot complete task: prerequisite not completed")
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(UTC)
        await self.db.flush()
        # Unblock dependents
        dependents = await self.db.execute(
            select(TaskDependency).where(TaskDependency.prerequisite_task_id == task_id)
        )
        for dep in dependents.scalars().all():
            dependent = await self.db.get(Task, dep.dependent_task_id)
            if dependent and dependent.status == TaskStatus.BLOCKED:
                # check all prereqs
                all_deps = await self.db.execute(
                    select(TaskDependency).where(
                        TaskDependency.dependent_task_id == dependent.id
                    )
                )
                ready = True
                for d in all_deps.scalars().all():
                    p = await self.db.get(Task, d.prerequisite_task_id)
                    if p and p.status != TaskStatus.COMPLETED:
                        ready = False
                        break
                if ready:
                    dependent.status = TaskStatus.ASSIGNED
        await emit_event(
            self.db,
            organization_id=task.organization_id,
            event_type="task.completed",
            actor_id=actor_id,
            entity_type="task",
            entity_id=task.id,
            payload={"title": task.title},
        )
        if task.owner_id != actor_id:
            await notify(
                self.db,
                organization_id=task.organization_id,
                user_id=task.owner_id,
                title="Task completed",
                body=task.title,
                entity_type="task",
                entity_id=task.id,
            )
        # Update work item progress
        if task.work_item_id:
            await self._refresh_work_item_status(task.work_item_id)
        return task

    async def _refresh_work_item_status(self, work_item_id: UUID) -> None:
        wi = await self.db.get(WorkItem, work_item_id)
        if not wi:
            return
        result = await self.db.execute(select(Task).where(Task.work_item_id == work_item_id))
        tasks = list(result.scalars().all())
        if not tasks:
            return
        if all(t.status == TaskStatus.COMPLETED for t in tasks):
            wi.status = WorkItemStatus.COMPLETED
        elif any(t.status in (TaskStatus.IN_PROGRESS, TaskStatus.ASSIGNED, TaskStatus.COMPLETED) for t in tasks):
            wi.status = WorkItemStatus.IN_PROGRESS

    async def work_item_progress(self, work_item_id: UUID) -> dict[str, Any]:
        wi = await self.db.scalar(
            select(WorkItem)
            .options(
                selectinload(WorkItem.tasks).selectinload(Task.assignees),
                selectinload(WorkItem.participants),
            )
            .where(WorkItem.id == work_item_id)
        )
        if not wi:
            raise ValueError("Work item not found")
        tasks = wi.tasks
        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        now = utc_now()
        overdue: int = sum(
            1
            for t in tasks
            if t.deadline is not None
            and t.status != TaskStatus.COMPLETED
            and (as_utc(t.deadline) or now) < now
        )
        return {
            "work_item_id": wi.id,
            "title": wi.title,
            "status": wi.status.value,
            "total_tasks": total,
            "completed_tasks": completed,
            "overdue_tasks": overdue,
            "progress_pct": round((completed / total) * 100, 1) if total else 0.0,
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status.value,
                    "deadline": t.deadline,
                    "assignment_target_type": (
                        t.assignment_target_type.value if t.assignment_target_type else None
                    ),
                    "assignment_target_id": t.assignment_target_id,
                    "assignees": [
                        {"user_id": a.user_id, "role": a.role.value} for a in t.assignees
                    ],
                }
                for t in tasks
            ],
            "participants": [
                {"user_id": p.user_id, "role": p.role.value} for p in wi.participants
            ],
        }

    async def list_work_items(
        self,
        organization_id: UUID,
        *,
        status: WorkItemStatus | None = None,
        owner_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        limit: int = 100,
        scope: DataScopeContext | None = None,
    ) -> list[WorkItem]:
        q = (
            select(WorkItem)
            .where(WorkItem.organization_id == organization_id)
            .order_by(WorkItem.created_at.desc())
            .limit(limit)
        )
        q = apply_scope(q, WorkItem, scope)
        if status:
            q = q.where(WorkItem.status == status)
        if owner_id:
            q = q.where(WorkItem.owner_id == owner_id)
        if vehicle_id:
            q = q.where(WorkItem.vehicle_id == vehicle_id)
        return list((await self.db.execute(q)).scalars().all())

    async def add_work_item_participant(
        self,
        *,
        work_item_id: UUID,
        user_id: UUID,
        role: ParticipantRole = ParticipantRole.MEMBER,
        actor_id: UUID | None = None,
    ) -> WorkItemParticipant:
        wi = await self.db.get(WorkItem, work_item_id)
        if not wi:
            raise ValueError("Work item not found")
        existing = await self.db.scalar(
            select(WorkItemParticipant).where(
                WorkItemParticipant.work_item_id == work_item_id,
                WorkItemParticipant.user_id == user_id,
            )
        )
        if existing:
            return existing
        row = WorkItemParticipant(work_item_id=work_item_id, user_id=user_id, role=role)
        self.db.add(row)
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=wi.organization_id,
            event_type="work_item.participant_added",
            actor_id=actor_id,
            entity_type="work_item",
            entity_id=work_item_id,
            payload={"user_id": str(user_id), "role": role.value},
        )
        await notify(
            self.db,
            organization_id=wi.organization_id,
            user_id=user_id,
            title="Added to work item",
            body=wi.title,
            entity_type="work_item",
            entity_id=work_item_id,
        )
        return row

    async def add_task_participant(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
        role: TaskRole = TaskRole.FOLLOWER,
        actor_id: UUID | None = None,
    ) -> TaskParticipant:
        task = await self.db.get(Task, task_id)
        if not task:
            raise ValueError("Task not found")
        existing = await self.db.scalar(
            select(TaskParticipant).where(
                TaskParticipant.task_id == task_id,
                TaskParticipant.user_id == user_id,
                TaskParticipant.role == role,
            )
        )
        if existing:
            return existing
        row = TaskParticipant(task_id=task_id, user_id=user_id, role=role)
        self.db.add(row)
        await self.db.flush()
        await emit_event(
            self.db,
            organization_id=task.organization_id,
            event_type="task.participant_added",
            actor_id=actor_id,
            entity_type="task",
            entity_id=task_id,
            payload={"user_id": str(user_id), "role": role.value},
        )
        return row

    async def list_tasks(
        self,
        organization_id: UUID,
        *,
        work_item_id: UUID | None = None,
        assignee_id: UUID | None = None,
        status: TaskStatus | None = None,
        overdue_only: bool = False,
        limit: int = 100,
        scope: DataScopeContext | None = None,
    ) -> list[Task]:
        q = (
            select(Task)
            .options(selectinload(Task.assignees))
            .where(Task.organization_id == organization_id)
            .order_by(Task.created_at.desc())
            .limit(limit)
        )
        q = apply_scope(q, Task, scope)
        if work_item_id:
            q = q.where(Task.work_item_id == work_item_id)
        if status:
            q = q.where(Task.status == status)
        if assignee_id:
            q = q.join(TaskAssignee, TaskAssignee.task_id == Task.id).where(
                TaskAssignee.user_id == assignee_id
            )
        if overdue_only:
            now = utc_now()
            # SQLite often stores naive datetimes; filter in Python for safe tz compare
            rows = list((await self.db.execute(q)).scalars().unique().all())
            return [
                t
                for t in rows
                if t.deadline
                and t.status != TaskStatus.COMPLETED
                and as_utc(t.deadline) is not None
                and as_utc(t.deadline) < now  # type: ignore[operator]
            ]
        return list((await self.db.execute(q)).scalars().unique().all())

    async def user_workload(self, user_id: UUID, *, organization_id: UUID | None = None) -> dict[str, Any]:
        open_statuses = [
            TaskStatus.OPEN,
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS,
            TaskStatus.BLOCKED,
        ]
        tasks = list(
            (
                await self.db.execute(
                    select(Task)
                    .join(TaskAssignee, TaskAssignee.task_id == Task.id)
                    .where(
                        TaskAssignee.user_id == user_id,
                        Task.status.in_(open_statuses),
                        *([Task.organization_id == organization_id] if organization_id else []),
                    )
                    .order_by(Task.created_at.desc())
                )
            )
            .scalars()
            .unique()
            .all()
        )
        now = utc_now()
        overdue = [
            t for t in tasks if t.deadline is not None and (as_utc(t.deadline) or now) < now
        ]
        wi_ids = {t.work_item_id for t in tasks if t.work_item_id}
        return {
            "user_id": user_id,
            "open_tasks": len(tasks),
            "overdue_tasks": len(overdue),
            "active_work_items": len(wi_ids),
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status.value,
                    "work_item_id": t.work_item_id,
                    "deadline": t.deadline,
                    "sla_state": t.sla_state.value,
                }
                for t in tasks
            ],
        }
