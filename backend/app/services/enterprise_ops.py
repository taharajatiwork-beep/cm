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


def _sid(value: UUID | None) -> str | None:
    return str(value) if value else None


def _ref(
    title: str,
    entity_type: str,
    entity_id: UUID | None,
    *,
    work_item_id: UUID | None = None,
    conversation_id: UUID | None = None,
    detail: str = "",
) -> dict:
    return {
        "title": ((title or "").strip()[:120] or entity_type),
        "detail": (detail or "")[:80],
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "work_item_id": _sid(work_item_id),
        "conversation_id": str(conversation_id) if conversation_id else None,
    }


def _push(bucket: dict[str, list], key: str, item: dict, limit: int = 200) -> None:
    rows = bucket.setdefault(key, [])
    if len(rows) < limit:
        rows.append(item)


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

    async def admin_messages(
        self,
        organization_id: UUID,
        *,
        days: int = 7,
        q: str = "",
        channel: str = "",
        day: str = "",
    ) -> list[dict]:
        """پیام‌های اخیر برای پنجرهٔ «نمایش بیشتر» — متن، فرستنده، موضوع و لینک گفتگو."""
        from app.models import Conversation, Message
        from app.models.enums import Channel

        span = max(1, min(days, 30))
        since = datetime.now(UTC) - timedelta(days=span)
        wanted: Channel | None = None
        if channel:
            try:
                wanted = Channel(channel)
            except ValueError:
                return []
        stmt = (
            select(
                Message.id,
                Message.text,
                Message.created_at,
                Message.channel,
                Message.conversation_id,
                User.full_name,
                Conversation.topic,
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .outerjoin(User, User.id == Message.sender_id)
            .where(
                Message.organization_id == organization_id,
                Message.created_at >= since,
            )
            .order_by(Message.created_at.desc())
            .limit(300)
        )
        if wanted is not None:
            stmt = stmt.where(Message.channel == wanted)
        rows = (await self.db.execute(stmt)).all()
        needle = q.strip().lower()
        out: list[dict] = []
        for mid, text, created_at, msg_channel, conversation_id, sender, topic in rows:
            when = created_at.isoformat() if created_at else ""
            if day and not when.startswith(day):
                continue
            body = " ".join((text or "").split())
            topic_text = (topic or "").strip()
            blob = f"{body} {topic_text} {sender or ''}".lower()
            if needle and needle not in blob:
                continue
            out.append(
                {
                    "id": str(mid),
                    "text": body[:240],
                    "at": when,
                    "channel": str(getattr(msg_channel, "value", msg_channel)),
                    "conversation_id": str(conversation_id),
                    "sender": sender or "",
                    "topic": topic_text,
                }
            )
        return out

    async def admin_records(
        self,
        organization_id: UUID,
        *,
        kind: str,
        days: int = 7,
        group: str = "",
    ) -> list[dict]:
        """ردیف‌های پشت عددها و نمودارهایی که هنوز فهرست ندارند."""
        from app.models import Branch, Conversation, Event, Message, TaskAssignee
        from app.models.divar import DivarListing
        from app.models.telegram import TelegramOutbox

        span = max(1, min(days, 90))
        now = datetime.now(UTC)
        since = now - timedelta(days=span)
        open_statuses = [
            TaskStatus.OPEN,
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS,
            TaskStatus.BLOCKED,
        ]

        def _enum(value: object) -> str:
            return str(getattr(value, "value", value) or "")

        def _when(value: datetime | None) -> str:
            return value.isoformat() if value else ""

        def _row(
            title: str,
            entity_type: str,
            entity_id: UUID | None,
            *,
            detail: str = "",
            work_item_id: UUID | None = None,
            conversation_id: UUID | None = None,
            at: str = "",
            facets: dict[str, str] | None = None,
        ) -> dict:
            return {
                "title": (title or "").strip()[:160] or entity_type,
                "detail": (detail or "").strip()[:160],
                "entity_type": entity_type,
                "entity_id": str(entity_id) if entity_id else None,
                "work_item_id": _sid(work_item_id),
                "conversation_id": str(conversation_id) if conversation_id else None,
                "at": at,
                "facets": facets or {},
            }

        async def _names(ids: set[UUID]) -> dict[UUID, str]:
            if not ids:
                return {}
            found = (
                await self.db.execute(select(User.id, User.full_name).where(User.id.in_(ids)))
            ).all()
            return {uid: name for uid, name in found}

        if kind == "users":
            people = list(
                (
                    await self.db.execute(
                        select(User).where(User.organization_id == organization_id).order_by(User.full_name)
                    )
                ).scalars().all()
            )
            out: list[dict] = []
            for person in people[:300]:
                locked = person.locked_until is not None and (as_utc(person.locked_until) or now) > now
                status = "locked" if locked else "active" if person.is_active else "inactive"
                out.append(
                    _row(
                        person.full_name,
                        "user",
                        person.id,
                        detail=person.email or "",
                        facets={"user_status": status},
                    )
                )
            return out

        if kind in {"waiting", "replies"}:
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
            out = []
            for conv in convs:
                msgs = sorted(conv.messages, key=lambda m: m.created_at or now)
                if not msgs:
                    continue
                topic = (conv.topic or "").strip() or "گفتگو"
                last = " ".join((msgs[-1].text or "").split())[:80]
                if kind == "waiting":
                    if not (len(msgs) == 1 or msgs[-1].sender_id == msgs[-2].sender_id):
                        continue
                    out.append(
                        _row(
                            topic,
                            "conversation",
                            conv.id,
                            detail=last,
                            conversation_id=conv.id,
                            at=_when(msgs[-1].created_at),
                            facets={"state": "waiting"},
                        )
                    )
                    continue
                first = msgs[0]
                reply = next((m for m in msgs[1:] if m.sender_id != first.sender_id), None)
                if reply and first.created_at and reply.created_at:
                    start = as_utc(first.created_at)
                    end = as_utc(reply.created_at)
                    minutes = (
                        max((end - start).total_seconds(), 0) / 60
                        if start is not None and end is not None
                        else 0
                    )
                    bucket = (
                        "lt5" if minutes < 5 else "lt30" if minutes < 30 else "lt120" if minutes < 120 else "gt120"
                    )
                    detail = f"{round(minutes, 1)} min"
                else:
                    bucket = "no_reply"
                    detail = last
                out.append(
                    _row(
                        topic,
                        "conversation",
                        conv.id,
                        detail=detail,
                        conversation_id=conv.id,
                        at=_when(first.created_at),
                        facets={"bucket": bucket},
                    )
                )
            return out[:300]

        if kind in {"cases_open", "cases_sla", "cases_closed"}:
            stmt = select(CommunicationCase).where(CommunicationCase.organization_id == organization_id)
            if kind == "cases_open":
                stmt = stmt.where(
                    CommunicationCase.status.notin_([CaseStatus.COMPLETED, CaseStatus.CANCELLED])
                )
            elif kind == "cases_sla":
                stmt = stmt.where(
                    CommunicationCase.sla_state.in_([SlaState.BREACHED, SlaState.ESCALATED])
                )
            else:
                stmt = stmt.where(CommunicationCase.closed_at.is_not(None), CommunicationCase.closed_at >= since)
            cases = list((await self.db.execute(stmt.order_by(CommunicationCase.created_at.desc()).limit(300))).scalars().all())
            owner_ids = {row.owner_id for row in cases if row.owner_id}
            owners = await _names(owner_ids)
            out = []
            for case in cases:
                hours = ""
                if kind == "cases_closed" and case.closed_at and case.created_at:
                    start = as_utc(case.created_at)
                    end = as_utc(case.closed_at)
                    if start is not None and end is not None:
                        hours = f"{round(max((end - start).total_seconds(), 0) / 3600, 1)} h"
                owner = owners.get(case.owner_id, "") if case.owner_id else ""
                out.append(
                    _row(
                        case.subject,
                        "case",
                        case.id,
                        detail=hours or owner,
                        work_item_id=case.work_item_id,
                        facets={
                            "case_status": _enum(case.status),
                            "case_type": _enum(case.type),
                            "sla": _enum(case.sla_state),
                        },
                    )
                )
            return out

        if kind == "approvals":
            rows = list(
                (
                    await self.db.execute(
                        select(ApprovalRequest)
                        .where(
                            ApprovalRequest.organization_id == organization_id,
                            ApprovalRequest.status == "pending",
                        )
                        .order_by(ApprovalRequest.created_at.desc())
                        .limit(300)
                    )
                ).scalars().all()
            )
            names = await _names({row.requester_id for row in rows})
            return [
                _row(
                    row.title,
                    "approval",
                    row.id,
                    detail=names.get(row.requester_id, ""),
                    at=_when(row.created_at),
                    facets={"kind": row.kind},
                )
                for row in rows
            ]

        if kind == "divar":
            rows = list(
                (
                    await self.db.execute(
                        select(DivarListing)
                        .where(
                            DivarListing.organization_id == organization_id,
                            DivarListing.last_error.is_not(None),
                        )
                        .order_by(DivarListing.updated_at.desc())
                        .limit(300)
                    )
                ).scalars().all()
            )
            return [
                _row(
                    row.title,
                    "vehicle",
                    row.vehicle_id,
                    detail=" ".join((row.last_error or "").split())[:160],
                    work_item_id=row.work_item_id,
                    facets={"divar_status": row.status or ""},
                )
                for row in rows
            ]

        if kind == "vehicles":
            rows = list(
                (
                    await self.db.execute(
                        select(Vehicle)
                        .where(Vehicle.organization_id == organization_id)
                        .order_by(Vehicle.created_at.desc())
                        .limit(300)
                    )
                ).scalars().all()
            )
            out = []
            for vehicle in rows:
                price = vehicle.sale_price if vehicle.sale_price is not None else vehicle.purchase_price
                label = f"{vehicle.brand} {vehicle.model}"
                if vehicle.stock_number:
                    label = f"{label} #{vehicle.stock_number}"
                out.append(
                    _row(
                        label,
                        "vehicle",
                        vehicle.id,
                        detail=f"{price:,}" if price is not None else "",
                        facets={"vehicle_status": _enum(vehicle.status)},
                    )
                )
            return out

        if kind == "tasks":
            mode = group or "branch"
            task_rows = list(
                (
                    await self.db.execute(
                        select(Task.id, Task.title, Task.priority, Task.deadline, Task.work_item_id, Branch.name)
                        .join(WorkItem, WorkItem.id == Task.work_item_id, isouter=True)
                        .join(Branch, Branch.id == WorkItem.branch_id, isouter=True)
                        .where(Task.organization_id == organization_id, Task.status.in_(open_statuses))
                        .order_by(Task.deadline.asc().nulls_last())
                        .limit(300)
                    )
                ).all()
            )
            assignees: dict[UUID, list[str]] = {}
            if task_rows:
                links = (
                    await self.db.execute(
                        select(TaskAssignee.task_id, User.full_name)
                        .join(User, User.id == TaskAssignee.user_id)
                        .where(TaskAssignee.task_id.in_([row[0] for row in task_rows]))
                    )
                ).all()
                for task_id, name in links:
                    people = assignees.setdefault(task_id, [])
                    if name not in people:
                        people.append(name)
            out = []
            for task_id, title, priority, deadline, work_item_id, branch_name in task_rows:
                due = as_utc(deadline)
                overdue = due is not None and due < now
                if mode == "overdue" and not overdue:
                    continue
                people = assignees.get(task_id) or ["—"]
                branch = branch_name or "بدون شعبه"
                if mode == "assignee":
                    for person in people:
                        out.append(
                            _row(
                                title,
                                "task",
                                task_id,
                                detail=branch,
                                work_item_id=work_item_id,
                                facets={"assignee": person, "overdue": "yes" if overdue else "no"},
                            )
                        )
                    continue
                out.append(
                    _row(
                        title,
                        "task",
                        task_id,
                        detail="، ".join(people),
                        work_item_id=work_item_id,
                        facets={
                            "branch": branch,
                            "priority": _enum(priority),
                            "overdue": "yes" if overdue else "no",
                        },
                    )
                )
            return out

        if kind == "tasks_done":
            rows = list(
                (
                    await self.db.execute(
                        select(Task.id, Task.title, Task.priority, Task.created_at, Task.completed_at, Task.work_item_id)
                        .where(
                            Task.organization_id == organization_id,
                            Task.completed_at.is_not(None),
                            Task.completed_at >= since,
                        )
                        .order_by(Task.completed_at.desc())
                        .limit(300)
                    )
                ).all()
            )
            out = []
            for task_id, title, priority, created_at, completed_at, work_item_id in rows:
                start = as_utc(created_at)
                end = as_utc(completed_at)
                hours = ""
                if start is not None and end is not None:
                    hours = f"{round(max((end - start).total_seconds(), 0) / 3600, 1)} h"
                out.append(
                    _row(
                        title,
                        "task",
                        task_id,
                        detail=hours,
                        work_item_id=work_item_id,
                        at=_when(completed_at),
                        facets={"priority": _enum(priority)},
                    )
                )
            return out

        if kind in {"logins", "audit"}:
            stmt = select(AuditLog.action, AuditLog.entity_type, AuditLog.entity_id, AuditLog.actor_id, AuditLog.created_at).where(
                AuditLog.organization_id == organization_id,
                AuditLog.created_at >= since,
            )
            if kind == "logins":
                stmt = stmt.where(AuditLog.action == "auth.login_failed")
            logs = list((await self.db.execute(stmt.order_by(AuditLog.created_at.desc()).limit(300))).all())
            names = await _names({actor for _, _, _, actor, _ in logs if actor})
            described = await self._describe_entities(
                organization_id, [(entity_type, entity_id) for _, entity_type, entity_id, _, _ in logs]
            )
            out = []
            for action, entity_type, entity_id, actor_id, created_at in logs:
                info = described.get((entity_type.lower(), str(entity_id)), {})
                day = created_at.date().isoformat() if created_at else ""
                title = info.get("title") or action
                if kind == "logins":
                    title = names.get(actor_id, title) if actor_id else title
                out.append(
                    _row(
                        str(title),
                        entity_type,
                        entity_id,
                        detail=names.get(actor_id, "") if actor_id and kind == "audit" else action,
                        work_item_id=UUID(info["work_item_id"]) if info.get("work_item_id") else None,
                        at=_when(created_at),
                        facets={"action": action, "day": day},
                    )
                )
            return out

        if kind == "outbox":
            rows = list(
                (
                    await self.db.execute(
                        select(TelegramOutbox)
                        .where(
                            TelegramOutbox.organization_id == organization_id,
                            TelegramOutbox.status.in_(["failed", "pending"]),
                        )
                        .order_by(TelegramOutbox.created_at.desc())
                        .limit(300)
                    )
                ).scalars().all()
            )
            described = await self._describe_entities(
                organization_id, [(row.entity_type, row.entity_id) for row in rows]
            )
            names = await _names({row.user_id for row in rows})
            out = []
            for row in rows:
                info = described.get(((row.entity_type or "").lower(), str(row.entity_id)), {})
                preview = " ".join((row.text or "").split())[:120]
                out.append(
                    _row(
                        str(info.get("title") or preview or row.event_type),
                        row.entity_type or "message",
                        row.entity_id,
                        detail=(row.last_error or preview or "")[:160],
                        work_item_id=UUID(info["work_item_id"]) if info.get("work_item_id") else None,
                        conversation_id=row.conversation_id,
                        at=_when(row.created_at),
                        facets={
                            "outbox_status": row.status,
                            "recipient": names.get(row.user_id, ""),
                        },
                    )
                )
            return out

        if kind == "events":
            rows = list(
                (
                    await self.db.execute(
                        select(Event)
                        .where(Event.organization_id == organization_id, Event.created_at >= since)
                        .order_by(Event.created_at.desc())
                        .limit(300)
                    )
                ).scalars().all()
            )
            described = await self._describe_entities(
                organization_id, [(row.entity_type, row.entity_id) for row in rows]
            )
            out = []
            for event in rows:
                info = described.get((event.entity_type.lower(), str(event.entity_id)), {})
                out.append(
                    _row(
                        str(info.get("title") or event.event_type),
                        event.entity_type,
                        event.entity_id,
                        detail=event.event_type,
                        work_item_id=UUID(info["work_item_id"]) if info.get("work_item_id") else None,
                        at=_when(event.created_at),
                        facets={"event": event.event_type},
                    )
                )
            return out

        raise ValueError(f"unknown admin record kind: {kind}")

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

    async def _describe_entities(
        self, organization_id: UUID, refs: list[tuple[str | None, UUID | None]]
    ) -> dict[tuple[str, str], dict[str, str | None]]:
        """عنوان قابل‌خواندن هر موجودیت، به‌همراه پروژهٔ والد اگر باشد."""
        from app.models import Conversation
        from app.models.customer import Customer

        buckets: dict[str, set[UUID]] = {}
        for raw_type, raw_id in refs:
            if not raw_type or raw_id is None:
                continue
            buckets.setdefault(raw_type.lower(), set()).add(raw_id)

        found: dict[tuple[str, str], dict[str, str | None]] = {}

        async def _take(kind: str, model, label_of) -> None:  # noqa: ANN001
            ids = buckets.get(kind)
            if not ids:
                return
            rows: list = list(
                (
                    await self.db.execute(
                        select(model).where(
                            model.organization_id == organization_id,
                            model.id.in_(ids),
                        )
                    )
                ).scalars().all()
            )
            for row in rows:
                title, parent = label_of(row)
                found[(kind, str(row.id))] = {"title": title, "work_item_id": _sid(parent)}

        await _take("work_item", WorkItem, lambda row: (row.title, None))
        await _take("task", Task, lambda row: (row.title, row.work_item_id))
        await _take("case", CommunicationCase, lambda row: (row.subject, row.work_item_id))
        await _take("conversation", Conversation, lambda row: (row.topic or "گفتگو", row.work_item_id))
        await _take(
            "vehicle",
            Vehicle,
            lambda row: (f"{row.brand} {row.model}" + (f" #{row.stock_number}" if row.stock_number else ""), None),
        )
        await _take("customer", Customer, lambda row: (row.full_name, None))
        await _take("user", User, lambda row: (row.full_name, None))
        return found

    async def _needs_attention(
        self,
        organization_id: UUID,
        now: datetime,
        open_statuses: list,
        no_reply_threads: list[dict],
    ) -> list[dict]:
        """نمونه‌های واقعی پشت عددها: کار عقب‌افتاده، گفتگوی بی‌پاسخ، پروندهٔ نقض SLA."""
        overdue = (
            await self.db.execute(
                select(Task.id, Task.title, Task.work_item_id, Task.owner_id)
                .where(
                    Task.organization_id == organization_id,
                    Task.status.in_(open_statuses),
                    Task.deadline.is_not(None),
                    Task.deadline < now,
                )
                .order_by(Task.deadline.asc())
                .limit(6)
            )
        ).all()
        breached = (
            await self.db.execute(
                select(CommunicationCase.id, CommunicationCase.subject, CommunicationCase.work_item_id, CommunicationCase.owner_id)
                .where(
                    CommunicationCase.organization_id == organization_id,
                    CommunicationCase.sla_state == SlaState.BREACHED,
                    CommunicationCase.status.notin_([CaseStatus.COMPLETED, CaseStatus.CANCELLED]),
                )
                .limit(4)
            )
        ).all()
        owner_ids = {row.owner_id for row in overdue if row.owner_id} | {
            row.owner_id for row in breached if row.owner_id
        }
        names: dict[UUID, str] = {}
        if owner_ids:
            name_rows = (
                await self.db.execute(
                    select(User.id, User.full_name).where(User.id.in_(owner_ids))
                )
            ).all()
            names = {uid: name for uid, name in name_rows}
        parent_ids = {row.work_item_id for row in list(overdue) + list(breached) if row.work_item_id}
        parents: dict[UUID, str] = {}
        if parent_ids:
            parent_rows = (
                await self.db.execute(
                    select(WorkItem.id, WorkItem.title).where(WorkItem.id.in_(parent_ids))
                )
            ).all()
            parents = {wid: title for wid, title in parent_rows}

        items: list[dict] = []
        for row in overdue:
            items.append(
                {
                    "kind": "task",
                    "title": row.title,
                    "detail": names.get(row.owner_id, ""),
                    "context": parents.get(row.work_item_id, "") if row.work_item_id else "",
                    "entity_type": "task",
                    "entity_id": str(row.id),
                    "work_item_id": _sid(row.work_item_id),
                    "conversation_id": None,
                }
            )
        items.extend(no_reply_threads)
        for case_row in breached:
            items.append(
                {
                    "kind": "case",
                    "title": case_row.subject,
                    "detail": names.get(case_row.owner_id, "") if case_row.owner_id else "",
                    "context": "مهلت پرونده گذشته",
                    "entity_type": "case",
                    "entity_id": str(case_row.id),
                    "work_item_id": _sid(case_row.work_item_id),
                    "conversation_id": None,
                }
            )
        return items[:12]

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
                select(Task.id, Task.title, Task.work_item_id, Task.created_at, Task.completed_at).where(
                    Task.organization_id == organization_id,
                    or_(Task.created_at >= weeks_ago8, Task.completed_at >= weeks_ago8),
                )
            )
        ).all()
        weekly: dict[str, dict[str, int]] = {}
        week_created: dict[str, list] = {}
        week_completed: dict[str, list] = {}
        completion_hours_30d: list[float] = []
        month_ago = now - timedelta(days=30)
        for task_id, title, work_item_id, created_at, completed_at in task_rows:
            wk = _week_key(created_at)
            if wk:
                weekly.setdefault(wk, {"created": 0, "completed": 0})["created"] += 1
                _push(week_created, wk, _ref(title, "task", task_id, work_item_id=work_item_id))
            wk2 = _week_key(completed_at)
            if wk2:
                weekly.setdefault(wk2, {"created": 0, "completed": 0})["completed"] += 1
                _push(week_completed, wk2, _ref(title, "task", task_id, work_item_id=work_item_id, detail="انجام‌شده"))
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
        priority_items: dict[str, list] = {}
        open_task_rows = (
            await self.db.execute(
                select(Task.id, Task.title, Task.priority, Task.work_item_id).where(
                    Task.organization_id == organization_id,
                    Task.status.in_(open_statuses),
                )
            )
        ).all()
        for task_id, title, priority, work_item_id in open_task_rows:
            _push(
                priority_items,
                str(getattr(priority, "value", priority)),
                _ref(title, "task", task_id, work_item_id=work_item_id),
            )

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
        case_status_items: dict[str, list] = {}
        case_type_items: dict[str, list] = {}
        case_item_rows = (
            await self.db.execute(
                select(
                    CommunicationCase.id,
                    CommunicationCase.subject,
                    CommunicationCase.status,
                    CommunicationCase.type,
                    CommunicationCase.work_item_id,
                ).where(CommunicationCase.organization_id == organization_id)
            )
        ).all()
        for case_id, subject, status, case_type, work_item_id in case_item_rows:
            ref = _ref(subject, "case", case_id, work_item_id=work_item_id)
            _push(case_status_items, str(getattr(status, "value", status)), ref)
            _push(case_type_items, str(getattr(case_type, "value", case_type)), ref)
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
        reply_items: dict[str, list] = {}
        no_reply_threads: list[dict] = []
        for conv in convs:
            msgs = sorted(conv.messages, key=lambda m: m.created_at or now)
            if not msgs:
                continue
            first = msgs[0]
            reply = next((m for m in msgs[1:] if m.sender_id != first.sender_id), None)
            topic = (conv.topic or "").strip()
            if not topic or (any(ch.isdigit() for ch in topic) and "-" in topic):
                topic = (first.text or "").strip()[:80] or "گفتگو بدون موضوع"
            conv_ref = _ref(topic, "conversation", conv.id, work_item_id=conv.work_item_id, conversation_id=conv.id)
            if reply is None or not first.created_at or not reply.created_at:
                reply_buckets["no_reply"] += 1
                _push(reply_items, "no_reply", conv_ref)
                if len(no_reply_threads) < 6 and conv.messages:
                    no_reply_threads.append(
                        {
                            "kind": "conversation",
                            "title": topic,
                            "detail": (first.text or "")[:80],
                            "context": "هنوز جوابی داده نشده",
                            "entity_type": "conversation",
                            "entity_id": str(conv.id),
                            "work_item_id": _sid(conv.work_item_id),
                            "conversation_id": str(conv.id),
                        }
                    )
                continue
            minutes = max((reply.created_at - first.created_at).total_seconds(), 0) / 60
            if minutes < 5:
                reply_buckets["lt5"] += 1
                _push(reply_items, "lt5", conv_ref)
            elif minutes < 30:
                reply_buckets["lt30"] += 1
                _push(reply_items, "lt30", conv_ref)
            elif minutes < 120:
                reply_buckets["lt120"] += 1
                _push(reply_items, "lt120", conv_ref)
            else:
                reply_buckets["gt120"] += 1
                _push(reply_items, "gt120", conv_ref)

        # --- پیام‌ها: روزانه ۱۴ روز اخیر ---
        msgs_14d = (
            await self.db.execute(
                select(Message.created_at, Message.text, Message.conversation_id).where(
                    Message.organization_id == organization_id,
                    Message.created_at >= now - timedelta(days=14),
                )
            )
        ).all()
        daily: Counter[str] = Counter()
        message_items: dict[str, list] = {}
        for created_at, text, conversation_id in msgs_14d:
            if not created_at:
                continue
            day_key = created_at.date().isoformat()
            daily[day_key] += 1
            preview = " ".join((text or "").split())[:80] or "پیام"
            _push(
                message_items,
                day_key,
                _ref(preview, "conversation", conversation_id, conversation_id=conversation_id),
            )
        messages_daily = []
        for i in range(13, -1, -1):
            day = (now - timedelta(days=i)).date().isoformat()
            messages_daily.append({"day": day, "count": daily.get(day, 0)})

        # --- خودروها: پیری انبار + ارزش موجودی ---
        veh_rows = (
            await self.db.execute(
                select(
                    Vehicle.id,
                    Vehicle.status,
                    Vehicle.created_at,
                    Vehicle.sale_price,
                    Vehicle.purchase_price,
                    Vehicle.brand,
                    Vehicle.model,
                    Vehicle.stock_number,
                )
                .where(Vehicle.organization_id == organization_id)
            )
        ).all()
        aging = {"lt7": 0, "lt30": 0, "lt90": 0, "gt90": 0}
        aging_items: dict[str, list] = {}
        value_by_status: dict[str, int] = {}
        for vehicle_id, status, created_at, sale_price, purchase_price, brand, model, stock_number in veh_rows:
            key = str(getattr(status, "value", status))
            est = int(sale_price or purchase_price or 0)
            value_by_status[key] = value_by_status.get(key, 0) + est
            stocked_at = as_utc(created_at)
            if key == "IN_STOCK" and stocked_at is not None:
                days = (now - stocked_at).days
                if days < 7:
                    age_key = "lt7"
                elif days < 30:
                    age_key = "lt30"
                elif days < 90:
                    age_key = "lt90"
                else:
                    age_key = "gt90"
                aging[age_key] += 1
                label = f"{brand} {model}" + (f" #{stock_number}" if stock_number else "")
                _push(aging_items, age_key, _ref(label, "vehicle", vehicle_id))

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

        needs_attention = await self._needs_attention(
            organization_id, now, open_statuses, no_reply_threads
        )

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
            "needs_attention": needs_attention,
            "drilldown": {
                "tasks_week": {
                    week: {
                        "created": week_created.get(week, []),
                        "completed": week_completed.get(week, []),
                    }
                    for week in week_created.keys() | week_completed.keys()
                },
                "priority": priority_items,
                "reply": reply_items,
                "case_status": case_status_items,
                "case_type": case_type_items,
                "aging": aging_items,
                "messages_day": message_items,
            },
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
        pending_at = as_utc(oldest_pending)
        oldest_pending_minutes = (
            int((now - pending_at).total_seconds() // 60) if pending_at is not None else None
        )
        failed_rows = list(
            (
                await self.db.execute(
                    select(TelegramOutbox)
                    .where(
                        TelegramOutbox.organization_id == organization_id,
                        TelegramOutbox.status == "failed",
                    )
                    .order_by(TelegramOutbox.created_at.desc())
                    .limit(6)
                )
            ).scalars().all()
        )
        recent_events = list(
            (
                await self.db.execute(
                    select(Event)
                    .where(Event.organization_id == organization_id)
                    .order_by(Event.created_at.desc())
                    .limit(8)
                )
            ).scalars().all()
        )
        described = await self._describe_entities(
            organization_id,
            [(row.entity_type, row.entity_id) for row in failed_rows]
            + [(row.entity_type, row.entity_id) for row in recent_events],
        )
        recipient_ids = {row.user_id for row in failed_rows}
        recipients: dict[UUID, str] = {}
        if recipient_ids:
            rec_rows = (
                await self.db.execute(
                    select(User.id, User.full_name).where(User.id.in_(recipient_ids))
                )
            ).all()
            recipients = {uid: name for uid, name in rec_rows}

        def _label(kind: str | None, entity_id: UUID | None) -> dict[str, str | None]:
            if not kind or entity_id is None:
                return {"title": "", "work_item_id": None}
            return described.get((kind.lower(), str(entity_id)), {"title": "", "work_item_id": None})

        failed_samples = []
        for row in failed_rows:
            info = _label(row.entity_type, row.entity_id)
            preview = " ".join((row.text or "").split())[:120]
            failed_samples.append(
                {
                    "provider": row.provider,
                    "error": (row.last_error or "")[:160],
                    "at": str(row.created_at or ""),
                    "event_type": row.event_type,
                    "preview": preview,
                    "title": info["title"] or preview or row.event_type,
                    "entity_type": row.entity_type,
                    "entity_id": _sid(row.entity_id),
                    "conversation_id": _sid(row.conversation_id),
                    "work_item_id": info["work_item_id"],
                    "recipient": recipients.get(row.user_id, ""),
                }
            )
        recent_event_rows = []
        for event in recent_events:
            info = _label(event.entity_type, event.entity_id)
            recent_event_rows.append(
                {
                    "type": event.event_type,
                    "entity_type": event.entity_type,
                    "entity_id": str(event.entity_id),
                    "title": info["title"] or event.event_type,
                    "work_item_id": info["work_item_id"],
                    "at": event.created_at.isoformat() if event.created_at else "",
                }
            )

        # --- قفل‌های jobها (سراسری) — منقضی = ورکر مرده/ریست‌شده ---
        locks = list((await self.db.execute(select(JobLock))).scalars().all())
        job_locks = [
            {
                "name": lk.name,
                "owner": lk.owner,
                "expires_at": lk.expires_at.isoformat() if lk.expires_at else None,
                "stale": bool((exp := as_utc(lk.expires_at)) is not None and exp < now),
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
            "recent_events": recent_event_rows,
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
