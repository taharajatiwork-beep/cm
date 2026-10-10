"""CommunicationAgent tools — all mutations go through domain services + RBAC."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.governance import is_ai_governance_enabled, is_sensitive_tool, request_ai_approval
from app.core.permissions import AuthorizationError, PermissionCode, require_permission
from app.models import (
    Branch,
    CommunicationCase,
    Event,
    Permission,
    Role,
    RolePermission,
    Task,
    Team,
    User,
)
from app.models.ai_audit import AiActionLog
from app.models.enums import CaseStatus, CaseType, NotificationChannel, Priority, TaskStatus
from app.services import WorkService, notify
from app.services.inventory import InventoryService
from app.services.search import SearchEntityType, SearchService


@dataclass
class ToolSpec:
    name: str
    permission: str
    description: str
    mutating: bool = False


TOOL_SPECS: dict[str, ToolSpec] = {
    "search_inventory": ToolSpec("search_inventory", PermissionCode.INVENTORY_READ, "Search vehicles"),
    "get_vehicle": ToolSpec("get_vehicle", PermissionCode.INVENTORY_READ, "Get vehicle by id"),
    "find_users": ToolSpec("find_users", PermissionCode.USER_READ, "Find users by name"),
    "find_customers": ToolSpec("find_customers", PermissionCode.CUSTOMER_READ, "Find customers by name/phone"),
    "find_team": ToolSpec("find_team", PermissionCode.USER_READ, "Find team by code/name"),
    "find_branch": ToolSpec("find_branch", PermissionCode.USER_READ, "Find branch by code/name"),
    "get_case": ToolSpec("get_case", PermissionCode.CASE_READ, "Get case by id or number"),
    "get_case_history": ToolSpec("get_case_history", PermissionCode.EVENT_READ, "Case timeline events"),
    "search_messages": ToolSpec("search_messages", PermissionCode.CONVERSATION_READ, "Search via hybrid text"),
    "get_pending_tasks": ToolSpec("get_pending_tasks", PermissionCode.TASK_READ, "Pending tasks for user"),
    "get_user_workload": ToolSpec("get_user_workload", PermissionCode.TASK_READ, "Open task count"),
    "create_case": ToolSpec("create_case", PermissionCode.CASE_WRITE, "Create case", True),
    "create_task": ToolSpec("create_task", PermissionCode.TASK_WRITE, "Create task", True),
    "create_work_item": ToolSpec("create_work_item", PermissionCode.WORK_ITEM_WRITE, "Create work item", True),
    "assign_task": ToolSpec("assign_task", PermissionCode.TASK_ASSIGN, "Assign/delegate task", True),
    "assign_case": ToolSpec("assign_case", PermissionCode.CASE_WRITE, "Assign case owner", True),
    "send_notification": ToolSpec("send_notification", PermissionCode.TASK_WRITE, "Notify a user", True),
    "escalate_case": ToolSpec("escalate_case", PermissionCode.CASE_WRITE, "Escalate case", True),
    "summarize_case": ToolSpec("summarize_case", PermissionCode.CASE_READ, "Summarize case from events"),
    "recommend_assignees": ToolSpec(
        "recommend_assignees", PermissionCode.TASK_ASSIGN, "Recommend assignees via AssignmentEngine"
    ),
    "list_aging_inventory": ToolSpec(
        "list_aging_inventory", PermissionCode.INVENTORY_READ, "List vehicles past aging threshold"
    ),
    "list_inventory_requests": ToolSpec(
        "list_inventory_requests", PermissionCode.INVENTORY_READ, "List open inventory requests"
    ),
    "detect_inventory_opportunities": ToolSpec(
        "detect_inventory_opportunities",
        PermissionCode.INVENTORY_READ,
        "Detect aged stock with demand signals",
    ),
    "create_inventory_opportunity": ToolSpec(
        "create_inventory_opportunity",
        PermissionCode.CASE_WRITE,
        "Create INVENTORY_OPPORTUNITY case (+ optional WorkItem)",
        True,
    ),
    "list_sales_pipeline": ToolSpec(
        "list_sales_pipeline", PermissionCode.CASE_READ, "List open buyer/interest/follow-up cases"
    ),
    "match_buyer_to_inventory": ToolSpec(
        "match_buyer_to_inventory",
        PermissionCode.INVENTORY_READ,
        "Match a buyer/interest case to in-stock vehicles",
    ),
    "detect_sales_follow_ups": ToolSpec(
        "detect_sales_follow_ups",
        PermissionCode.CASE_READ,
        "Detect stale sales cases needing follow-up",
    ),
    "create_sales_follow_up": ToolSpec(
        "create_sales_follow_up",
        PermissionCode.CASE_WRITE,
        "Create FOLLOW_UP case + WorkItem + seller task",
        True,
    ),
    "list_purchase_pipeline": ToolSpec(
        "list_purchase_pipeline",
        PermissionCode.CASE_READ,
        "List open SELLER_REQUEST cases",
    ),
    "detect_purchase_opportunities": ToolSpec(
        "detect_purchase_opportunities",
        PermissionCode.CASE_READ,
        "Detect unmet demand + stale seller offers",
    ),
    "create_purchase_opportunity": ToolSpec(
        "create_purchase_opportunity",
        PermissionCode.CASE_WRITE,
        "Create purchase opportunity / follow-up Case + WorkItem",
        True,
    ),
    "list_divar_candidates": ToolSpec(
        "list_divar_candidates",
        PermissionCode.INVENTORY_READ,
        "List IN_STOCK vehicles without active Divar listing",
    ),
    "list_divar_listings": ToolSpec(
        "list_divar_listings",
        PermissionCode.INVENTORY_READ,
        "List Divar listings linked in Core",
    ),
    "prepare_divar_listing": ToolSpec(
        "prepare_divar_listing",
        PermissionCode.WORK_ITEM_WRITE,
        "Map vehicle → Divar product/task + Core WorkItem (no auto-submit)",
        True,
    ),
    "draft_work_request": ToolSpec(
        "draft_work_request", PermissionCode.REQUEST_CREATE, "Draft a work request; writes only with confirm", True
    ),
    "suggest_project_split": ToolSpec(
        "suggest_project_split", PermissionCode.REQUEST_TRIAGE, "Read-only project split suggestion"
    ),
    "query_my_work": ToolSpec("query_my_work", PermissionCode.TASK_READ, "Buckets of my tasks"),
    "query_projects": ToolSpec("query_projects", PermissionCode.REQUEST_CREATE, "List visible projects"),
    "query_costs_summary": ToolSpec("query_costs_summary", PermissionCode.EXPENSE_REQUEST, "Budget versus recorded"),
    "explain_status": ToolSpec("explain_status", PermissionCode.REQUEST_CREATE, "Explain a request or project status"),
    "prioritize_my_tasks": ToolSpec("prioritize_my_tasks", PermissionCode.TASK_READ, "Order my open tasks"),
    "summarize_scope": ToolSpec("summarize_scope", PermissionCode.TASK_READ, "Summarize allowed work scope"),
}


class ToolContext:
    def __init__(
        self,
        db: AsyncSession,
        *,
        organization_id: UUID,
        user: User,
        permissions: set[str],
        request_id: str,
        agent: str = "CommunicationAgent",
        model: str = "rules-v1",
        prompt_version: str = "1",
    ):
        self.db = db
        self.organization_id = organization_id
        self.user = user
        self.permissions = permissions
        self.request_id = request_id
        self.agent = agent
        self.model = model
        self.prompt_version = prompt_version
        self.work = WorkService(db)
        self.inventory = InventoryService(db)
        self.search = SearchService(db)

    async def audit(
        self,
        tool: str,
        action: str,
        *,
        target_entity: str | None = None,
        input_data: dict | None = None,
        result: Any = None,
        approval: str = "auto",
    ) -> None:
        self.db.add(
            AiActionLog(
                request_id=self.request_id,
                organization_id=self.organization_id,
                user_id=self.user.id,
                acting_for=self.user.id,
                agent=self.agent,
                tool=tool,
                action=action,
                target_entity=target_entity,
                input_json=json.dumps(input_data, default=str) if input_data else None,
                result_json=json.dumps(result, default=str) if result is not None else None,
                approval=approval,
                model=self.model,
                prompt_version=self.prompt_version,
            )
        )
        await self.db.flush()


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _err(message: str) -> dict[str, Any]:
    return {"ok": False, "error": message}


class ToolExecutor:
    def __init__(self, ctx: ToolContext):
        self.ctx = ctx

    async def _org_admin_ids(self) -> list[UUID]:
        """کاربران دارای مجوز org.admin در همین سازمان — تأییدکنندهٔ جایگزین."""
        rows = await self.ctx.db.execute(
            select(User.id)
            .join(Role, User.role_id == Role.id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, RolePermission.permission_id == Permission.id)
            .where(
                User.organization_id == self.ctx.organization_id,
                Permission.code == PermissionCode.ORG_ADMIN,
                User.is_active.is_(True),
            )
        )
        return [r for r in rows.scalars().all() if r != self.ctx.user.id]

    def _require(self, tool_name: str) -> ToolSpec:
        spec = TOOL_SPECS[tool_name]
        require_permission(self.ctx.permissions, spec.permission)
        # SEARCH is used by some read helpers
        # (search_inventory is allowed through the inventory service directly)
        if (
            tool_name == "search_messages"
            and PermissionCode.SEARCH not in self.ctx.permissions
            and PermissionCode.ORG_ADMIN not in self.ctx.permissions
        ):
            require_permission(self.ctx.permissions, PermissionCode.SEARCH)
        return spec

    async def execute(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool_name not in TOOL_SPECS:
            return _err(f"Unknown tool: {tool_name}")
        try:
            self._require(tool_name)
        except AuthorizationError as e:
            await self.ctx.audit(
                tool_name, "denied", input_data=args, result={"error": e.message}, approval="denied"
            )
            return _err(e.message)

        # AI Governance: check if sensitive tool needs human approval
        if is_ai_governance_enabled() and is_sensitive_tool(tool_name):
            # Request approval instead of executing
            # اگر کاربر مدیر نداشته باشد، تأیید به سرپرستِ سرپرست یا ادمین سازمان می‌رود؛
            # هرگز به خودِ درخواست‌دهنده (که حاکمیت AI را بی‌اثر می‌کرد).
            approver_ids = [self.ctx.user.manager_id] if self.ctx.user.manager_id else []
            if not approver_ids:
                approver_ids = await self._org_admin_ids()
            if not approver_ids:
                return _err(
                    "برای این عملیات حساس هیچ تأییدکننده‌ای وجود ندارد؛ "
                    "لطفاً مدیر سازمان را تعیین کنید یا از سرپرست بخواهید درخواست را بررسی کند."
                )
            row = await request_ai_approval(
                self.ctx.db,
                organization_id=self.ctx.organization_id,
                requester_id=self.ctx.user.id,
                tool_name=tool_name,
                title=args.get("title") or args.get("subject") or tool_name,
                payload=args,
                approver_ids=approver_ids,
            )
            await self.ctx.audit(
                tool_name,
                "approval_requested",
                target_entity="",
                input_data=args,
                result={"approval_id": str(row.id)},
                approval="pending",
            )
            return _ok({"approval_id": str(row.id), "status": "pending_approval"})

        handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] = getattr(self, f"_tool_{tool_name}")
        result = await handler(args)
        await self.ctx.audit(
            tool_name,
            "execute",
            target_entity=str(args.get("id") or args.get("vehicle_id") or args.get("case_id") or ""),
            input_data=args,
            result=result,
            approval="auto",
        )
        return result

    async def _tool_search_inventory(self, args: dict[str, Any]) -> dict[str, Any]:
        vehicles = await self.ctx.inventory.search_vehicles(
            self.ctx.organization_id,
            q=args.get("q"),
            brand=args.get("brand"),
            model=args.get("model"),
            stock_number=args.get("stock_number"),
            vin=args.get("vin"),
            branch_id=UUID(args["branch_id"]) if args.get("branch_id") else None,
        )
        return _ok(
            [
                {
                    "id": str(v.id),
                    "vin": v.vin,
                    "brand": v.brand,
                    "model": v.model,
                    "stock_number": v.stock_number,
                    "status": v.status.value,
                    "branch_id": str(v.branch_id) if v.branch_id else None,
                }
                for v in vehicles
            ]
        )

    async def _tool_get_vehicle(self, args: dict[str, Any]) -> dict[str, Any]:
        vehicle = await self.ctx.inventory.get_vehicle(UUID(args["vehicle_id"]))
        if not vehicle or vehicle.organization_id != self.ctx.organization_id:
            return _err("Vehicle not found")
        return _ok(
            {
                "id": str(vehicle.id),
                "vin": vehicle.vin,
                "brand": vehicle.brand,
                "model": vehicle.model,
                "stock_number": vehicle.stock_number,
                "status": vehicle.status.value,
            }
        )

    async def _tool_find_users(self, args: dict[str, Any]) -> dict[str, Any]:
        q = (args.get("q") or "").strip()
        users = list(
            (
                await self.ctx.db.execute(
                    select(User).where(
                        User.organization_id == self.ctx.organization_id,
                        User.is_active.is_(True),
                    )
                )
            ).scalars().all()
        )

        def matches(u: User) -> bool:
            if not q:
                return True
            name = u.full_name
            lower = name.lower()
            ql = q.lower()
            if ql in lower or q in name:
                return True
            aliases = {
                "رضا": ("reza", "رضا"),
                "reza": ("reza", "رضا"),
                "سارا": ("sara", "سارا"),
                "sara": ("sara", "سارا"),
                "علی": ("ali", "علی"),
                "ali": ("ali", "علی"),
            }
            for token in aliases.get(ql, aliases.get(q, ())):
                if token in lower or token in name:
                    return True
            return False

        matched = [
            {
                "id": str(u.id),
                "full_name": u.full_name,
                "email": u.email,
                "team_id": str(u.team_id) if u.team_id else None,
                "branch_id": str(u.branch_id) if u.branch_id else None,
            }
            for u in users
            if matches(u)
        ]
        return _ok(matched)

    async def _tool_find_customers(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.services.customer import CustomerService

        rows = await CustomerService(self.ctx.db).search(
            self.ctx.organization_id, q=args.get("q"), limit=int(args.get("limit") or 20)
        )
        return _ok(
            [
                {
                    "id": str(c.id),
                    "full_name": c.full_name,
                    "phone": c.phone,
                    "email": c.email,
                }
                for c in rows
            ]
        )

    async def _tool_find_team(self, args: dict[str, Any]) -> dict[str, Any]:
        q = (args.get("q") or "").strip()
        rows = list(
            (
                await self.ctx.db.execute(
                    select(Team).where(Team.organization_id == self.ctx.organization_id)
                )
            ).scalars().all()
        )
        out = [
            {"id": str(t.id), "name": t.name, "code": t.code}
            for t in rows
            if not q or q.lower() in t.name.lower() or q.lower() == t.code.lower()
        ]
        return _ok(out)

    async def _tool_find_branch(self, args: dict[str, Any]) -> dict[str, Any]:
        q = (args.get("q") or "").strip()
        rows = list(
            (
                await self.ctx.db.execute(
                    select(Branch).where(Branch.organization_id == self.ctx.organization_id)
                )
            ).scalars().all()
        )
        out = [
            {"id": str(b.id), "name": b.name, "code": b.code, "city": b.city}
            for b in rows
            if not q or q.lower() in (b.name or "").lower() or q.lower() == (b.code or "").lower()
        ]
        return _ok(out)

    async def _tool_get_case(self, args: dict[str, Any]) -> dict[str, Any]:
        case = None
        if args.get("case_id"):
            case = await self.ctx.db.get(CommunicationCase, UUID(args["case_id"]))
        elif args.get("case_number"):
            case = await self.ctx.db.scalar(
                select(CommunicationCase).where(
                    CommunicationCase.organization_id == self.ctx.organization_id,
                    CommunicationCase.case_number == args["case_number"],
                )
            )
        if not case or case.organization_id != self.ctx.organization_id:
            return _err("Case not found")
        return _ok(
            {
                "id": str(case.id),
                "case_number": case.case_number,
                "subject": case.subject,
                "status": case.status.value,
                "owner_id": str(case.owner_id) if case.owner_id else None,
            }
        )

    async def _tool_get_case_history(self, args: dict[str, Any]) -> dict[str, Any]:
        case_id = UUID(args["case_id"])
        events = list(
            (
                await self.ctx.db.execute(
                    select(Event)
                    .where(Event.entity_type == "case", Event.entity_id == case_id)
                    .order_by(Event.created_at)
                )
            ).scalars().all()
        )
        return _ok(
            [
                {"event_type": e.event_type, "payload": e.payload, "created_at": str(e.created_at)}
                for e in events
            ]
        )

    async def _tool_search_messages(self, args: dict[str, Any]) -> dict[str, Any]:
        # Reuse structured search as message/work text proxy for Phase 7
        hits = await self.ctx.search.search(
            organization_id=self.ctx.organization_id,
            actor_permissions=self.ctx.permissions | {PermissionCode.SEARCH},
            q=args.get("q"),
            types=[SearchEntityType.WORK_ITEM, SearchEntityType.CASE],
            limit=10,
        )
        return _ok(
            [
                {
                    "entity_type": h.entity_type,
                    "entity_id": str(h.entity_id),
                    "title": h.title,
                    "subtitle": h.subtitle,
                }
                for h in hits
            ]
        )

    async def _tool_get_pending_tasks(self, args: dict[str, Any]) -> dict[str, Any]:
        user_id = UUID(args["user_id"]) if args.get("user_id") else self.ctx.user.id
        from app.models import TaskAssignee

        rows = list(
            (
                await self.ctx.db.execute(
                    select(Task)
                    .join(TaskAssignee, TaskAssignee.task_id == Task.id)
                    .where(
                        TaskAssignee.user_id == user_id,
                        Task.organization_id == self.ctx.organization_id,
                        Task.status.in_(
                            [TaskStatus.OPEN, TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED]
                        ),
                    )
                )
            ).scalars().all()
        )
        return _ok(
            [{"id": str(t.id), "title": t.title, "status": t.status.value} for t in rows]
        )

    async def _tool_get_user_workload(self, args: dict[str, Any]) -> dict[str, Any]:
        user_id = UUID(args["user_id"])
        from app.models import TaskAssignee

        count = await self.ctx.db.scalar(
            select(func.count())
            .select_from(Task)
            .join(TaskAssignee, TaskAssignee.task_id == Task.id)
            .where(
                TaskAssignee.user_id == user_id,
                Task.organization_id == self.ctx.organization_id,
                Task.status.in_(
                    [TaskStatus.OPEN, TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED]
                ),
            )
        )
        return _ok({"user_id": str(user_id), "open_tasks": int(count or 0)})

    async def _tool_create_work_item(self, args: dict[str, Any]) -> dict[str, Any]:
        wi = await self.ctx.work.create_work_item(
            organization_id=self.ctx.organization_id,
            title=args["title"],
            owner_id=self.ctx.user.id,
            description=args.get("description"),
            priority=Priority(args["priority"]) if args.get("priority") else Priority.HIGH,
            vehicle_id=UUID(args["vehicle_id"]) if args.get("vehicle_id") else None,
            branch_id=UUID(args["branch_id"]) if args.get("branch_id") else None,
            participant_ids=[UUID(x) for x in args.get("participant_ids", [])],
        )
        return _ok({"id": str(wi.id), "title": wi.title})

    async def _tool_create_case(self, args: dict[str, Any]) -> dict[str, Any]:
        case = await self.ctx.work.create_case(
            organization_id=self.ctx.organization_id,
            subject=args["subject"],
            case_type=CaseType(args.get("type", CaseType.GENERAL_OPERATIONAL_REQUEST.value)),
            created_by=self.ctx.user.id,
            work_item_id=UUID(args["work_item_id"]) if args.get("work_item_id") else None,
            owner_id=UUID(args["owner_id"]) if args.get("owner_id") else None,
            vehicle_id=UUID(args["vehicle_id"]) if args.get("vehicle_id") else None,
            branch_id=UUID(args["branch_id"]) if args.get("branch_id") else None,
            priority=Priority(args["priority"]) if args.get("priority") else Priority.MEDIUM,
        )
        return _ok({"id": str(case.id), "case_number": case.case_number})

    async def _tool_create_task(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.models.enums import AssignmentTargetType

        target_type = None
        if args.get("assignment_target_type"):
            target_type = AssignmentTargetType(args["assignment_target_type"])
        task = await self.ctx.work.create_task(
            organization_id=self.ctx.organization_id,
            title=args["title"],
            owner_id=self.ctx.user.id,
            work_item_id=UUID(args["work_item_id"]) if args.get("work_item_id") else None,
            case_id=UUID(args["case_id"]) if args.get("case_id") else None,
            description=args.get("description"),
            assignee_ids=[UUID(x) for x in args.get("assignee_ids", [])],
            assignment_target_type=target_type,
            assignment_target_id=(
                UUID(args["assignment_target_id"]) if args.get("assignment_target_id") else None
            ),
            priority=Priority(args["priority"]) if args.get("priority") else Priority.HIGH,
            actor_permissions=self.ctx.permissions,
        )
        return _ok(
            {
                "id": str(task.id),
                "title": task.title,
                "status": task.status.value,
                "assignment_target_type": (
                    task.assignment_target_type.value if task.assignment_target_type else None
                ),
                "assignment_target_id": (
                    str(task.assignment_target_id) if task.assignment_target_id else None
                ),
            }
        )

    async def _tool_assign_task(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.models.enums import AssignmentTargetType

        target_type = None
        if args.get("to_target_type") or args.get("assignment_target_type"):
            target_type = AssignmentTargetType(
                args.get("to_target_type") or args["assignment_target_type"]
            )
        to_target_id = args.get("to_target_id") or args.get("assignment_target_id")
        task = await self.ctx.work.delegate_task(
            organization_id=self.ctx.organization_id,
            task_id=UUID(args["task_id"]),
            actor_id=self.ctx.user.id,
            actor_permissions=self.ctx.permissions,
            to_user_id=UUID(args["user_id"]) if args.get("user_id") else None,
            to_target_type=target_type,
            to_target_id=UUID(to_target_id) if to_target_id else None,
        )
        return _ok(
            {
                "id": str(task.id),
                "status": task.status.value,
                "assignment_target_type": (
                    task.assignment_target_type.value if task.assignment_target_type else None
                ),
            }
        )

    async def _tool_assign_case(self, args: dict[str, Any]) -> dict[str, Any]:
        case = await self.ctx.db.get(CommunicationCase, UUID(args["case_id"]))
        if not case or case.organization_id != self.ctx.organization_id:
            return _err("Case not found")
        owner_id = UUID(args["owner_id"])
        case.owner_id = owner_id
        case.status = CaseStatus.ASSIGNED
        await self.ctx.db.flush()
        await notify(
            self.ctx.db,
            organization_id=self.ctx.organization_id,
            user_id=owner_id,
            title=f"Case {case.case_number} assigned",
            body=case.subject,
            entity_type="case",
            entity_id=case.id,
        )
        return _ok({"id": str(case.id), "owner_id": str(owner_id)})

    async def _tool_send_notification(self, args: dict[str, Any]) -> dict[str, Any]:
        n = await notify(
            self.ctx.db,
            organization_id=self.ctx.organization_id,
            user_id=UUID(args["user_id"]),
            title=args.get("title", "Notification"),
            body=args["body"],
            channel=NotificationChannel.WEB,
            entity_type=args.get("entity_type"),
            entity_id=UUID(args["entity_id"]) if args.get("entity_id") else None,
        )
        return _ok({"id": str(n.id)})

    async def _tool_escalate_case(self, args: dict[str, Any]) -> dict[str, Any]:
        case = await self.ctx.db.get(CommunicationCase, UUID(args["case_id"]))
        if not case or case.organization_id != self.ctx.organization_id:
            return _err("Case not found")
        case.status = CaseStatus.ESCALATED
        await self.ctx.db.flush()
        return _ok({"id": str(case.id), "status": case.status.value})

    async def _tool_summarize_case(self, args: dict[str, Any]) -> dict[str, Any]:
        case_id = UUID(args["case_id"])
        case = await self.ctx.db.get(CommunicationCase, case_id)
        if not case:
            return _err("Case not found")
        hist = await self._tool_get_case_history({"case_id": str(case_id)})
        events = hist.get("data") or []
        summary = (
            f"Case {case.case_number}: {case.subject}. "
            f"Status {case.status.value}. Events: {len(events)}."
        )
        return _ok({"summary": summary, "event_count": len(events)})

    async def _tool_recommend_assignees(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.services.assignment import AssignmentEngine

        rec = await AssignmentEngine(self.ctx.db).recommend(
            organization_id=self.ctx.organization_id,
            actor_permissions=self.ctx.permissions,
            role_code=args.get("role_code"),
            branch_id=UUID(args["branch_id"]) if args.get("branch_id") else None,
            department_id=UUID(args["department_id"]) if args.get("department_id") else None,
            team_id=UUID(args["team_id"]) if args.get("team_id") else None,
            required_skills=args.get("required_skills") or [],
            require_available=args.get("require_available", True),
            limit=int(args.get("limit") or 10),
        )
        return _ok(
            {
                "recommended_user_id": str(rec.recommended_user_id)
                if rec.recommended_user_id
                else None,
                "auto_assign_allowed": rec.auto_assign_allowed,
                "candidates": [
                    {
                        "user_id": str(c.user_id),
                        "full_name": c.full_name,
                        "score": c.score,
                        "open_tasks": c.open_tasks,
                        "skills": c.skills,
                        "reasons": c.reasons,
                    }
                    for c in rec.candidates
                ],
            }
        )

    async def _tool_list_aging_inventory(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.core.config import get_settings

        min_days = int(args.get("min_days") or get_settings().inventory_aging_days)
        rows = await self.ctx.inventory.list_aging_vehicles(
            self.ctx.organization_id, min_days=min_days
        )
        return _ok({"min_days": min_days, "count": len(rows), "vehicles": rows})

    async def _tool_list_inventory_requests(self, args: dict[str, Any]) -> dict[str, Any]:
        vehicle_id = UUID(args["vehicle_id"]) if args.get("vehicle_id") else None
        reqs = await self.ctx.inventory.list_open_requests(
            self.ctx.organization_id, vehicle_id=vehicle_id
        )
        return _ok(
            [
                {
                    "id": str(r.id),
                    "vehicle_id": str(r.vehicle_id) if r.vehicle_id else None,
                    "requesting_branch_id": str(r.requesting_branch_id),
                    "subject": r.subject,
                    "status": r.status.value,
                    "request_type": r.request_type.value,
                }
                for r in reqs
            ]
        )

    async def _tool_detect_inventory_opportunities(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.core.config import get_settings

        settings = get_settings()
        min_days = int(args.get("min_days") or settings.inventory_aging_days)
        min_branches = int(args.get("min_branch_requests") or settings.inventory_min_branch_requests)
        opps = await self.ctx.inventory.detect_opportunities(
            self.ctx.organization_id,
            min_days=min_days,
            min_branch_requests=min_branches,
        )
        return _ok(
            {
                "min_days": min_days,
                "min_branch_requests": min_branches,
                "count": len(opps),
                "opportunities": opps,
            }
        )

    async def _tool_create_inventory_opportunity(self, args: dict[str, Any]) -> dict[str, Any]:
        vehicle_id = UUID(args["vehicle_id"])
        vehicle = await self.ctx.inventory.get_vehicle(vehicle_id)
        if not vehicle or vehicle.organization_id != self.ctx.organization_id:
            return _err("Vehicle not found")

        reasons = args.get("reasons") or []
        reason_txt = ", ".join(reasons) if reasons else "inventory signals"
        subject = args.get("subject") or (
            f"Inventory opportunity: {vehicle.brand} {vehicle.model}"
            + (f" #{vehicle.stock_number}" if vehicle.stock_number else "")
        )
        create_work = bool(args.get("create_work_item", True))

        work_item_id: UUID | None = None
        if create_work:
            wi = await self.ctx.work.create_work_item(
                organization_id=self.ctx.organization_id,
                title=subject,
                owner_id=self.ctx.user.id,
                description=f"Auto-recommended by InventoryAgent ({reason_txt}).",
                priority=Priority.HIGH,
                vehicle_id=vehicle_id,
                branch_id=vehicle.branch_id,
            )
            work_item_id = wi.id

        case = await self.ctx.work.create_case(
            organization_id=self.ctx.organization_id,
            subject=subject,
            case_type=CaseType.INVENTORY_OPPORTUNITY,
            created_by=self.ctx.user.id,
            work_item_id=work_item_id,
            vehicle_id=vehicle_id,
            branch_id=vehicle.branch_id,
            priority=Priority.HIGH,
        )
        return _ok(
            {
                "case_id": str(case.id),
                "case_number": case.case_number,
                "work_item_id": str(work_item_id) if work_item_id else None,
                "vehicle_id": str(vehicle_id),
                "subject": subject,
            }
        )

    async def _tool_list_sales_pipeline(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.services.sales import SalesService

        rows = await SalesService(self.ctx.db).list_pipeline(self.ctx.organization_id)
        return _ok({"count": len(rows), "cases": rows})

    async def _tool_match_buyer_to_inventory(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.services.sales import SalesService

        try:
            data = await SalesService(self.ctx.db).match_case_to_inventory(
                self.ctx.organization_id, UUID(args["case_id"])
            )
        except ValueError as e:
            return _err(str(e))
        return _ok(data)

    async def _tool_detect_sales_follow_ups(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.core.config import get_settings
        from app.services.sales import SalesService

        stale_days = int(args.get("stale_days") or get_settings().sales_stale_days)
        rows = await SalesService(self.ctx.db).detect_follow_ups(
            self.ctx.organization_id, stale_days=stale_days
        )
        return _ok({"stale_days": stale_days, "count": len(rows), "follow_ups": rows})

    async def _tool_create_sales_follow_up(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.services.assignment import AssignmentEngine

        source_case_id = UUID(args["case_id"])
        source = await self.ctx.db.get(CommunicationCase, source_case_id)
        if not source or source.organization_id != self.ctx.organization_id:
            return _err("Case not found")

        vehicle_id = UUID(args["vehicle_id"]) if args.get("vehicle_id") else source.vehicle_id
        reasons = args.get("reasons") or []
        reason_txt = ", ".join(reasons) if reasons else "stale sales signal"
        subject = args.get("subject") or f"Sales follow-up: {source.case_number} — {source.subject}"

        # Recommend a seller when possible
        assignee_id: UUID | None = None
        if args.get("assignee_id"):
            assignee_id = UUID(args["assignee_id"])
        else:
            rec = await AssignmentEngine(self.ctx.db).recommend(
                organization_id=self.ctx.organization_id,
                actor_permissions=self.ctx.permissions,
                role_code=args.get("role_code") or "seller",
                branch_id=source.branch_id,
                require_available=False,
                limit=3,
            )
            if rec.recommended_user_id:
                assignee_id = rec.recommended_user_id

        wi = await self.ctx.work.create_work_item(
            organization_id=self.ctx.organization_id,
            title=subject,
            owner_id=self.ctx.user.id,
            description=f"Auto-created by SalesAgent ({reason_txt}). Source case {source.case_number}.",
            priority=Priority.HIGH,
            vehicle_id=vehicle_id,
            branch_id=source.branch_id,
            participant_ids=[assignee_id] if assignee_id else None,
        )

        case = await self.ctx.work.create_case(
            organization_id=self.ctx.organization_id,
            subject=subject,
            case_type=CaseType.FOLLOW_UP,
            created_by=self.ctx.user.id,
            work_item_id=wi.id,
            owner_id=assignee_id,
            vehicle_id=vehicle_id,
            branch_id=source.branch_id,
            priority=Priority.HIGH,
        )

        task_id: str | None = None
        if assignee_id:
            task = await self.ctx.work.create_task(
                organization_id=self.ctx.organization_id,
                title=f"Follow up buyer — {source.case_number}",
                owner_id=self.ctx.user.id,
                work_item_id=wi.id,
                case_id=case.id,
                description=f"Contact buyer and update case {source.case_number}.",
                assignee_ids=[assignee_id],
                priority=Priority.HIGH,
                actor_permissions=self.ctx.permissions,
            )
            task_id = str(task.id)

        return _ok(
            {
                "case_id": str(case.id),
                "case_number": case.case_number,
                "work_item_id": str(wi.id),
                "task_id": task_id,
                "assignee_id": str(assignee_id) if assignee_id else None,
                "source_case_id": str(source_case_id),
                "vehicle_id": str(vehicle_id) if vehicle_id else None,
                "subject": subject,
            }
        )

    async def _tool_list_purchase_pipeline(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.services.purchase import PurchaseService

        rows = await PurchaseService(self.ctx.db).list_pipeline(self.ctx.organization_id)
        return _ok({"count": len(rows), "cases": rows})

    async def _tool_detect_purchase_opportunities(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.core.config import get_settings
        from app.services.purchase import PurchaseService

        stale_days = int(args.get("stale_days") or get_settings().purchase_stale_days)
        rows = await PurchaseService(self.ctx.db).detect_opportunities(
            self.ctx.organization_id, stale_days=stale_days
        )
        return _ok({"stale_days": stale_days, "count": len(rows), "opportunities": rows})

    async def _tool_create_purchase_opportunity(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.services.assignment import AssignmentEngine

        kind = args.get("kind") or "unmet_demand"
        reasons = args.get("reasons") or []
        reason_txt = ", ".join(reasons) if reasons else "purchase signal"
        brand = args.get("brand")
        model = args.get("model")
        label = args.get("label") or f"{brand or ''} {model or ''}".strip() or "vehicle"
        source_case_id = UUID(args["source_case_id"]) if args.get("source_case_id") else None

        if kind == "stale_seller_offer" and source_case_id:
            source = await self.ctx.db.get(CommunicationCase, source_case_id)
            if not source or source.organization_id != self.ctx.organization_id:
                return _err("Source case not found")
            subject = args.get("subject") or f"Purchase follow-up: {source.case_number} — {source.subject}"
            case_type = CaseType.FOLLOW_UP
            branch_id = source.branch_id
            vehicle_id = source.vehicle_id
        else:
            subject = args.get("subject") or f"Purchase opportunity: {label}"
            case_type = CaseType.GENERAL_OPERATIONAL_REQUEST
            branch_id = UUID(args["branch_id"]) if args.get("branch_id") else None
            vehicle_id = UUID(args["vehicle_id"]) if args.get("vehicle_id") else None

        assignee_id: UUID | None = None
        if args.get("assignee_id"):
            assignee_id = UUID(args["assignee_id"])
        else:
            try:
                rec = await AssignmentEngine(self.ctx.db).recommend(
                    organization_id=self.ctx.organization_id,
                    actor_permissions=self.ctx.permissions,
                    role_code=args.get("role_code") or "seller",
                    branch_id=branch_id,
                    require_available=False,
                    limit=3,
                )
                if rec.recommended_user_id:
                    assignee_id = rec.recommended_user_id
            except AuthorizationError:
                assignee_id = None

        wi = await self.ctx.work.create_work_item(
            organization_id=self.ctx.organization_id,
            title=subject,
            owner_id=self.ctx.user.id,
            description=f"Auto-created by PurchaseAgent ({reason_txt}).",
            priority=Priority.HIGH,
            vehicle_id=vehicle_id,
            branch_id=branch_id,
            participant_ids=[assignee_id] if assignee_id else None,
        )
        case = await self.ctx.work.create_case(
            organization_id=self.ctx.organization_id,
            subject=subject,
            case_type=case_type,
            created_by=self.ctx.user.id,
            work_item_id=wi.id,
            owner_id=assignee_id,
            vehicle_id=vehicle_id,
            branch_id=branch_id,
            priority=Priority.HIGH,
        )
        task_id: str | None = None
        if assignee_id:
            task = await self.ctx.work.create_task(
                organization_id=self.ctx.organization_id,
                title=f"Evaluate purchase — {label}",
                owner_id=self.ctx.user.id,
                work_item_id=wi.id,
                case_id=case.id,
                description=f"Source kind={kind}. {reason_txt}",
                assignee_ids=[assignee_id],
                priority=Priority.HIGH,
                actor_permissions=self.ctx.permissions,
            )
            task_id = str(task.id)

        return _ok(
            {
                "case_id": str(case.id),
                "case_number": case.case_number,
                "work_item_id": str(wi.id),
                "task_id": task_id,
                "assignee_id": str(assignee_id) if assignee_id else None,
                "kind": kind,
                "subject": subject,
            }
        )

    async def _tool_list_divar_candidates(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.services.divar import DivarService

        rows = await DivarService(self.ctx.db).list_candidates(
            self.ctx.organization_id, limit=int(args.get("limit") or 50)
        )
        return _ok({"count": len(rows), "candidates": rows})

    async def _tool_list_divar_listings(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.services.divar import DivarService

        rows = await DivarService(self.ctx.db).list_listings(self.ctx.organization_id)
        return _ok({"count": len(rows), "listings": rows})

    async def _guard_context(self, kind: str | None, entity_id: str | None) -> dict[str, Any] | None:
        if not kind or not entity_id:
            return None
        from app.requests.spine import assert_visible

        try:
            await assert_visible(self.ctx.db, self.ctx.organization_id, kind, UUID(entity_id))
        except LookupError:
            return _err("پیدا نشد")
        return None

    async def _tool_draft_work_request(self, args: dict[str, Any]) -> dict[str, Any]:
        draft = {
            "title": str(args.get("title") or "").strip(),
            "kind": str(args.get("kind") or "عمومی"),
            "description": str(args.get("description") or ""),
        }
        if not draft["title"]:
            return _err("عنوان خالی است")
        if not args.get("confirm"):
            return _ok({"draft": draft, "saved": False})
        from app.requests.models import WorkRequest
        from app.requests.routes import _next_request_code

        row = WorkRequest(
            organization_id=self.ctx.organization_id,
            code=await _next_request_code(self.ctx.db, self.ctx.organization_id),
            title=draft["title"],
            description=draft["description"],
            kind=draft["kind"],
            requested_by=self.ctx.user.id,
            created_by=self.ctx.user.id,
        )
        self.ctx.db.add(row)
        await self.ctx.db.flush()
        return _ok({"id": str(row.id), "code": row.code, "saved": True})

    async def _tool_suggest_project_split(self, args: dict[str, Any]) -> dict[str, Any]:
        blocked = await self._guard_context("request", args.get("request_id"))
        if blocked:
            return blocked
        from app.requests.spine import KIND_HINT

        kind = str(args.get("kind") or "عمومی")
        return _ok({"kind": kind, "handling": KIND_HINT.get(kind, "project"), "writes": False})

    async def _tool_query_my_work(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.requests.spine import my_work

        return _ok(await my_work(self.ctx.db, self.ctx.organization_id, self.ctx.user.id))

    async def _tool_query_projects(self, args: dict[str, Any]) -> dict[str, Any]:
        blocked = await self._guard_context("project", args.get("project_id"))
        if blocked:
            return blocked
        from app.requests.models import WorkProject

        rows = list(
            (
                await self.ctx.db.scalars(
                    select(WorkProject).where(WorkProject.organization_id == self.ctx.organization_id)
                )
            ).all()
        )
        return _ok([{"id": str(row.id), "code": row.code, "title": row.title, "status": row.status} for row in rows])

    async def _tool_query_costs_summary(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.services.work_report import work_report

        try:
            data = await work_report(
                self.ctx.db,
                organization_id=self.ctx.organization_id,
                user=self.ctx.user,
                permissions=self.ctx.permissions,
                scope="me",
                group_by="none",
            )
        except PermissionError as exc:
            return _err(str(exc))
        return _ok({"planned_budget": data["planned_budget"], "recorded_cost": data["recorded_cost"]})

    async def _tool_explain_status(self, args: dict[str, Any]) -> dict[str, Any]:
        kind = str(args.get("kind") or "request")
        blocked = await self._guard_context(kind, args.get("id"))
        if blocked:
            return blocked
        return _ok({"kind": kind, "id": args.get("id"), "note": "وضعیت از پایگاه داده خوانده شد"})

    async def _tool_prioritize_my_tasks(self, args: dict[str, Any]) -> dict[str, Any]:
        data = await self._tool_query_my_work(args)
        groups = data.get("data") or {}
        ordered = groups.get("overdue", []) + groups.get("today", []) + groups.get("later", [])
        return _ok(ordered)

    async def _tool_summarize_scope(self, args: dict[str, Any]) -> dict[str, Any]:
        return _ok({"user_id": str(self.ctx.user.id), "team_id": str(self.ctx.user.team_id) if self.ctx.user.team_id else None})

    async def _tool_prepare_divar_listing(self, args: dict[str, Any]) -> dict[str, Any]:
        from app.services.divar import DivarService

        try:
            data = await DivarService(self.ctx.db).prepare_listing(
                organization_id=self.ctx.organization_id,
                vehicle_id=UUID(args["vehicle_id"]),
                actor_id=self.ctx.user.id,
                city=args.get("city") or "تهران",
                create_task=bool(args.get("create_task", True)),
                create_work_item=bool(args.get("create_work_item", True)),
            )
        except ValueError as e:
            return _err(str(e))
        return _ok(data)
