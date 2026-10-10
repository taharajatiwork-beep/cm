"""Seed rich demo data for UI walkthrough.

Usage:
  cd backend
  uv run python -m scripts.seed_demo

Idempotent: skips if vehicle stock #124 already exists for org `autoco`.
Creates org + people if missing (same passwords as tests: password).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app import models  # noqa: F401 — register mappers
from app.core.permissions import PermissionCode
from app.core.permissions import PermissionCode as PC
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.models import Organization, User
from app.models.campaign import Campaign
from app.models.enums import (
    AssignmentTargetType,
    CampaignStatus,
    CaseStatus,
    CaseType,
    Channel,
    Priority,
    SlaState,
    RelationshipType,
    VehicleStatus,
)
from app.models.inventory import Vehicle
from app.services import (
    CommunicationService,
    OrgService,
    SlaService,
    WorkService,
    notify,
)
from app.services.campaign import CampaignService
from app.services.customer import CustomerService
from app.services.inventory import InventoryService
from app.services.knowledge import KnowledgeService


async def _ensure_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def _patch_columns(sync_conn):
            from sqlalchemy import inspect, text

            insp = inspect(sync_conn)
            tables = set(insp.get_table_names())

            if "conversations" in tables:
                cols = {c["name"] for c in insp.get_columns("conversations")}
                if "campaign_id" not in cols:
                    sync_conn.execute(text("ALTER TABLE conversations ADD COLUMN campaign_id CHAR(36)"))

            for table in ("work_items", "cases", "campaigns"):
                if table in tables:
                    cols = {c["name"] for c in insp.get_columns(table)}
                    if "department_id" not in cols:
                        sync_conn.execute(
                            text(f"ALTER TABLE {table} ADD COLUMN department_id CHAR(36)")
                        )

            if "vehicles" in tables:
                vcols = {c["name"] for c in insp.get_columns("vehicles")}
                vehicle_alters = [
                    ("description", "TEXT"),
                    ("notes", "TEXT"),
                    ("body_type", "VARCHAR(50)"),
                    ("transmission", "VARCHAR(50)"),
                    ("fuel_type", "VARCHAR(50)"),
                    ("engine", "VARCHAR(80)"),
                    ("plate_number", "VARCHAR(40)"),
                    ("doors", "INTEGER"),
                    ("seats", "INTEGER"),
                    ("options", "TEXT"),
                    ("exterior_condition", "VARCHAR(80)"),
                    ("interior_condition", "VARCHAR(80)"),
                    ("import_source", "VARCHAR(120)"),
                ]
                for name, col_type in vehicle_alters:
                    if name not in vcols:
                        sync_conn.execute(text(f"ALTER TABLE vehicles ADD COLUMN {name} {col_type}"))
                pricing_alters = [
                    ("price_updated_at", "DATETIME"),
                    ("price_updated_by", "CHAR(36)"),
                    ("stock_updated_at", "DATETIME"),
                    ("stock_updated_by", "CHAR(36)"),
                    ("delivery_note", "VARCHAR(255)"),
                ]
                for name, col_type in pricing_alters:
                    if name not in vcols:
                        sync_conn.execute(text(f"ALTER TABLE vehicles ADD COLUMN {name} {col_type}"))

            if "pm_lead" in tables:
                cols = {c["name"] for c in insp.get_columns("pm_lead")}
                if "quantity" not in cols:
                    sync_conn.execute(text("ALTER TABLE pm_lead ADD COLUMN quantity INTEGER DEFAULT 1"))

            if "pm_story" in tables:
                cols = {c["name"] for c in insp.get_columns("pm_story")}
                if "kind" not in cols:
                    sync_conn.execute(text("ALTER TABLE pm_story ADD COLUMN kind VARCHAR(20) DEFAULT 'story'"))
                if "status" not in cols:
                    sync_conn.execute(text("ALTER TABLE pm_story ADD COLUMN status VARCHAR(20) DEFAULT 'published'"))

            if "pm_campaign" in tables:
                cols = {c["name"] for c in insp.get_columns("pm_campaign")}
                if "brief" not in cols:
                    sync_conn.execute(text("ALTER TABLE pm_campaign ADD COLUMN brief TEXT DEFAULT ''"))

            if "pm_sms_send" in tables:
                cols = {c["name"] for c in insp.get_columns("pm_sms_send")}
                if "pishgam_message_id" not in cols:
                    sync_conn.execute(text("ALTER TABLE pm_sms_send ADD COLUMN pishgam_message_id BIGINT"))

        await conn.run_sync(_patch_columns)


async def _ensure_org(db) -> dict:
    svc = OrgService(db)
    from app.models import Branch, Department, Role, Team

    org = await db.scalar(select(Organization).where(Organization.slug == "autoco"))
    created_org = False
    if not org:
        org = await svc.create_organization("AutoCo", "autoco")
        created_org = True

    async def get_or_create_branch(name: str, code: str, city: str):
        row = await db.scalar(
            select(Branch).where(Branch.organization_id == org.id, Branch.code == code)
        )
        if row:
            return row
        return await svc.create_branch(org.id, name, code, city=city)

    async def get_or_create_dept(name: str, code: str):
        row = await db.scalar(
            select(Department).where(
                Department.organization_id == org.id, Department.code == code
            )
        )
        if row:
            return row
        return await svc.create_department(org.id, name, code)

    async def get_or_create_team(name: str, code: str, dept_id):
        row = await db.scalar(
            select(Team).where(Team.organization_id == org.id, Team.code == code)
        )
        if row:
            return row
        return await svc.create_team(org.id, name, code, dept_id)

    async def get_or_create_role(name: str, code: str, perms: list, scope: str):
        row = await db.scalar(
            select(Role).where(Role.organization_id == org.id, Role.code == code)
        )
        if row:
            await svc.grant_role_permissions(row.id, perms)
            return row
        return await svc.create_role(org.id, name, code, perms, scope)

    branch = await get_or_create_branch("شعبهٔ تهران", "THR", "تهران")
    mashhad = await get_or_create_branch("شعبهٔ مشهد", "MHD", "مشهد")
    marzdaran = await get_or_create_branch("مرزداران", "MZD", "تهران")
    kashani = await get_or_create_branch("کاشانی", "KSH", "تهران")
    iranmall = await get_or_create_branch("ایرانمال", "IRM", "تهران")
    sales_dept = await get_or_create_dept("فروش", "SALES")
    mkt_dept = await get_or_create_dept("بازاریابی", "MKT")
    ops_dept = await get_or_create_dept("عملیات", "OPS")
    fin_dept = await get_or_create_dept("مالی", "FIN")
    sales_team = await get_or_create_team("تیم فروش تهران", "SALES_T", sales_dept.id)
    mkt_team = await get_or_create_team("تیم بازاریابی", "MKT_T", mkt_dept.id)

    admin_role = await get_or_create_role(
        "ادمین سایت", "admin", [p.value for p in PermissionCode], "organization"
    )
    if admin_role.name != "ادمین سایت":
        admin_role.name = "ادمین سایت"
    from app.models import DataScope

    admin_scope = await db.scalar(select(DataScope).where(DataScope.role_id == admin_role.id))
    if admin_scope and admin_scope.level != "organization":
        admin_scope.level = "organization"
    manager_role = await get_or_create_role(
        "Manager",
        "manager",
        [
            PC.ORG_ADMIN,
            PC.USER_READ,
            PC.USER_WRITE,
            PC.RELATIONSHIP_WRITE,
            PC.CONVERSATION_READ,
            PC.CONVERSATION_WRITE,
            PC.WORK_ITEM_READ,
            PC.WORK_ITEM_WRITE,
            PC.CASE_READ,
            PC.CASE_WRITE,
            PC.TASK_READ,
            PC.TASK_WRITE,
            PC.TASK_ASSIGN,
            PC.TASK_DELEGATE,
            PC.NOTIFICATION_READ,
            PC.EVENT_READ,
            PC.SLA_MANAGE,
            PC.INVENTORY_READ,
            PC.INVENTORY_WRITE,
            PC.SEARCH,
            PC.RAG_READ,
            PC.RAG_INDEX,
            PC.AGENT_RUN,
            PC.KB_READ,
            PC.KB_WRITE,
            PC.CUSTOMER_READ,
            PC.CUSTOMER_WRITE,
            PC.CAMPAIGN_READ,
            PC.CAMPAIGN_WRITE,
        ],
        "branch",
    )
    seller_role = await get_or_create_role(
        "Seller",
        "seller",
        [
            PC.CONVERSATION_READ,
            PC.CONVERSATION_WRITE,
            PC.WORK_ITEM_READ,
            PC.CASE_READ,
            PC.TASK_READ,
            PC.TASK_WRITE,
            PC.NOTIFICATION_READ,
            PC.INVENTORY_READ,
            PC.SEARCH,
            PC.RAG_READ,
            PC.KB_READ,
            PC.CUSTOMER_READ,
            PC.EVENT_READ,
            PC.CAMPAIGN_READ,
        ],
        "team",
    )
    mkt_role = await get_or_create_role(
        "Marketing",
        "marketing",
        [
            PC.CONVERSATION_READ,
            PC.CONVERSATION_WRITE,
            PC.WORK_ITEM_READ,
            PC.CASE_READ,
            PC.TASK_READ,
            PC.TASK_WRITE,
            PC.NOTIFICATION_READ,
            PC.INVENTORY_READ,
            PC.SEARCH,
            PC.RAG_READ,
            PC.KB_READ,
            PC.EVENT_READ,
            PC.CAMPAIGN_READ,
            PC.CAMPAIGN_WRITE,
        ],
        "team",
    )
    mkt_mgr_role = await get_or_create_role(
        "مدیر مارکتینگ",
        "marketing_manager",
        [
            PC.CONVERSATION_READ,
            PC.CONVERSATION_WRITE,
            PC.WORK_ITEM_READ,
            PC.CASE_READ,
            PC.TASK_READ,
            PC.TASK_WRITE,
            PC.NOTIFICATION_READ,
            PC.INVENTORY_READ,
            PC.SEARCH,
            PC.RAG_READ,
            PC.KB_READ,
            PC.EVENT_READ,
            PC.CAMPAIGN_READ,
            PC.CAMPAIGN_WRITE,
            PC.PERF_READ,
            PC.PERF_WRITE,
            PC.PERF_APPROVE,
            PC.REQUEST_TRIAGE,
            PC.REQUEST_MANAGE,
            PC.EXPENSE_REQUEST,
        ],
        "team",
    )
    perf_role = await get_or_create_role(
        "پرفورمنس مارکتینگ",
        "performance_marketing",
        [
            PC.CONVERSATION_READ,
            PC.CONVERSATION_WRITE,
            PC.NOTIFICATION_READ,
            PC.INVENTORY_READ,
            PC.SEARCH,
            PC.RAG_READ,
            PC.KB_READ,
            PC.PERF_READ,
            PC.PERF_WRITE,
        ],
        "organization",
    )
    viewer_role = await get_or_create_role(
        "Viewer",
        "viewer",
        [PC.WORK_ITEM_READ, PC.NOTIFICATION_READ, PC.RAG_READ],
        "self",
    )
    finance_role = await get_or_create_role(
        "مالی",
        "finance",
        [
            PC.PRICE_WRITE,
            PC.EXPENSE_REQUEST,
            PC.EXPENSE_APPROVE,
            PC.INVENTORY_READ,
            PC.NOTIFICATION_READ,
            PC.CONVERSATION_READ,
            PC.CONVERSATION_WRITE,
            PC.USER_READ,
            PC.CAMPAIGN_READ,
            PC.RAG_READ,
            PC.PERF_READ,
        ],
        "organization",
    )
    maker_perms = [
        PC.TASK_READ,
        PC.TASK_WRITE,
        PC.CONVERSATION_READ,
        PC.CONVERSATION_WRITE,
        PC.NOTIFICATION_READ,
        PC.REQUEST_CREATE,
    ]
    design_role = await get_or_create_role("طراح", "designer", maker_perms, "team")
    film_role = await get_or_create_role("فیلم‌بردار", "filmmaker", maker_perms, "team")

    async def get_or_create_user(
        email: str,
        full_name: str,
        role_id,
        *,
        branch_id=None,
        department_id=None,
        team_id=None,
        manager_id=None,
    ):
        row = await db.scalar(
            select(User).where(User.organization_id == org.id, User.email == email)
        )
        if row:
            return row
        return await svc.create_user(
            organization_id=org.id,
            email=email,
            full_name=full_name,
            password="password",
            role_id=role_id,
            branch_id=branch_id,
            department_id=department_id,
            team_id=team_id,
            manager_id=manager_id,
        )

    ali = await get_or_create_user(
        "ali@autoco.example",
        "علی مدیر",
        manager_role.id,
        branch_id=branch.id,
        department_id=sales_dept.id,
    )
    reza = await get_or_create_user(
        "reza@autoco.example",
        "رضا فروشنده",
        seller_role.id,
        branch_id=branch.id,
        department_id=sales_dept.id,
        team_id=sales_team.id,
        manager_id=ali.id,
    )
    sara = await get_or_create_user(
        "sara@autoco.example",
        "سارا بازاریابی",
        mkt_role.id,
        branch_id=branch.id,
        department_id=mkt_dept.id,
        team_id=mkt_team.id,
        manager_id=ali.id,
    )
    nima = await get_or_create_user(
        "nima@autoco.example",
        "نیما عملیات",
        seller_role.id,
        branch_id=branch.id,
        department_id=ops_dept.id,
        manager_id=ali.id,
    )
    maryam = await get_or_create_user(
        "maryam@autoco.example",
        "مریم مدیر شعبه مشهد",
        manager_role.id,
        branch_id=mashhad.id,
        department_id=sales_dept.id,
    )
    viewer = await get_or_create_user(
        "viewer@autoco.example",
        "بازدیدکننده محدود",
        viewer_role.id,
        branch_id=branch.id,
    )
    site_admin = await get_or_create_user(
        "admin@autoco.example",
        "ادمین سایت",
        admin_role.id,
        branch_id=branch.id,
    )
    finance = await get_or_create_user(
        "finance@autoco.example",
        "ندا مالی",
        finance_role.id,
        branch_id=branch.id,
        department_id=fin_dept.id,
    )
    mina = await get_or_create_user(
        "mina@autoco.example",
        "مینا مدیر مارکتینگ",
        mkt_mgr_role.id,
        branch_id=branch.id,
        department_id=mkt_dept.id,
        team_id=mkt_team.id,
        manager_id=ali.id,
    )
    if mina.role_id != mkt_mgr_role.id:
        mina.role_id = mkt_mgr_role.id
    nadia = await get_or_create_user(
        "nadia@autoco.example",
        "نادیا پرفورمنس",
        perf_role.id,
        branch_id=branch.id,
        department_id=mkt_dept.id,
        team_id=mkt_team.id,
        manager_id=mina.id,
    )
    await get_or_create_user(
        "leila@autoco.example",
        "لیلا طراح",
        design_role.id,
        branch_id=branch.id,
        department_id=mkt_dept.id,
        team_id=mkt_team.id,
        manager_id=mina.id,
    )
    await get_or_create_user(
        "kamran@autoco.example",
        "کامران فیلم‌بردار",
        film_role.id,
        branch_id=branch.id,
        department_id=mkt_dept.id,
        team_id=mkt_team.id,
        manager_id=mina.id,
    )

    from app.core.permissions import ROLE_TEMPLATES
    from app.models import DataScope

    template_roles: dict[str, Role] = {}
    for code, (name, scope, perms) in ROLE_TEMPLATES.items():
        level = scope.value if hasattr(scope, "value") else str(scope)
        role = await get_or_create_role(name, code, [item.value for item in perms], level)
        if role.name != name:
            role.name = name
        scope_row = await db.scalar(select(DataScope).where(DataScope.role_id == role.id))
        if scope_row and scope_row.level != level:
            scope_row.level = level
        template_roles[code] = role

    role_names = {
        "admin": "ادمین سایت",
        "requester": "مدیر",
        "lead": "سرپرست",
        "member": "عضو",
        "manager": "مدیر شعبه",
        "seller": "فروشنده",
        "marketing": "مارکتینگ",
        "marketing_manager": "مدیر مارکتینگ",
        "performance_marketing": "پرفورمنس مارکتینگ",
        "finance": "مالی",
        "designer": "طراح",
        "filmmaker": "فیلم‌بردار",
        "viewer": "بازدیدکننده",
    }
    for code, name in role_names.items():
        named = await db.scalar(select(Role).where(Role.organization_id == org.id, Role.code == code))
        if named and named.name != name:
            named.name = name

    async def team_under(name: str, code: str, dept_id, parent):
        row = await get_or_create_team(name, code, dept_id)
        if parent and row.parent_team_id != parent.id:
            row.parent_team_id = parent.id
            row.department_id = dept_id
        return row

    fin_team = await team_under("مالی", "FIN_T", fin_dept.id, None)
    perf_team = await team_under("پرفورمنس", "MKT_PERF", mkt_dept.id, mkt_team)
    design_team = await team_under("طراحی", "MKT_DESIGN", mkt_dept.id, mkt_team)
    film_team = await team_under("فیلم‌برداری", "MKT_FILM", mkt_dept.id, mkt_team)
    by_code = {
        "SALES_T": sales_team,
        "MKT_T": mkt_team,
        "FIN_T": fin_team,
        "MKT_PERF": perf_team,
        "MKT_DESIGN": design_team,
        "MKT_FILM": film_team,
    }
    # نگاشت صریح کاربران فعلی. ادمین و بازدیدکننده دست نمی‌خورند.
    # (قالب، تیم، بخش، شعبه یا None یعنی شعبهٔ فعلی بماند، قابلیت‌ها)
    assignment = {
        "ali@autoco.example": ("requester", "SALES_T", sales_dept.id, branch.id, []),
        "reza@autoco.example": ("member", "SALES_T", sales_dept.id, branch.id, []),
        "sara@autoco.example": ("member", "MKT_T", mkt_dept.id, branch.id, []),
        "mina@autoco.example": ("lead", "MKT_T", mkt_dept.id, branch.id, []),
        "finance@autoco.example": ("lead", "FIN_T", fin_dept.id, branch.id, [PC.EXPENSE_APPROVE, PC.PRICE_WRITE]),
        "maryam@autoco.example": ("requester", None, sales_dept.id, mashhad.id, []),
        "nima@autoco.example": ("member", None, ops_dept.id, branch.id, []),
        "nadia@autoco.example": ("lead", "MKT_PERF", mkt_dept.id, branch.id, [PC.PERF_READ, PC.PERF_WRITE, PC.CAMPAIGN_WRITE]),
        "leila@autoco.example": ("member", "MKT_DESIGN", mkt_dept.id, branch.id, []),
        "kamran@autoco.example": ("member", "MKT_FILM", mkt_dept.id, branch.id, []),
    }
    for email, (role_code, team_code, dept_id, branch_id, grants) in assignment.items():
        person = await db.scalar(select(User).where(User.organization_id == org.id, User.email == email))
        if not person:
            continue
        person.role_id = template_roles[role_code].id
        person.department_id = dept_id
        person.team_id = by_code[team_code].id if team_code else None
        if branch_id:
            person.branch_id = branch_id
        await svc.set_user_grants(person.id, grants)

    # Relationships (ignore duplicates via try/existing check)
    async def ensure_rel(frm, to, typ):
        from app.models import OrgRelationship

        exists = await db.scalar(
            select(OrgRelationship).where(
                OrgRelationship.organization_id == org.id,
                OrgRelationship.from_user_id == frm.id,
                OrgRelationship.to_user_id == to.id,
                OrgRelationship.relationship_type == typ,
            )
        )
        if not exists:
            await svc.add_relationship(org.id, frm.id, to.id, typ, ali.id)

    await ensure_rel(ali, reza, RelationshipType.MANAGES)
    await ensure_rel(reza, ali, RelationshipType.REPORTS_TO)
    await ensure_rel(reza, sara, RelationshipType.COLLABORATES_WITH)
    await ensure_rel(ali, sara, RelationshipType.MANAGES)
    await ensure_rel(ali, nima, RelationshipType.MANAGES)
    await _ensure_perf_panels(db, org.id)
    await _ensure_perf_demo(db, org.id, nadia, mina, branch.id)
    await _ensure_social_formats(db, org.id, nadia.id)

    return {
        "org": org,
        "branch": branch,
        "mashhad": mashhad,
        "sales_dept": sales_dept,
        "mkt_dept": mkt_dept,
        "sales_team": sales_team,
        "mkt_team": mkt_team,
        "ali": ali,
        "reza": reza,
        "sara": sara,
        "nima": nima,
        "maryam": maryam,
        "viewer": viewer,
        "finance": finance,
        "mina": mina,
        "nadia": nadia,
        "site_admin": site_admin,
        "marzdaran": marzdaran,
        "kashani": kashani,
        "iranmall": iranmall,
        "created": created_org,
    }


async def _ensure_perf_panels(db, organization_id) -> None:
    from app.perf.models import PmPanel

    specs = (
        ("isms", "آی‌اس‌ام‌اس", "50002100304010", 166),
        ("pishgam", "پیشگامان رایان", "5000302137682", 200),
    )
    for code, name, line, tariff in specs:
        row = await db.scalar(
            select(PmPanel).where(PmPanel.organization_id == organization_id, PmPanel.code == code)
        )
        if row:
            continue
        db.add(
            PmPanel(
                organization_id=organization_id,
                code=code,
                name=name,
                sender_line=line,
                tariff_toman=tariff,
                balance_toman=1_000_000,
                low_balance_toman=200_000,
            )
        )


async def _ensure_perf_demo(db, organization_id, nadia, mina, branch_id) -> None:
    """نمونه‌های واقعی‌نما از پنل پیامک، شیت هزینه و استوری. اگر باشد، دوباره ساخته نمی‌شود."""
    from datetime import date

    from app.perf.models import (
        PmCampaign,
        PmCarRequest,
        PmCost,
        PmPage,
        PmPanel,
        PmPaymentRequest,
        PmRecipient,
        PmRecipientList,
        PmSmsSend,
        PmStory,
    )
    from app.services import CommunicationService

    marked = await db.scalar(
        select(PmPage).where(PmPage.organization_id == organization_id, PmPage.name == "خودرو بانک")
    )
    if marked:
        return

    panels = {
        row.code: row
        for row in (
            await db.scalars(select(PmPanel).where(PmPanel.organization_id == organization_id))
        ).all()
    }
    isms = panels.get("isms")
    if isms and isms.balance_toman == 1_000_000:
        isms.balance_toman = 4_250_000

    async def campaign(code: str, title: str, brand: str, channels: str, budget: int, start: date, end: date):
        row = await db.scalar(
            select(PmCampaign).where(PmCampaign.organization_id == organization_id, PmCampaign.code == code)
        )
        if row:
            return row
        row = PmCampaign(
            organization_id=organization_id,
            code=code,
            title=title,
            brand=brand,
            goal="ورودی فروش",
            starts_on=start,
            ends_on=end,
            budget_toman=budget,
            status="active",
            channels=channels,
            created_by=nadia.id,
        )
        db.add(row)
        await db.flush()
        return row

    s84 = await campaign("S84", "فونیکس، تحویل فوری", "فونیکس", "sms,ig_story", 80_000_000, date(2026, 9, 1), date(2026, 9, 30))
    u85 = await campaign("U85", "ماموت خودرو U85", "ماموت", "sms,ig_story", 45_000_000, date(2026, 8, 20), date(2026, 9, 20))
    s90 = await db.scalar(
        select(PmCampaign).where(PmCampaign.organization_id == organization_id, PmCampaign.code == "S90")
    )
    if s90 and not s90.brand:
        s90.brand = "فونیکس"
        s90.channels = "sms,ig_story"
        s90.budget_toman = s90.budget_toman or 25_000_000

    page_specs = (
        ("خودرو بانک", 186_000, "خودرو", 2_400_000),
        ("ماشین‌بازها", 240_000, "بازار خودرو", 2_000_000),
        ("ستوده مگ", 92_000, "برند ستوده", 1_500_000),
        ("کارکرده ستوده", 74_000, "اقساط و کارکرده", 1_800_000),
    )
    pages: dict[str, PmPage] = {}
    for name, followers, topic, price in page_specs:
        row = PmPage(
            organization_id=organization_id,
            name=name,
            followers=followers,
            topic=topic,
            price_toman=price,
        )
        db.add(row)
        pages[name] = row
    await db.flush()

    stories = [
        (s84, pages["خودرو بانک"], date(2026, 9, 12), 2_400_000, 62_000, 51_000, 1_140, 41, 4_800),
        (s84, pages["ماشین‌بازها"], date(2026, 9, 14), 2_000_000, 48_500, 40_200, 860, 29, 3_100),
        (u85, pages["ستوده مگ"], date(2026, 9, 8), 1_500_000, 21_000, 18_400, 310, 12, 1_600),
        (s90, pages["کارکرده ستوده"], date(2026, 9, 28), 1_800_000, 33_000, 27_500, 540, 18, 2_200) if s90 else None,
    ]
    for item in stories:
        if not item or not item[0]:
            continue
        camp, page, day, cost, views, reach, clicks, leads, exited = item
        db.add(
            PmStory(
                organization_id=organization_id,
                campaign_id=camp.id,
                page_id=page.id,
                status="published",
                published_on=day,
                cost_toman=cost,
                views=views,
                reach=reach,
                link_clicks=clicks,
                replies=18,
                shares=7,
                exited=exited,
                leads=leads,
                created_by=nadia.id,
            )
        )

    sms_rows = []
    if isms:
        sms_rows.append((s84, 18_650, 2, 18_650 * 2 * isms.tariff_toman, 14_200, 86, date(2026, 9, 16)))
        sms_rows.append((u85, 9_400, 1, 9_400 * isms.tariff_toman, 7_100, 34, date(2026, 9, 6)))
        if s90:
            sms_rows.append((s90, 4_200, 2, 4_200 * 2 * isms.tariff_toman, 3_050, 19, date(2026, 9, 27)))
    for camp, count, pages_n, cost, delivered, leads, day in sms_rows:
        if not camp:
            continue
        db.add(
            PmSmsSend(
                organization_id=organization_id,
                campaign_id=camp.id,
                panel_id=isms.id if isms else None,
                sender_line=isms.sender_line if isms else "",
                body=f"{camp.brand} — {camp.title}. تحویل فوری. تماس ۰۲۱۴۷۶۷۷۷۷۷ لغو11",
                pages=pages_n,
                recipient_count=count,
                sent_at=datetime(day.year, day.month, day.day, 11, 0, tzinfo=UTC),
                cost_toman=cost,
                delivered_count=delivered,
                calls=leads // 2,
                leads=leads,
                created_by=nadia.id,
            )
        )

    numbers = [
        (s84, "فونیکس", "پیامک و استوری S84", 18_650 * 2 * (isms.tariff_toman if isms else 166) + 4_400_000, date(2026, 9, 16)),
        (u85, "ماموت", "پیامک و استوری U85", 9_400 * (isms.tariff_toman if isms else 166) + 1_500_000, date(2026, 9, 8)),
    ]
    for index, (camp, brand, detail, amount, day) in enumerate(numbers, start=120):
        db.add(
            PmCost(
                organization_id=organization_id,
                cost_number=index,
                spent_on=day,
                amount_toman=amount,
                kind="تبلیغ",
                detail=detail,
                brand=brand,
                campaign_code=camp.code,
                cost_center="پرفورمنس",
                description="ثبت‌شده در شیت هزینه",
                counts_for_cpl=True,
            )
        )
    if isms:
        db.add(
            PmPaymentRequest(
                organization_id=organization_id,
                kind="panel_charge",
                amount_toman=5_000_000,
                beneficiary="آی‌اس‌ام‌اس",
                iban="IR820120000000000000000000",
                panel_id=isms.id,
                cost_center="پرفورمنس",
                status="requested",
                note="شارژ آنلاین پنل پیامکی آی‌اس‌ام‌اس",
                requester_id=nadia.id,
            )
        )

    ready = PmRecipientList(
        organization_id=organization_id,
        campaign_id=s84.id,
        name="دیدار S84",
        source_filename="didar-s84.xlsx",
        raw_count=21_040,
        duplicate_count=980,
        blacklist_count=140,
        recent_count=1_180,
        invalid_count=90,
        final_count=18_650,
        created_by=nadia.id,
    )
    db.add(ready)
    await db.flush()
    for phone in ("989121001001", "989122002002", "989123003003", "989124004004", "989125005005"):
        db.add(PmRecipient(organization_id=organization_id, list_id=ready.id, phone=phone))

    db.add(
        PmCarRequest(
            organization_id=organization_id,
            raw_text="برای تیگو ۸ تحویل فوری، استوری روی پیج کارکرده و خودرو بانک لازم است.",
            brand="فونیکس",
            summary="استوری تیگو ۸، تحویل فوری",
            source="panel",
            status="planned",
            campaign_id=s84.id,
            created_by=mina.id,
        )
    )
    db.add(
        PmCarRequest(
            organization_id=organization_id,
            raw_text="کمپین U85 ماموت: دو استوری و یک پیامک روی لیست دیدار.",
            brand="ماموت",
            summary="برنامه U85 ماموت",
            source="panel",
            status="new",
            campaign_id=u85.id,
            created_by=nadia.id,
        )
    )

    comm = CommunicationService(db)
    conv = await comm.create_conversation(
        organization_id=organization_id,
        channel=Channel.WEB,
        participant_ids=[nadia.id, mina.id],
        topic="درخواست استوری تیگو ۸",
        branch_id=branch_id,
        actor_id=mina.id,
    )
    await comm.post_message(
        organization_id=organization_id,
        conversation_id=conv.id,
        sender_id=mina.id,
        text="تیگو ۸ موجود است. برای استوری، پیج کارکرده و خودرو بانک را با بودجه حدود ۴ میلیون در نظر بگیر.",
        channel=Channel.WEB,
    )
    await db.flush()


async def _ensure_social_formats(db, organization_id, nadia_id) -> None:
    """پست و بنر کنار استوری، داخل همان کمپین‌ها."""
    from datetime import date

    from app.perf.models import PmCampaign, PmPage, PmStory

    campaign = await db.scalar(
        select(PmCampaign).where(PmCampaign.organization_id == organization_id, PmCampaign.code == "S84")
    )
    if not campaign:
        return
    pages = {
        row.name: row
        for row in (await db.scalars(select(PmPage).where(PmPage.organization_id == organization_id))).all()
    }
    have = {
        row.kind
        for row in (
            await db.scalars(select(PmStory).where(PmStory.organization_id == organization_id, PmStory.campaign_id == campaign.id))
        ).all()
    }
    samples = (
        ("post", "ستوده مگ", date(2026, 9, 18), 1_800_000, 22_000, 18_000, 640, 11),
        ("banner", "خودرو بانک", date(2026, 9, 20), 3_200_000, 90_000, 70_000, 2_400, 22),
    )
    for kind, page_name, day, cost, views, reach, clicks, leads in samples:
        if kind in have or page_name not in pages:
            continue
        db.add(
            PmStory(
                organization_id=organization_id,
                campaign_id=campaign.id,
                page_id=pages[page_name].id,
                kind=kind,
                status="published",
                published_on=day,
                cost_toman=cost,
                views=views,
                reach=reach,
                link_clicks=clicks,
                leads=leads,
                created_by=nadia_id,
            )
        )
    await db.flush()


async def _ensure_campaigns(db, ctx) -> int:
    """Idempotent campaign + linked conversation for Communication UI."""
    org = ctx["org"]
    ali, sara = ctx["ali"], ctx["sara"]
    mkt_team = ctx["mkt_team"]
    branch = ctx["branch"]
    perms = {p.value for p in PermissionCode}
    camp_svc = CampaignService(db)
    comm = CommunicationService(db)

    created = 0
    demos = [
        {
            "title": "آگهی هیوندای توسان، شماره ۴۴۰",
            "description": "آگهی دیوار و شبکهٔ اجتماعی برای توسان موجود در شعبهٔ تهران.",
            "status": CampaignStatus.ACTIVE,
            "channel": Channel.WEB,
            "topic": "هماهنگی آگهی هیوندای توسان",
            "messages": [
                (sara.id, "آگهی توسان را شروع می‌کنم. برای انتشار به عکس واضح و یک کپشن فارسی نیاز داریم."),
                (sara.id, "فهرست را دیدم. پیش‌نویس آگهی را تا فردا آماده می‌کنم و برای تأیید می‌فرستم."),
            ],
        },
        {
            "title": "تبلیغات نوروزی موجودی شعبهٔ تهران",
            "description": "برنامهٔ تبلیغاتی نوروز برای خودروهایی که همین حالا در شعبهٔ تهران موجودند.",
            "status": CampaignStatus.DRAFT,
            "channel": Channel.WEB,
            "topic": "برنامهٔ تبلیغات نوروزی",
            "messages": [
                (sara.id, "برای نوروز بهتر است اول موجودی تهران را مرور کنیم و بعد بودجهٔ تبلیغات را قطعی کنیم."),
            ],
        },
    ]

    tucson = await db.scalar(
        select(Vehicle).where(
            Vehicle.organization_id == org.id, Vehicle.stock_number == "440"
        )
    )

    for demo in demos:
        existing = await db.scalar(
            select(Campaign).where(
                Campaign.organization_id == org.id, Campaign.title == demo["title"]
            )
        )
        if existing:
            continue
        camp = await camp_svc.create(
            organization_id=org.id,
            title=demo["title"],
            description=demo["description"],
            status=demo["status"],
            channel=demo["channel"],
            owner_id=sara.id,
            vehicle_id=tucson.id if tucson and "توسان" in demo["title"] else None,
            branch_id=branch.id,
            team_id=mkt_team.id if mkt_team else None,
            actor_id=ali.id,
            actor_permissions=perms,
        )
        conv = await comm.create_conversation(
            organization_id=org.id,
            channel=Channel.WEB,
            participant_ids=[sara.id],
            topic=demo["topic"],
            campaign_id=camp.id,
            vehicle_id=camp.vehicle_id,
            branch_id=branch.id,
            team_id=mkt_team.id if mkt_team else None,
            actor_id=ali.id,
        )
        for sender_id, text in demo["messages"]:
            await comm.post_message(
                organization_id=org.id,
                conversation_id=conv.id,
                sender_id=sender_id,
                text=text,
                channel=Channel.WEB,
            )
        created += 1
    return created


def _marketing_title(title: str) -> bool:
    text = title or ""
    return "توسان" in text or "آگهی" in text or "تبلیغ" in text or "کمپین" in text


async def _stamp_sections(db, ctx) -> int:
    """Put each existing project, case and campaign in its department.

    Marketing work stays with Sara. Everything else in this demo is sales.
    Ali is removed from marketing items so the sales home does not list them.
    """
    from sqlalchemy import delete

    from app.models import CommunicationCase, Conversation, Task, WorkItem, WorkItemParticipant
    from app.models.campaign import Campaign

    org = ctx["org"]
    ali, sara = ctx["ali"], ctx["sara"]
    sales_id = ali.department_id
    mkt_id = sara.department_id
    if not sales_id or not mkt_id:
        return 0

    work_items = list(
        (
            await db.scalars(select(WorkItem).where(WorkItem.organization_id == org.id))
        ).all()
    )
    changed = 0
    marketing_ids: set = set()
    for wi in work_items:
        if _marketing_title(wi.title):
            marketing_ids.add(wi.id)
            if wi.department_id != mkt_id or wi.owner_id != sara.id:
                wi.department_id = mkt_id
                wi.owner_id = sara.id
                changed += 1
        elif wi.department_id is None:
            wi.department_id = sales_id
            changed += 1

    if marketing_ids:
        await db.execute(
            delete(WorkItemParticipant).where(
                WorkItemParticipant.work_item_id.in_(marketing_ids),
                WorkItemParticipant.user_id == ali.id,
            )
        )
        tasks = list(
            (
                await db.scalars(select(Task).where(Task.work_item_id.in_(marketing_ids)))
            ).all()
        )
        for task in tasks:
            if task.owner_id == ali.id:
                task.owner_id = sara.id
                changed += 1

    cases = list(
        (
            await db.scalars(
                select(CommunicationCase).where(CommunicationCase.organization_id == org.id)
            )
        ).all()
    )
    work_by_id = {wi.id: wi for wi in work_items}
    for case in cases:
        parent = work_by_id.get(case.work_item_id) if case.work_item_id else None
        target = parent.department_id if parent and parent.department_id else sales_id
        if case.department_id != target:
            case.department_id = target
            changed += 1

    campaigns = list(
        (await db.scalars(select(Campaign).where(Campaign.organization_id == org.id))).all()
    )
    campaign_ids = []
    for camp in campaigns:
        campaign_ids.append(camp.id)
        if camp.department_id != mkt_id or camp.owner_id != sara.id:
            camp.department_id = mkt_id
            camp.owner_id = sara.id
            changed += 1

    if campaign_ids or marketing_ids:
        convs = list(
            (
                await db.scalars(
                    select(Conversation).where(Conversation.organization_id == org.id)
                )
            ).all()
        )
        from app.models import ConversationParticipant

        hide_ids = [
            conv.id
            for conv in convs
            if conv.campaign_id in campaign_ids or conv.work_item_id in marketing_ids
        ]
        if hide_ids:
            await db.execute(
                delete(ConversationParticipant).where(
                    ConversationParticipant.conversation_id.in_(hide_ids),
                    ConversationParticipant.user_id == ali.id,
                )
            )
    await db.flush()
    return changed


_VEHICLE_DETAIL_SEED: dict[str, dict] = {
    "124": {
        "trim": "LE",
        "purchase_price": 2_200_000_000,
        "body_type": "sedan",
        "transmission": "automatic",
        "fuel_type": "petrol",
        "engine": "2.5L",
        "doors": 4,
        "seats": 5,
        "plate_number": "12ب345-67",
        "options": "سانروف، دوربین عقب، کروز کنترل",
        "exterior_condition": "خوب — خط جزئی گلگیر",
        "interior_condition": "عالی",
        "description": (
            "تویوتا کمری ۲۰۲۰، سفید، کارکرد ۴۵ هزار کیلومتر. سرویس‌ها در نمایندگی انجام شده "
            "و خودرو آمادهٔ تحویل از شعبهٔ تهران است. برای خانواده مناسب است."
        ),
        "notes": "کلید یدک و دفترچهٔ سرویس همراه خودرو است.",
    },
    "210": {
        "trim": "Smart",
        "purchase_price": 1_650_000_000,
        "body_type": "sedan",
        "transmission": "automatic",
        "fuel_type": "petrol",
        "engine": "1.6L",
        "doors": 4,
        "seats": 5,
        "options": "صفحه لمسی، سنسور دنده عقب",
        "exterior_condition": "عالی",
        "interior_condition": "خوب",
        "description": (
            "هیوندای النترا ۲۰۲۱، نقره‌ای، کارکرد پایین. مصرفش برای شهر و مسیر بین‌شهری مناسب است "
            "و بدنه در وضعیت عالی است."
        ),
        "notes": "گلگیر عقب یک بار رنگ شده است.",
    },
    "307": {
        "trim": "پانوراما",
        "purchase_price": 850_000_000,
        "body_type": "hatchback",
        "transmission": "manual",
        "fuel_type": "petrol",
        "engine": "1.6L",
        "doors": 5,
        "seats": 5,
        "plate_number": "21ج112-33",
        "options": "سقف پانوراما، سنسور جلو و عقب",
        "exterior_condition": "متوسط — خط درب راننده",
        "interior_condition": "خوب",
        "description": (
            "پژو ۲۰۷ مدل ۲۰۱۹، قرمز، با سقف پانوراما. برای مشتری شعبهٔ مشهد رزرو شده است. "
            "پیش از تحویل باید دوباره کارشناسی شود."
        ),
        "notes": "رزرو تا پایان هفته معتبر است. انتقال را با شعبهٔ مشهد هماهنگ کنید.",
    },
    "440": {
        "trim": "Premium",
        "purchase_price": 2_950_000_000,
        "body_type": "SUV",
        "transmission": "automatic",
        "fuel_type": "petrol",
        "engine": "2.0L",
        "doors": 5,
        "seats": 5,
        "options": "AWD، صندلی برقی، دوربین ۳۶۰",
        "exterior_condition": "عالی",
        "interior_condition": "عالی",
        "description": (
            "هیوندای توسان ۲۰۲۲، مشکی، تیپ پرمیوم، کارکرد ۱۸ هزار کیلومتر. آپشن کامل است "
            "و هم برای نمایشگاه و هم برای مشتری سازمانی مناسب است."
        ),
        "notes": "گارانتی کارخانه تا شهریور ۱۴۰۵ برقرار است.",
    },
}


async def _enrich_vehicle_details(db, organization_id) -> int:
    """Backfill rich details on demo vehicles that were seeded before this feature."""
    updated = 0
    for stock, details in _VEHICLE_DETAIL_SEED.items():
        v = await db.scalar(
            select(Vehicle).where(
                Vehicle.organization_id == organization_id,
                Vehicle.stock_number == stock,
            )
        )
        if not v or v.description:
            continue
        for key, value in details.items():
            setattr(v, key, value)
        updated += 1
    await db.flush()
    return updated


async def _cover_operations(
    db,
    *,
    org,
    ali,
    reza,
    sara,
    nima,
    maryam,
    viewer,
    branch,
    now,
    perms,
    work,
    inv,
    kb,
    elantra,
    case_mashhad,
    t_done,
    **_unused,
) -> None:
    """بخش‌هایی که در داستان اصلی نیستند: موجودی کهنه، پیگیری بسته‌شده، تأیید، دیوار و روند هفتگی."""
    import json

    from app.models.divar import DivarListing
    from app.models.enterprise import KpiSnapshot
    from app.models.enums import CaseStatus, CaseType, Priority, SlaState, VehicleStatus
    from app.models.telegram import TelegramOutbox
    from app.services import write_audit
    from app.services.enterprise_ops import EnterpriseService

    aged = await inv.create_vehicle(
        organization_id=org.id,
        vin="NAS11100000000090",
        brand="سایپا",
        model="ساینا",
        year=2018,
        actor_id=ali.id,
        actor_permissions=perms,
        stock_number="090",
        color="سفید",
        mileage=142000,
        sale_price=420_000_000,
        purchase_price=390_000_000,
        branch_id=branch.id,
        status=VehicleStatus.IN_STOCK,
        body_type="هاچ‌بک",
        transmission="دستی",
        fuel_type="بنزین",
        description=(
            "سایپا ساینا ۱۳۹۷، سفید. بیش از سه ماه در انبار تهران مانده است "
            "و برای فروش یا انتقال به شعبهٔ دیگر نیاز به تصمیم دارد."
        ),
        notes="کارکرد بالا است. پیش از آگهی، قیمت را دوباره بررسی کنید.",
    )
    aged.created_at = now - timedelta(days=120)

    sold = await inv.create_vehicle(
        organization_id=org.id,
        vin="IRN55100000000551",
        brand="ایران‌خودرو",
        model="دنا پلاس",
        year=2021,
        actor_id=ali.id,
        actor_permissions=perms,
        stock_number="551",
        color="مشکی",
        mileage=61000,
        sale_price=980_000_000,
        purchase_price=910_000_000,
        branch_id=branch.id,
        status=VehicleStatus.SOLD,
        body_type="سدان",
        transmission="اتوماتیک",
        fuel_type="بنزین",
        description="ایران‌خودرو دنا پلاس ۱۴۰۰، مشکی. این خودرو فروخته شده و از انبار خارج شده است.",
        notes="تحویل به خریدار انجام شده است.",
    )
    sold.created_at = now - timedelta(days=40)

    follow = await work.create_case(
        organization_id=org.id,
        subject="پیگیری تست‌درایو هیوندای النترا برای فاطمه رضایی",
        case_type=CaseType.FOLLOW_UP,
        created_by=reza.id,
        owner_id=reza.id,
        priority=Priority.MEDIUM,
        branch_id=branch.id,
        vehicle_id=elantra.id,
        customer_id=_unused.get("c2").id if _unused.get("c2") is not None else None,
        deadline=now - timedelta(days=1),
    )
    await work.update_case(
        organization_id=org.id,
        case_id=follow.id,
        actor_id=reza.id,
        status=CaseStatus.COMPLETED,
    )
    follow.created_at = now - timedelta(days=6)
    follow.closed_at = now - timedelta(days=2)

    opportunity = await work.create_case(
        organization_id=org.id,
        subject="تصمیم دربارهٔ ساینا ۰۹۰ که در انبار مانده است",
        case_type=CaseType.INVENTORY_OPPORTUNITY,
        created_by=ali.id,
        owner_id=nima.id,
        priority=Priority.HIGH,
        branch_id=branch.id,
        vehicle_id=aged.id,
        deadline=now - timedelta(days=3),
    )
    opportunity.sla_state = SlaState.BREACHED

    case_mashhad.deadline = now - timedelta(days=1)
    case_mashhad.sla_state = SlaState.BREACHED

    if t_done.completed_at:
        t_done.completed_at = now - timedelta(days=3)
        t_done.created_at = now - timedelta(days=5)

    await EnterpriseService(db).request_approval(
        organization_id=org.id,
        requester_id=reza.id,
        kind="price_change",
        title="تخفیف برای تویوتا کمری ۱۲۴",
        payload={
            "stock_number": "124",
            "reason": "حسین احمدی برای قطعی کردن خرید، تخفیف محدود خواسته است.",
        },
        approver_ids=[ali.id],
    )
    if maryam is not None:
        await EnterpriseService(db).request_approval(
            organization_id=org.id,
            requester_id=maryam.id,
            kind="transfer",
            title="انتقال پژو ۲۰۷ قرمز به شعبهٔ مشهد",
            payload={
                "stock_number": "307",
                "reason": "مشتری شعبهٔ مشهد آمادهٔ تحویل است و خودرو باید از تهران منتقل شود.",
            },
            approver_ids=[ali.id],
        )

    from app.models.knowledge import DocumentCategory

    await kb.upload(
        organization_id=org.id,
        uploaded_by=ali.id,
        title="قاعدهٔ تغییر قیمت",
        category=DocumentCategory.SALES_RULES,
        content=(
            "تغییر قیمت فروش\n"
            "\n"
            "۱. قیمت روی کارت خودرو، همان قیمتی است که به مشتری گفته می‌شود.\n"
            "۲. تخفیف بیشتر از دو درصد فقط با تأیید مدیر ممکن است.\n"
            "۳. درخواست تخفیف را در بخش تأییدها ثبت کنید و دلیل را همان‌جا بنویسید.\n"
            "۴. تا پیش از تأیید، قیمت قبلی را به مشتری اعلام کنید.\n"
        ),
        filename="sales-price.txt",
        content_type="text/plain",
        actor_permissions=perms,
    )
    await kb.upload(
        organization_id=org.id,
        uploaded_by=ali.id,
        title="قاعدهٔ انتقال بین شعب",
        category=DocumentCategory.BRANCH_RULES,
        content=(
            "انتقال خودرو بین شعب\n"
            "\n"
            "۱. شعبهٔ درخواست‌کننده یک پیگیری با موضوع انتقال ثبت می‌کند.\n"
            "۲. شعبهٔ مبدأ موجود بودن خودرو و وضعیت رزرو را بررسی می‌کند.\n"
            "۳. انتقال فقط پس از تأیید مدیر انجام می‌شود.\n"
            "۴. تا پیش از رسیدن خودرو، آن را فروخته‌شده ثبت نکنید.\n"
        ),
        filename="branch-transfer.txt",
        content_type="text/plain",
        actor_permissions=perms,
    )

    db.add(
        DivarListing(
            organization_id=org.id,
            vehicle_id=elantra.id,
            created_by=sara.id,
            divar_product_id="demo-elantra-210",
            title="آگهی هیوندای النترا، شماره ۲۱۰",
            status="synced",
            last_error="عکس اصلی آگهی بارگذاری نشد. تصویر را دوباره بفرستید و سپس آگهی را منتشر کنید.",
        )
    )
    db.add(
        TelegramOutbox(
            organization_id=org.id,
            user_id=reza.id,
            provider="telegram",
            event_type="task.assigned",
            text="بررسی انتقال پژو ۲۰۷ به مشهد به شما سپرده شد.",
            entity_type="task",
            status="failed",
            last_error="پیام به تلگرام نرسید، چون حساب رضا هنوز به ربات وصل نشده است.",
            attempts=2,
        )
    )
    for weeks_ago, open_tasks, vehicles, cases in (
        (7, 4, 5, 2),
        (6, 5, 5, 2),
        (5, 5, 6, 3),
        (4, 6, 6, 3),
        (3, 6, 6, 4),
        (2, 7, 6, 4),
        (1, 7, 6, 5),
        (0, 7, 6, 5),
    ):
        snap = KpiSnapshot(
            organization_id=org.id,
            payload_json=json.dumps(
                {
                    "open_tasks": open_tasks,
                    "vehicles": vehicles,
                    "cases": cases,
                    "work_items": 4,
                }
            ),
        )
        snap.created_at = now - timedelta(days=7 * weeks_ago)
        db.add(snap)

    await write_audit(
        db,
        organization_id=org.id,
        actor_id=viewer.id,
        action="auth.login_failed",
        entity_type="user",
        entity_id=viewer.id,
        details={"reason": "رمز عبور نادرست بود."},
    )
    await db.flush()


async def _ensure_pricing_demo(db, ctx) -> int:
    """خودروهای شعب و سه پست امروز. اگر پست نمایشی باشد، دوباره ساخته نمی‌شود."""
    from app.models.pricing import PostSlot

    org = ctx["org"]
    sara = ctx["sara"]
    finance = ctx["finance"]
    existing = await db.scalar(
        select(PostSlot.id).where(PostSlot.organization_id == org.id, PostSlot.channel == "demo")
    )

    inv = InventoryService(db)
    perms = {p.value for p in PermissionCode}
    tehran = ctx["branch"]
    million = 1_000_000
    catalog = [
        ("POST-Q4", "آئودی", "Q4", "سفید و مشکی", 2024, "مرزداران", 15700),
        ("POST-FX", "آئودی", "FX", "سفید", 1403, "کاشانی", 6700),
        ("POST-TG7", "تیگو", "تیگو ۷ پرو", "سفید", 1403, "مرزداران", 18500),
        ("POST-A5", "آئودی", "A5", "مشکی", 1403, "کاشانی", 14200),
        ("POST-M5", "آریزو", "آریزو M5", "سفید", 1403, "مرزداران", 9800),
        ("POST-ID4", "فولکس", "ID4", "خاکستری", 2025, "ایرانمال", 21000),
        ("POST-X7", "بیجینگ", "بیجینگ X7", "مشکی", 1403, "مرزداران", 12500),
        ("POST-LC", "لوکانو", "لوکانو", "سبز", 1403, "کاشانی", 7800),
    ]
    by_stock: dict[str, Vehicle] = {}
    for stock, brand, model, color, year, branch_name, price_m in catalog:
        row = await db.scalar(
            select(Vehicle).where(Vehicle.organization_id == org.id, Vehicle.stock_number == stock)
        )
        if row is None:
            row = await inv.create_vehicle(
                organization_id=org.id,
                vin=stock,
                brand=brand,
                model=model,
                year=year,
                actor_id=finance.id,
                actor_permissions=perms,
                stock_number=stock,
                color=color,
                sale_price=price_m * million,
                branch_id=tehran.id,
                delivery_note=f"موجود در شعبه {branch_name}",
                status=VehicleStatus.IN_STOCK,
            )
        elif row.branch_id != tehran.id:
            row.branch_id = tehran.id
            row.delivery_note = row.delivery_note or f"موجود در شعبه {branch_name}"
        by_stock[stock] = row

    if existing:
        await db.flush()
        return 0

    offset = timedelta(hours=3, minutes=30)

    def at_hour(hour: int) -> datetime:
        local = datetime.now(UTC) + offset
        return local.replace(hour=hour, minute=0, second=0, microsecond=0) - offset

    now = datetime.now(UTC)
    specs = [
        ("POST-Q4", 11, "confirmed"),
        ("POST-FX", 14, "requested"),
        ("POST-ID4", 18, "needs_recheck"),
    ]
    for stock, hour, status in specs:
        vehicle = by_stock[stock]
        db.add(
            PostSlot(
                organization_id=org.id,
                vehicle_id=vehicle.id,
                post_at=at_hour(hour),
                slot_type="video",
                channel="demo",
                requester_id=sara.id,
                status=status,
                confirmed_price=vehicle.sale_price if status != "requested" else None,
                confirmed_by=finance.id if status == "confirmed" else None,
                confirmed_at=now if status == "confirmed" else None,
            )
        )
    await db.flush()
    return len(specs)


async def _ensure_work_spine(db, ctx) -> str:
    """یک درخواست تبلیغات با سه پروژه و یک درخواست عملیاتی قیمت. اگر کد موجود باشد دوباره ساخته نمی‌شود."""
    from app.core.permissions import PermissionCode
    from app.requests.models import WorkProject, WorkRequest
    from app.requests.spine import ensure_thread

    org = ctx["org"]
    existing = await db.scalar(select(WorkRequest).where(WorkRequest.organization_id == org.id, WorkRequest.code == "REQ-ADS"))
    if existing:
        return "present"
    ali = ctx["ali"]
    mina = ctx["mina"]
    team = ctx["mkt_team"]
    ads = WorkRequest(
        organization_id=org.id,
        code="REQ-ADS",
        title="تبلیغ فروش بهمن",
        description="سه تیم: پرفورمنس، طراحی، فیلم",
        kind="تبلیغات",
        status="converted",
        requested_by=ali.id,
        team_id=team.id,
        created_by=ali.id,
    )
    price = WorkRequest(
        organization_id=org.id,
        code="REQ-PRICE",
        title="اصلاح قیمت امروز",
        kind="قیمت و پست‌ها",
        status="converted",
        requested_by=ali.id,
        team_id=team.id,
        created_by=ali.id,
    )
    db.add(ads)
    db.add(price)
    await db.flush()
    work = WorkService(db)
    perms = {PermissionCode.TASK_WRITE.value}
    for kind, title in (("پرفورمنس", "کمپین پرفورمنس"), ("طراحی", "طرح بنر"), ("فیلم‌برداری", "فیلم شعبه")):
        project = WorkProject(
            organization_id=org.id,
            code=f"PRJ-{kind[:2]}",
            title=title,
            kind=kind,
            request_id=ads.id,
            team_id=team.id,
            lead_user_id=mina.id,
            status="in_progress",
            created_by=mina.id,
        )
        db.add(project)
        await db.flush()
        await work.create_task(
            organization_id=org.id,
            title=f"شروع {title}",
            owner_id=mina.id,
            project_id=project.id,
            request_id=ads.id,
            actor_permissions=perms,
        )
        await ensure_thread(db, organization_id=org.id, actor_id=mina.id, project_id=project.id, topic=title)
    await work.create_task(
        organization_id=org.id,
        title="اصلاح قیمت امروز",
        owner_id=mina.id,
        request_id=price.id,
        actor_permissions=perms,
    )
    await db.flush()
    return "added"


async def seed(*, reset: bool = False) -> dict:
    if reset:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    await _ensure_schema()
    async with AsyncSessionLocal() as db:
        ctx = await _ensure_org(db)
        org = ctx["org"]
        ali, reza, sara = ctx["ali"], ctx["reza"], ctx["sara"]
        maryam = ctx["maryam"]
        branch, mashhad = ctx["branch"], ctx["mashhad"]
        mkt_team = ctx["mkt_team"]

        existing = await db.scalar(
            select(Vehicle).where(
                Vehicle.organization_id == org.id, Vehicle.stock_number == "124"
            )
        )
        if existing:
            camps = await _ensure_campaigns(db, ctx)
            enriched = await _enrich_vehicle_details(db, org.id)
            stamped = await _stamp_sections(db, ctx)
            posts = await _ensure_pricing_demo(db, ctx)
            spine = await _ensure_work_spine(db, ctx)
            await db.commit()
            return {
                "status": "already_seeded",
                "org": org.slug,
                "hint": "stock #124 exists",
                "campaigns_added": camps,
                "vehicles_enriched": enriched,
                "sections_stamped": stamped,
                "posts_added": posts,
                "work_spine": spine,
                "login": _demo_logins(),
            }

        inv = InventoryService(db)
        work = WorkService(db)
        comm = CommunicationService(db)
        cust = CustomerService(db)
        kb = KnowledgeService(db)
        sla = SlaService(db)
        perms = {p.value for p in PermissionCode}

        # —— Customers ——
        c1 = await cust.create(
            organization_id=org.id,
            full_name="حسین احمدی",
            phone="09121234567",
            email="hossein@example.com",
            notes="خریدار تویوتا کمری سفید در شعبهٔ تهران. بودجه حدود ۲٫۵ میلیارد تومان است و بازدید حضوری هماهنگ شده.",
            actor_id=ali.id,
            actor_permissions=perms,
        )
        c2 = await cust.create(
            organization_id=org.id,
            full_name="فاطمه رضایی",
            phone="09129876543",
            notes="برای هیوندای النترا نقره‌ای درخواست بازدید داده و ترجیح می‌دهد تست‌درایو در شعبهٔ تهران باشد.",
            actor_id=reza.id,
            actor_permissions=perms,
        )
        await cust.create(
            organization_id=org.id,
            full_name="کانون خودرو پارس",
            phone="02188776655",
            notes="عرضه‌کننده است و یک پژو ۲۰۷ کارکرده برای خرید به شعبه پیشنهاد داده.",
            actor_id=ali.id,
            actor_permissions=perms,
        )

        # —— Vehicles ——
        camry = await inv.create_vehicle(
            organization_id=org.id,
            vin="JTDBR32E720012424",
            brand="Toyota",
            model="Camry",
            year=2020,
            actor_id=ali.id,
            actor_permissions=perms,
            stock_number="124",
            color="White",
            trim="LE",
            mileage=45000,
            sale_price=2_500_000_000,
            purchase_price=2_200_000_000,
            branch_id=branch.id,
            status=VehicleStatus.IN_STOCK,
            body_type="sedan",
            transmission="automatic",
            fuel_type="petrol",
            engine="2.5L",
            doors=4,
            seats=5,
            plate_number="12ب345-67",
            options="سانروف، دوربین عقب، کروز کنترل",
            exterior_condition="خوب — خط جزئی گلگیر",
            interior_condition="عالی",
            description=(
                "تویوتا کمری ۲۰۲۰، سفید، کارکرد ۴۵ هزار کیلومتر. سرویس‌ها در نمایندگی انجام شده "
                "و خودرو آمادهٔ تحویل از شعبهٔ تهران است. برای خانواده مناسب است."
            ),
            notes="کلید یدک و دفترچهٔ سرویس همراه خودرو است.",
        )
        elantra = await inv.create_vehicle(
            organization_id=org.id,
            vin="KMHD84LF5JU123456",
            brand="Hyundai",
            model="Elantra",
            year=2021,
            actor_id=ali.id,
            actor_permissions=perms,
            stock_number="210",
            color="Silver",
            trim="Smart",
            mileage=32000,
            sale_price=1_850_000_000,
            purchase_price=1_650_000_000,
            branch_id=branch.id,
            body_type="sedan",
            transmission="automatic",
            fuel_type="petrol",
            engine="1.6L",
            doors=4,
            seats=5,
            options="صفحه لمسی، سنسور دنده عقب",
            exterior_condition="عالی",
            interior_condition="خوب",
            description=(
                "هیوندای النترا ۲۰۲۱، نقره‌ای، کارکرد پایین. مصرفش برای شهر و مسیر بین‌شهری مناسب است "
                "و بدنه در وضعیت عالی است."
            ),
            notes="گلگیر عقب یک بار رنگ شده است.",
        )
        peugeot = await inv.create_vehicle(
            organization_id=org.id,
            vin="VF34C5FW0JS987654",
            brand="Peugeot",
            model="207",
            year=2019,
            actor_id=ali.id,
            actor_permissions=perms,
            stock_number="307",
            color="Red",
            trim="پانوراما",
            mileage=78000,
            sale_price=980_000_000,
            purchase_price=850_000_000,
            branch_id=mashhad.id,
            status=VehicleStatus.RESERVED,
            body_type="hatchback",
            transmission="manual",
            fuel_type="petrol",
            engine="1.6L",
            doors=5,
            seats=5,
            plate_number="21ج112-33",
            options="سقف پانوراما، سنسور جلو و عقب",
            exterior_condition="متوسط — خط درب راننده",
            interior_condition="خوب",
            description=(
                "پژو ۲۰۷ مدل ۲۰۱۹، قرمز، با سقف پانوراما. برای مشتری شعبهٔ مشهد رزرو شده است. "
                "پیش از تحویل باید دوباره کارشناسی شود."
            ),
            notes="رزرو تا پایان هفته معتبر است. انتقال را با شعبهٔ مشهد هماهنگ کنید.",
        )
        tucson = await inv.create_vehicle(
            organization_id=org.id,
            vin="KM8J3CA46KU555555",
            brand="Hyundai",
            model="Tucson",
            year=2022,
            actor_id=ali.id,
            actor_permissions=perms,
            stock_number="440",
            color="Black",
            trim="Premium",
            mileage=18000,
            sale_price=3_200_000_000,
            purchase_price=2_950_000_000,
            branch_id=branch.id,
            body_type="SUV",
            transmission="automatic",
            fuel_type="petrol",
            engine="2.0L",
            doors=5,
            seats=5,
            options="AWD، صندلی برقی، دوربین ۳۶۰",
            exterior_condition="عالی",
            interior_condition="عالی",
            description=(
                "هیوندای توسان ۲۰۲۲، مشکی، تیپ پرمیوم، کارکرد ۱۸ هزار کیلومتر. آپشن کامل است "
                "و هم برای نمایشگاه و هم برای مشتری سازمانی مناسب است."
            ),
            notes="گارانتی کارخانه تا شهریور ۱۴۰۵ برقرار است.",
        )

        # —— SLA ——
        policy = await sla.create_policy(
            organization_id=org.id,
            name="پیگیری فوری فروش",
            priority=Priority.HIGH,
            response_minutes=240,
            warning_minutes=120,
            escalate_on_breach=True,
        )

        now = datetime.now(UTC)

        # —— Shared work: Camry sell (main demo) ——
        wi_camry = await work.create_work_item(
            organization_id=org.id,
            title="فروش تویوتا کمری، شماره ۱۲۴",
            owner_id=ali.id,
            description="رضا خریدار را تا بازدید همراهی کند و سارا پیش‌نویس آگهی را برای تأیید آماده کند.",
            priority=Priority.HIGH,
            branch_id=branch.id,
            vehicle_id=camry.id,
            customer_id=c1.id,
            deadline=now + timedelta(days=3),
            participant_ids=[reza.id, sara.id],
        )
        t_reza = await work.create_task(
            organization_id=org.id,
            title="هماهنگی بازدید با حسین احمدی",
            owner_id=ali.id,
            work_item_id=wi_camry.id,
            description="زمان بازدید حضوری کمری سفید را با خریدار قطعی کنید.",
            assignee_ids=[reza.id],
            priority=Priority.HIGH,
            deadline=now + timedelta(hours=4),
            sla_policy_id=policy.id,
            actor_permissions=perms,
        )
        t_sara = await work.create_task(
            organization_id=org.id,
            title="آماده‌سازی پیش‌نویس آگهی دیوار",
            owner_id=ali.id,
            work_item_id=wi_camry.id,
            assignee_ids=[sara.id],
            assignment_target_type=AssignmentTargetType.TEAM,
            assignment_target_id=mkt_team.id if mkt_team else None,
            priority=Priority.HIGH,
            deadline=now + timedelta(hours=8),
            actor_permissions=perms,
        )
        t_ali = await work.create_task(
            organization_id=org.id,
            title="بررسی نتیجهٔ بازدید و تأیید قیمت",
            owner_id=ali.id,
            work_item_id=wi_camry.id,
            assignee_ids=[ali.id],
            priority=Priority.MEDIUM,
            deadline=now + timedelta(days=1),
            actor_permissions=perms,
        )
        await work.add_dependency(t_ali.id, t_reza.id, actor_id=ali.id)
        await work.add_dependency(t_ali.id, t_sara.id, actor_id=ali.id)

        case_camry = await work.create_case(
            organization_id=org.id,
            subject="علاقهٔ حسین احمدی به تویوتا کمری ۱۲۴",
            case_type=CaseType.CUSTOMER_INTEREST,
            created_by=ali.id,
            work_item_id=wi_camry.id,
            owner_id=reza.id,
            priority=Priority.HIGH,
            branch_id=branch.id,
            vehicle_id=camry.id,
            customer_id=c1.id,
            deadline=now + timedelta(hours=6),
            sla_policy_id=policy.id,
        )

        # —— Shared work: Elantra (partially done) ——
        wi_el = await work.create_work_item(
            organization_id=org.id,
            title="پیگیری فروش هیوندای النترا، شماره ۲۱۰",
            owner_id=ali.id,
            priority=Priority.MEDIUM,
            branch_id=branch.id,
            vehicle_id=elantra.id,
            customer_id=c2.id,
            participant_ids=[reza.id],
        )
        t_done = await work.create_task(
            organization_id=org.id,
            title="ارسال مشخصات النترا برای فاطمه رضایی",
            owner_id=ali.id,
            work_item_id=wi_el.id,
            assignee_ids=[reza.id],
            actor_permissions=perms,
        )
        await work.complete_task(t_done.id, reza.id)
        await work.create_task(
            organization_id=org.id,
            title="هماهنگی زمان تست‌درایو",
            owner_id=ali.id,
            work_item_id=wi_el.id,
            assignee_ids=[reza.id],
            deadline=now + timedelta(days=2),
            actor_permissions=perms,
        )

        # —— Overdue task for demo ——
        wi_old = await work.create_work_item(
            organization_id=org.id,
            title="پاسخ به درخواست انتقال پژو ۲۰۷ به مشهد",
            owner_id=ali.id,
            priority=Priority.URGENT,
            branch_id=mashhad.id if mashhad else branch.id,
            vehicle_id=peugeot.id,
            participant_ids=[reza.id, maryam.id] if maryam else [reza.id],
        )
        await work.create_task(
            organization_id=org.id,
            title="بررسی و تأیید امکان انتقال به مشهد",
            owner_id=ali.id,
            work_item_id=wi_old.id,
            assignee_ids=[reza.id],
            deadline=now - timedelta(hours=6),  # overdue
            priority=Priority.URGENT,
            actor_permissions=perms,
        )
        case_mashhad = await work.create_case(
            organization_id=org.id,
            subject="درخواست شعبهٔ مشهد برای انتقال پژو ۲۰۷ قرمز",
            case_type=CaseType.BRANCH_REQUEST,
            created_by=maryam.id if maryam else ali.id,
            work_item_id=wi_old.id,
            owner_id=reza.id,
            priority=Priority.HIGH,
            branch_id=mashhad.id if mashhad else branch.id,
            vehicle_id=peugeot.id,
        )

        # —— Marketing-only listing work ——
        wi_mkt = await work.create_work_item(
            organization_id=org.id,
            title="آماده‌سازی آگهی هیوندای توسان، شماره ۴۴۰",
            owner_id=sara.id,
            priority=Priority.MEDIUM,
            vehicle_id=tucson.id,
            department_id=sara.department_id,
        )
        await work.create_task(
            organization_id=org.id,
            title="عکس‌برداری از توسان و نوشتن متن آگهی",
            owner_id=sara.id,
            work_item_id=wi_mkt.id,
            assignee_ids=[sara.id],
            assignment_target_type=AssignmentTargetType.TEAM,
            assignment_target_id=mkt_team.id if mkt_team else None,
            deadline=now + timedelta(days=1),
            actor_permissions=perms,
        )

        # —— Campaigns (also linked from Communication) ——
        await _ensure_campaigns(db, ctx)

        # —— Conversations ——
        conv1 = await comm.create_conversation(
            organization_id=org.id,
            channel=Channel.WEB,
            participant_ids=[ali.id, reza.id, sara.id],
            topic="هماهنگی فروش تویوتا کمری ۱۲۴",
            work_item_id=wi_camry.id,
            case_id=case_camry.id,
            vehicle_id=camry.id,
            branch_id=branch.id,
            actor_id=ali.id,
        )
        await comm.post_message(
            organization_id=org.id,
            conversation_id=conv1.id,
            sender_id=ali.id,
            text="رضا، امروز با حسین هماهنگ کن که فردا برای بازدید کمری به شعبه بیاید. سارا، پیش‌نویس آگهی را تا قبل از بازدید آماده کن.",
            channel=Channel.WEB,
        )
        await comm.post_message(
            organization_id=org.id,
            conversation_id=conv1.id,
            sender_id=reza.id,
            text="با حسین صحبت کردم. فردا ساعت ۱۱ برای بازدید کمری سفید به شعبهٔ تهران می‌آید.",
            channel=Channel.WEB,
        )
        await comm.post_message(
            organization_id=org.id,
            conversation_id=conv1.id,
            sender_id=sara.id,
            text="پیش‌نویس آگهی آماده است. بعد از تأیید شما آن را منتشر می‌کنم.",
            channel=Channel.WEB,
        )

        conv2 = await comm.create_conversation(
            organization_id=org.id,
            channel=Channel.WEB,
            participant_ids=[ali.id, maryam.id] if maryam else [ali.id, reza.id],
            topic="درخواست انتقال پژو ۲۰۷ به مشهد",
            work_item_id=wi_old.id,
            vehicle_id=peugeot.id,
            actor_id=maryam.id if maryam else ali.id,
        )
        await comm.post_message(
            organization_id=org.id,
            conversation_id=conv2.id,
            sender_id=maryam.id if maryam else ali.id,
            text="شعبهٔ مشهد برای این پژو ۲۰۷ قرمز مشتری دارد. لطفاً امکان انتقال خودرو را بررسی کنید.",
            channel=Channel.WEB,
        )

        # —— Knowledge ——
        from app.models.knowledge import DocumentCategory

        await kb.upload(
            organization_id=org.id,
            uploaded_by=ali.id,
            title="دستور پیگیری مشتری",
            category=DocumentCategory.COMMUNICATION_RULES,
            content=(
                "پیگیری علاقهٔ مشتری\n"
                "\n"
                "۱. هر علاقهٔ تازه را حداکثر تا دو ساعت بعد پیگیری کنید.\n"
                "۲. برای فروش هر خودرو یک پروژه بسازید و کار فروش و آگهی را جداگانه بسپارید.\n"
                "۳. قیمت را بدون تأیید مدیر تغییر ندهید.\n"
                "۴. درخواست شعبه را به‌صورت پیگیری ثبت کنید و یک مسئول مشخص برایش بگذارید.\n"
            ),
            filename="sop-followup.txt",
            content_type="text/plain",
            actor_permissions=perms,
        )

        await _cover_operations(
            db,
            org=org,
            ali=ali,
            reza=reza,
            sara=sara,
            nima=ctx["nima"],
            maryam=maryam,
            viewer=ctx["viewer"],
            branch=branch,
            mashhad=mashhad,
            now=now,
            perms=perms,
            work=work,
            inv=inv,
            cust=cust,
            kb=kb,
            camry=camry,
            elantra=elantra,
            peugeot=peugeot,
            tucson=tucson,
            c1=c1,
            c2=c2,
            case_mashhad=case_mashhad,
            t_done=t_done,
        )

        # —— Extra notifications for Home attention ——
        await notify(
            db,
            organization_id=org.id,
            user_id=ali.id,
            title="انتقال پژو ۲۰۷ به مشهد هنوز باز است",
            body="مهلت بررسی انتقال گذشته است. لطفاً امروز دربارهٔ امکان انتقال تصمیم بگیرید.",
            entity_type="work_item",
            entity_id=wi_old.id,
        )
        await notify(
            db,
            organization_id=org.id,
            user_id=reza.id,
            title="بازدید فردا، تویوتا کمری ۱۲۴",
            body="حسین احمدی ساعت ۱۱ به شعبهٔ تهران می‌آید. خودرو را برای بازدید آماده کنید.",
            entity_type="task",
            entity_id=t_reza.id,
        )

        await _stamp_sections(db, ctx)
        posts = await _ensure_pricing_demo(db, ctx)
        spine = await _ensure_work_spine(db, ctx)
        await db.commit()
        return {
            "status": "ok",
            "org": org.slug,
            "vehicles": 6,
            "customers": 3,
            "work_items": 4,
            "campaigns": 2,
            "posts_added": posts,
            "work_spine": spine,
            "login": _demo_logins(),
        }


def _demo_logins() -> dict:
    return {
        "slug": "autoco",
        "admin": "admin@autoco.example / password",
        "manager": "ali@autoco.example / password",
        "seller": "reza@autoco.example / password",
        "marketing": "sara@autoco.example / password",
        "marketing_manager": "mina@autoco.example / password",
        "performance": "nadia@autoco.example / password",
        "finance": "finance@autoco.example / password",
        "designer": "leila@autoco.example / password",
        "filmmaker": "kamran@autoco.example / password",
        "mashhad": "maryam@autoco.example / password",
    }


def main() -> None:
    import sys

    result = asyncio.run(seed(reset="--reset" in sys.argv))
    print(result)


if __name__ == "__main__":
    main()
