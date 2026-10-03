"""Approvals, reports, audit queries, retention, and AI quota."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.core.permissions import PermissionCode, require_permission
from app.core.timeutil import as_utc
from app.models import AuditLog, CommunicationCase, Task, User, WorkItem
from app.models.enterprise import AiUsage, ApprovalRequest, ApprovalStep, ReportSchedule, UserTeam
from app.models.enums import CaseStatus, SlaState, TaskStatus
from app.models.inventory import Vehicle
from app.models.telegram import TelegramAccount
from app.services import write_audit

log = get_logger(__name__)


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
        action: str | None = None,
        day: str | None = None,
        limit: int = 50,
    ) -> list[AuditLog]:
        if PermissionCode.ORG_ADMIN not in actor_permissions:
            require_permission(actor_permissions, PermissionCode.EVENT_READ)
        q = select(AuditLog).where(AuditLog.organization_id == organization_id)
        if actor_id:
            q = q.where(AuditLog.actor_id == actor_id)
        if entity_type:
            q = q.where(AuditLog.entity_type == entity_type)
        if action:
            q = q.where(AuditLog.action == action)
        if day:
            # day = YYYY-MM-DD (به وقت سرور) — برای فیلتر تاریخ در تب ممیزی
            try:
                start = datetime.fromisoformat(day)
            except ValueError as e:
                raise ValueError("bad day filter") from e
            if start.tzinfo is None:
                start = start.replace(tzinfo=UTC)
            end = start + timedelta(days=1)
            q = q.where(AuditLog.created_at >= start, AuditLog.created_at < end)
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
        # خود-تأییدی ممنوع: درخواست‌دهنده نباید در زنجیرهٔ تأیید خودش باشد
        if requester_id in approver_ids:
            raise ValueError("requester cannot be an approver of their own request")
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

    async def admin_overview(self, organization_id: UUID) -> dict:
        """نمای کلی ادمین — فقط خواندنی و پشت ORG_ADMIN (مرحله ۴ پلن محصول فعلی)."""
        from app.models import Branch, Conversation, Message, TaskAssignee
        from app.models.divar import DivarListing
        from app.models.enterprise import KpiSnapshot

        now = datetime.now(UTC)
        week_ago = now - timedelta(days=7)

        async def _count(model, *extra):
            q = select(func.count()).select_from(model).where(model.organization_id == organization_id)
            for cond in extra:
                q = q.where(cond)
            return int((await self.db.scalar(q)) or 0)

        # --- کاربران: فعال / غیرفعال / قفل‌شده ---
        users_total = await _count(User)
        users_active = await _count(User, User.is_active.is_(True))
        users_locked = await _count(User, User.locked_until.is_not(None), User.locked_until > now)

        # --- پیام‌های ۷ روز اخیر ---
        messages_7d = await _count(Message, Message.created_at >= week_ago)

        # --- گفتگوهای منتظر پاسخ + میانگین زمان اولین پاسخ ---
        convs = list(
            (
                await self.db.execute(
                    select(Conversation)
                    .options(selectinload(Conversation.messages))
                    .where(
                        Conversation.organization_id == organization_id,
                        Conversation.archived_at.is_(None),
                    )
                )
            ).scalars().all()
        )
        waiting_reply = 0
        first_reply_minutes: list[float] = []
        for conv in convs:
            msgs = sorted(conv.messages, key=lambda m: m.created_at or now)
            if not msgs:
                continue
            first = msgs[0]
            reply = next((m for m in msgs[1:] if m.sender_id != first.sender_id), None)
            if reply and first.created_at and reply.created_at:
                delta = reply.created_at - first.created_at
                first_reply_minutes.append(max(delta.total_seconds(), 0) / 60)
            # منتظر پاسخ: هنوز کسی جواب نداده یا آخرین دو پیام از یک نفر است.
            if len(msgs) == 1 or msgs[-1].sender_id == msgs[-2].sender_id:
                waiting_reply += 1
        avg_first_reply = (
            round(sum(first_reply_minutes) / len(first_reply_minutes), 1)
            if first_reply_minutes
            else None
        )

        # --- کارهای باز و عقب‌افتاده به تفکیک شعبه ---
        open_statuses = [TaskStatus.OPEN, TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED]
        branch_rows = (
            await self.db.execute(
                select(
                    Branch.name,
                    func.count(Task.id),
                    func.sum(
                        case((Task.deadline.is_not(None) & (Task.deadline < now), 1), else_=0)
                    ),
                )
                .select_from(Task)
                .join(WorkItem, WorkItem.id == Task.work_item_id, isouter=True)
                .join(Branch, Branch.id == WorkItem.branch_id, isouter=True)
                .where(Task.organization_id == organization_id, Task.status.in_(open_statuses))
                .group_by(Branch.name)
            )
        ).all()
        tasks_by_branch = [
            {
                "branch": name or "بدون شعبه",
                "open": int(open_count or 0),
                "overdue": int(overdue or 0),
            }
            for name, open_count, overdue in branch_rows
        ]

        # --- ۵ نفر پرکار (بیشترین کار باز) ---
        top_rows = (
            await self.db.execute(
                select(TaskAssignee.user_id, func.count(Task.id))
                .join(Task, Task.id == TaskAssignee.task_id)
                .where(Task.organization_id == organization_id, Task.status.in_(open_statuses))
                .group_by(TaskAssignee.user_id)
                .order_by(func.count(Task.id).desc())
                .limit(5)
            )
        ).all()
        top_users = []
        for user_id, cnt in top_rows:
            person = await self.db.get(User, user_id)
            top_users.append(
                {"user_id": str(user_id), "name": person.full_name if person else str(user_id)[:8], "open_tasks": int(cnt)}
            )

        # --- پرونده‌ها و SLA ---
        cases_open = await _count(
            CommunicationCase,
            CommunicationCase.status.notin_([CaseStatus.COMPLETED, CaseStatus.CANCELLED]),
        )
        cases_sla_breached = await _count(
            CommunicationCase,
            CommunicationCase.sla_state.in_([SlaState.BREACHED, SlaState.ESCALATED]),
        )

        # --- تأییدهای منتظر ---
        approvals_pending = await _count(ApprovalRequest, ApprovalRequest.status == "pending")

        # --- خودروها و خطاهای دیوار ---
        vehicle_rows = (
            await self.db.execute(
                select(Vehicle.status, func.count(Vehicle.id))
                .where(Vehicle.organization_id == organization_id)
                .group_by(Vehicle.status)
            )
        ).all()
        vehicle_counts = {str(getattr(status, "value", status)): int(cnt) for status, cnt in vehicle_rows}
        divar_errors = await _count(DivarListing, DivarListing.last_error.is_not(None))

        # --- روند ۸ هفته از kpi_snapshots ---
        snapshots = list(
            (
                await self.db.execute(
                    select(KpiSnapshot)
                    .where(KpiSnapshot.organization_id == organization_id)
                    .order_by(KpiSnapshot.created_at.desc())
                    .limit(8)
                )
            ).scalars().all()
        )
        snapshots.reverse()
        trend = [
            {
                "week": row.created_at.isocalendar()[1] if row.created_at else None,
                "date": row.created_at.date().isoformat() if row.created_at else None,
                "kpis": json.loads(row.payload_json) if row.payload_json else {},
            }
            for row in snapshots
        ]

        return {
            "users": {
                "total": users_total,
                "active": users_active,
                "inactive": users_total - users_active,
                "locked": users_locked,
            },
            "messages_7d": messages_7d,
            "conversations_waiting_reply": waiting_reply,
            "avg_first_reply_minutes": avg_first_reply,
            "tasks_by_branch": tasks_by_branch,
            "top_users": top_users,
            "cases": {"open": cases_open, "sla_breached": cases_sla_breached},
            "approvals_pending": approvals_pending,
            "vehicles": {
                "in_stock": vehicle_counts.get("IN_STOCK", 0),
                "reserved": vehicle_counts.get("RESERVED", 0),
                "sold": vehicle_counts.get("SOLD", 0),
            },
            "divar_errors": divar_errors,
            "trend": trend,
        }

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

    async def admin_analytics(self, organization_id: UUID) -> dict:
        """تحلیل‌های تفصیلی تب «تحلیل‌ها» — فقط خواندنی، پشت ORG_ADMIN.

        همهٔ سری‌های زمانی در پایتون دسته‌بندی می‌شوند تا بین SQLite و
        Postgres قابل حمل بماند (بدون strftime/to_char).
        """
        from collections import Counter

        from app.models import Conversation, Message

        now = datetime.now(UTC)
        open_statuses = [
            TaskStatus.OPEN,
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS,
            TaskStatus.BLOCKED,
        ]

        def _week_key(dt: datetime | None) -> str | None:
            if dt is None:
                return None
            iso = dt.isocalendar()
            return f"{iso[0]}-W{iso[1]:02d}"

        def _day_key(dt: datetime | None) -> str | None:
            return dt.date().isoformat() if dt else None

        # --- وظایف: ساخته‌شده/تکمیل‌شده در ۸ هفته اخیر + زمان تکمیل ---
        weeks_ago8 = now - timedelta(weeks=8)
        task_rows = (
            await self.db.execute(
                select(Task.created_at, Task.completed_at).where(
                    Task.organization_id == organization_id,
                    or_(Task.created_at >= weeks_ago8, Task.completed_at >= weeks_ago8),
                )
            )
        ).all()
        weekly: dict[str, dict[str, int]] = {}
        completion_hours_30d: list[float] = []
        month_ago = now - timedelta(days=30)
        for created_at, completed_at in task_rows:
            wk = _week_key(created_at)
            if wk:
                weekly.setdefault(wk, {"created": 0, "completed": 0})["created"] += 1
            wk2 = _week_key(completed_at)
            if wk2:
                weekly.setdefault(wk2, {"created": 0, "completed": 0})["completed"] += 1
            done = as_utc(completed_at)
            started = as_utc(created_at)
            if done and started and done >= month_ago and done >= started:
                completion_hours_30d.append((done - started).total_seconds() / 3600)
        tasks_weekly = []
        for i in range(7, -1, -1):
            key = _week_key(now - timedelta(weeks=i))
            agg = weekly.get(key or "?", {})
            tasks_weekly.append(
                {
                    "week": key,
                    "created": agg.get("created", 0),
                    "completed": agg.get("completed", 0),
                }
            )
        tasks_overdue = int(
            await self.db.scalar(
                select(func.count()).select_from(Task).where(
                    Task.organization_id == organization_id,
                    Task.status.in_(open_statuses),
                    Task.deadline.is_not(None),
                    Task.deadline < now,
                )
            )
            or 0
        )
        avg_completion_hours = (
            round(sum(completion_hours_30d) / len(completion_hours_30d), 1)
            if completion_hours_30d
            else None
        )

        # --- وظایف باز به تفکیک اولویت ---
        prio_rows = (
            await self.db.execute(
                select(Task.priority, func.count())
                .where(Task.organization_id == organization_id, Task.status.in_(open_statuses))
                .group_by(Task.priority)
            )
        ).all()
        tasks_by_priority = {
            str(getattr(p, "value", p)): int(c) for p, c in prio_rows
        }

        # --- پرونده‌ها: وضعیت / نوع / میانگین زمان حل (۹۰ روز) ---
        case_status_rows = (
            await self.db.execute(
                select(CommunicationCase.status, func.count())
                .where(CommunicationCase.organization_id == organization_id)
                .group_by(CommunicationCase.status)
            )
        ).all()
        cases_by_status = {str(getattr(s, "value", s)): int(c) for s, c in case_status_rows}
        case_type_rows = (
            await self.db.execute(
                select(CommunicationCase.type, func.count())
                .where(CommunicationCase.organization_id == organization_id)
                .group_by(CommunicationCase.type)
            )
        ).all()
        cases_by_type = {str(getattr(t, "value", t)): int(c) for t, c in case_type_rows}
        closed_rows = (
            await self.db.execute(
                select(CommunicationCase.created_at, CommunicationCase.closed_at).where(
                    CommunicationCase.organization_id == organization_id,
                    CommunicationCase.closed_at.is_not(None),
                    CommunicationCase.closed_at >= now - timedelta(days=90),
                )
            )
        ).all()
        resolution_hours = [
            (closed - created).total_seconds() / 3600
            for created, closed in closed_rows
            if closed and created and closed >= created
        ]
        avg_case_resolution_hours = (
            round(sum(resolution_hours) / len(resolution_hours), 1) if resolution_hours else None
        )

        # --- پاسخ اول گفتگوها: بازه‌ها ---
        convs = list(
            (
                await self.db.execute(
                    select(Conversation)
                    .options(selectinload(Conversation.messages))
                    .where(
                        Conversation.organization_id == organization_id,
                        Conversation.archived_at.is_(None),
                    )
                )
            ).scalars().all()
        )
        reply_buckets = {"lt5": 0, "lt30": 0, "lt120": 0, "gt120": 0, "no_reply": 0}
        for conv in convs:
            msgs = sorted(conv.messages, key=lambda m: m.created_at or now)
            if not msgs:
                continue
            first = msgs[0]
            reply = next((m for m in msgs[1:] if m.sender_id != first.sender_id), None)
            if reply is None or not first.created_at or not reply.created_at:
                reply_buckets["no_reply"] += 1
                continue
            minutes = max((reply.created_at - first.created_at).total_seconds(), 0) / 60
            if minutes < 5:
                reply_buckets["lt5"] += 1
            elif minutes < 30:
                reply_buckets["lt30"] += 1
            elif minutes < 120:
                reply_buckets["lt120"] += 1
            else:
                reply_buckets["gt120"] += 1

        # --- پیام‌ها: روزانه ۱۴ روز اخیر ---
        msgs_14d = (
            await self.db.execute(
                select(Message.created_at).where(
                    Message.organization_id == organization_id,
                    Message.created_at >= now - timedelta(days=14),
                )
            )
        ).scalars().all()
        daily: Counter[str] = Counter(_day.date().isoformat() for _day in msgs_14d if _day)
        messages_daily = []
        for i in range(13, -1, -1):
            day = (now - timedelta(days=i)).date().isoformat()
            messages_daily.append({"day": day, "count": daily.get(day, 0)})

        # --- خودروها: پیری انبار + ارزش موجودی ---
        veh_rows = (
            await self.db.execute(
                select(Vehicle.status, Vehicle.created_at, Vehicle.sale_price, Vehicle.purchase_price)
                .where(Vehicle.organization_id == organization_id)
            )
        ).all()
        aging = {"lt7": 0, "lt30": 0, "lt90": 0, "gt90": 0}
        value_by_status: dict[str, int] = {}
        for status, created_at, sale_price, purchase_price in veh_rows:
            key = str(getattr(status, "value", status))
            est = int(sale_price or purchase_price or 0)
            value_by_status[key] = value_by_status.get(key, 0) + est
            if key == "IN_STOCK" and created_at:
                days = (now - as_utc(created_at)).days
                if days < 7:
                    aging["lt7"] += 1
                elif days < 30:
                    aging["lt30"] += 1
                elif days < 90:
                    aging["lt90"] += 1
                else:
                    aging["gt90"] += 1

        # --- ممیزی: روزانه ۷ روز + پرتکرارترین اقدام‌ها + ورود ناموفق ---
        audit_rows = (
            await self.db.execute(
                select(AuditLog.action, AuditLog.created_at).where(
                    AuditLog.organization_id == organization_id,
                    AuditLog.created_at >= now - timedelta(days=7),
                )
            )
        ).all()
        audit_daily: Counter[str] = Counter()
        action_counts: Counter[str] = Counter()
        login_failed_7d = 0
        for action, created_at in audit_rows:
            audit_day = _day_key(created_at)
            if audit_day:
                audit_daily[audit_day] += 1
            action_counts[action] += 1
            if action == "auth.login_failed":
                login_failed_7d += 1
        audit_daily_7d = []
        for i in range(6, -1, -1):
            day = (now - timedelta(days=i)).date().isoformat()
            audit_daily_7d.append({"day": day, "count": audit_daily.get(day, 0)})
        top_actions = [
            {"action": a, "count": int(c)} for a, c in action_counts.most_common(6)
        ]

        return {
            "tasks_weekly": tasks_weekly,
            "tasks_overdue": tasks_overdue,
            "avg_completion_hours": avg_completion_hours,
            "tasks_by_priority": tasks_by_priority,
            "cases_by_status": cases_by_status,
            "cases_by_type": cases_by_type,
            "avg_case_resolution_hours": avg_case_resolution_hours,
            "reply_buckets": reply_buckets,
            "messages_daily": messages_daily,
            "vehicles_aging": aging,
            "vehicles_value_by_status": value_by_status,
            "audit_daily_7d": audit_daily_7d,
            "top_actions": top_actions,
            "login_failed_7d": login_failed_7d,
        }

    async def admin_monitoring(self, organization_id: UUID) -> dict:
        """مانیتورینگ سلامت سیستم — فقط خواندنی، پشت ORG_ADMIN."""
        from sqlalchemy import text

        from app.core.config import get_settings
        from app.integrations.channels import channel_status
        from app.models import Event, Message
        from app.models.enterprise import JobLock
        from app.models.telegram import TelegramOutbox
        from app.services.audit import verify_audit_chain

        now = datetime.now(UTC)

        # --- دیتابیس: حجم و journal (فقط SQLite؛ در بقیه None) ---
        db_size_bytes: int | None = None
        journal_mode: str | None = None
        try:
            page_count = int(
                (await self.db.execute(text("PRAGMA page_count"))).scalar() or 0
            )
            page_size = int(
                (await self.db.execute(text("PRAGMA page_size"))).scalar() or 0
            )
            journal_mode = str(
                (await self.db.execute(text("PRAGMA journal_mode"))).scalar() or ""
            )
            db_size_bytes = page_count * page_size
        except Exception as exc:  # noqa: BLE001, S110 — postgres این PRAGMAها را ندارد
            log.debug("monitoring_db_pragma_unavailable", error=str(exc))

        async def _count(model, *extra) -> int:  # noqa: ANN001
            q = select(func.count()).select_from(model).where(
                model.organization_id == organization_id
            )
            for cond in extra:
                q = q.where(cond)
            return int((await self.db.scalar(q)) or 0)

        table_counts = {
            "users": await _count(User),
            "tasks": await _count(Task),
            "work_items": await _count(WorkItem),
            "messages": await _count(Message),
            "cases": await _count(CommunicationCase),
            "vehicles": await _count(Vehicle),
            "audit_logs": await _count(AuditLog),
            "events": await _count(Event),
        }

        # --- صف خروجی تلگرام ---
        ob_rows = (
            await self.db.execute(
                select(TelegramOutbox.status, func.count())
                .where(TelegramOutbox.organization_id == organization_id)
                .group_by(TelegramOutbox.status)
            )
        ).all()
        outbox_counts = {str(s): int(c) for s, c in ob_rows}
        oldest_pending: datetime | None = await self.db.scalar(
            select(func.min(TelegramOutbox.created_at)).where(
                TelegramOutbox.organization_id == organization_id,
                TelegramOutbox.status == "pending",
            )
        )
        oldest_pending_minutes = (
            int((now - as_utc(oldest_pending)).total_seconds() // 60) if oldest_pending else None
        )
        failed_samples = [
            {"provider": row.provider, "error": (row.last_error or "")[:160], "at": str(row.created_at or "")}
            for row in (
                await self.db.execute(
                    select(TelegramOutbox)
                    .where(
                        TelegramOutbox.organization_id == organization_id,
                        TelegramOutbox.status == "failed",
                    )
                    .order_by(TelegramOutbox.created_at.desc())
                    .limit(3)
                )
            ).scalars().all()
        ]

        # --- قفل‌های jobها (سراسری) — منقضی = ورکر مرده/ریست‌شده ---
        locks = list((await self.db.execute(select(JobLock))).scalars().all())
        job_locks = [
            {
                "name": lk.name,
                "owner": lk.owner,
                "expires_at": lk.expires_at.isoformat() if lk.expires_at else None,
                "stale": bool(lk.expires_at and as_utc(lk.expires_at) < now),
            }
            for lk in locks
        ]

        # --- رویدادهای ۲۴ ساعت اخیر به تفکیک نوع ---
        ev_rows = (
            await self.db.execute(
                select(Event.event_type, func.count())
                .where(
                    Event.organization_id == organization_id,
                    Event.created_at >= now - timedelta(hours=24),
                )
                .group_by(Event.event_type)
                .order_by(func.count().desc())
                .limit(6)
            )
        ).all()
        events_24h = [{"type": str(t), "count": int(c)} for t, c in ev_rows]

        # --- احراز هویت ۲۴ ساعت ---
        auth_failed_24h = int(
            await self.db.scalar(
                select(func.count()).select_from(AuditLog).where(
                    AuditLog.organization_id == organization_id,
                    AuditLog.action == "auth.login_failed",
                    AuditLog.created_at >= now - timedelta(hours=24),
                )
            )
            or 0
        )

        # --- یکپارچگی زنجیرهٔ ممیزی (بازمحاسبهٔ کامل) ---
        try:
            chain = await verify_audit_chain(self.db, organization_id)
        except Exception as exc:  # noqa: BLE001 — مانیتورینگ نباید 500 بدهد
            chain = {"ok": None, "rows_checked": 0, "broken_at": None, "detail": str(exc)[:160]}

        integrations = channel_status(get_settings())

        return {
            "database": {
                "size_bytes": db_size_bytes,
                "journal_mode": journal_mode,
                "table_counts": table_counts,
            },
            "outbox": {
                "by_status": outbox_counts,
                "oldest_pending_minutes": oldest_pending_minutes,
                "failed_samples": failed_samples,
            },
            "job_locks": job_locks,
            "events_24h": events_24h,
            "auth_failed_24h": auth_failed_24h,
            "audit_chain": chain,
            "integrations": integrations,
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
