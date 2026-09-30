"""Seed rich demo data for UI walkthrough.

Usage:
  cd backend
  uv run python -m scripts.seed_demo

Idempotent: skips if vehicle stock #124 already exists for org `autoco`.
Creates org + people if missing (same passwords as tests: password).
"""

from __future__ import annotations

import asyncio
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
    CaseType,
    Channel,
    Priority,
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

    branch = await get_or_create_branch("تهران / Tehran", "THR", "Tehran")
    mashhad = await get_or_create_branch("مشهد / Mashhad", "MHD", "Mashhad")
    sales_dept = await get_or_create_dept("فروش / Sales", "SALES")
    mkt_dept = await get_or_create_dept("بازاریابی / Marketing", "MKT")
    ops_dept = await get_or_create_dept("عملیات / Operations", "OPS")
    sales_team = await get_or_create_team("تیم فروش الف", "SALES_T", sales_dept.id)
    mkt_team = await get_or_create_team("تیم مارکتینگ", "MKT_T", mkt_dept.id)

    await get_or_create_role(
        "Admin", "admin", [p.value for p in PermissionCode], "organization"
    )
    manager_role = await get_or_create_role(
        "Manager",
        "manager",
        [
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
    viewer_role = await get_or_create_role(
        "Viewer", "viewer", [PC.WORK_ITEM_READ, PC.NOTIFICATION_READ], "self"
    )

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
        "created": created_org,
    }


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
            "title": "کمپین آگهی Tucson #440",
            "description": "آگهی دیوار و اینستاگرام برای توسان انبار #440",
            "status": CampaignStatus.ACTIVE,
            "channel": Channel.WEB,
            "topic": "هماهنگی کمپین Tucson #440",
            "messages": [
                (ali.id, "سارا کمپین توسان رو شروع کن؛ عکس و کپشن فارسی لازم داریم."),
                (sara.id, "لیست کمپین رو دیدم — پیش‌نویس آگهی تا فردا آماده می‌شه."),
            ],
        },
        {
            "title": "کمپین نوروزی موجودی تهران",
            "description": "پکیج تبلیغاتی نوروز برای خودروهای موجود شعبه تهران",
            "status": CampaignStatus.DRAFT,
            "channel": Channel.WEB,
            "topic": "برنامه‌ریزی کمپین نوروزی",
            "messages": [
                (sara.id, "برای نوروز لیست کمپین‌ها رو مرور کنیم و بودجه را قطعی کنیم."),
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
            vehicle_id=tucson.id if tucson and "Tucson" in demo["title"] else None,
            branch_id=branch.id,
            team_id=mkt_team.id if mkt_team else None,
            actor_id=ali.id,
            actor_permissions=perms,
        )
        conv = await comm.create_conversation(
            organization_id=org.id,
            channel=Channel.WEB,
            participant_ids=[ali.id, sara.id],
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
            "تویوتا کمری ۲۰۲۰ سفید، کارکرد ۴۵ هزار، سرویس منظم نمایندگی. "
            "مناسب خانواده؛ آماده تحویل از شعبه تهران."
        ),
        "notes": "کلید یدک و دفترچه سرویس موجود است.",
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
            "هیوندای النترا ۲۰۲۱ نقره‌ای با کارکرد پایین. "
            "مصرف اقتصادی؛ مناسب استفاده شهری و بین‌شهری."
        ),
        "notes": "یک بار رنگ گلگیر عقب.",
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
            "پژو ۲۰۷ ۲۰۱۹ قرمز، سقف پانوراما. رزرو شده برای مشتری مشهد؛ "
            "قبل از تحویل کارشناسی مجدد انجام شود."
        ),
        "notes": "رزرو تا پایان هفته؛ هماهنگی با شعبه مشهد.",
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
            "هیوندای توسان ۲۰۲۲ مشکی پرمیوم، کارکرد ۱۸ هزار. "
            "آپشن کامل؛ مناسب نمایشگاه و مشتری سازمانی."
        ),
        "notes": "گارانتی کارخانه تا ۱۴۰۵/۰۶.",
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


async def seed() -> dict:
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
            await db.commit()
            return {
                "status": "already_seeded",
                "org": org.slug,
                "hint": "stock #124 exists",
                "campaigns_added": camps,
                "vehicles_enriched": enriched,
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
            full_name="حسین خریدار",
            phone="09121234567",
            email="hossein@example.com",
            notes="علاقه‌مند به کمری سفید؛ بودجه حدود ۲٫۵ میلیارد",
            actor_id=ali.id,
            actor_permissions=perms,
        )
        c2 = await cust.create(
            organization_id=org.id,
            full_name="فاطمه رضایی",
            phone="09129876543",
            notes="درخواست بازدید النترا — شعبه تهران",
            actor_id=reza.id,
            actor_permissions=perms,
        )
        await cust.create(
            organization_id=org.id,
            full_name="کانون خودرو پارس (فروشنده)",
            phone="02188776655",
            notes="پیشنهاد خرید پژو ۲۰۷ کارکرده",
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
                "تویوتا کمری ۲۰۲۰ سفید، کارکرد ۴۵ هزار، سرویس منظم نمایندگی. "
                "مناسب خانواده؛ آماده تحویل از شعبه تهران."
            ),
            notes="کلید یدک و دفترچه سرویس موجود است.",
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
                "هیوندای النترا ۲۰۲۱ نقره‌ای با کارکرد پایین. "
                "مصرف اقتصادی؛ مناسب استفاده شهری و بین‌شهری."
            ),
            notes="یک بار رنگ گلگیر عقب.",
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
                "پژو ۲۰۷ ۲۰۱۹ قرمز، سقف پانوراما. رزرو شده برای مشتری مشهد؛ "
                "قبل از تحویل کارشناسی مجدد انجام شود."
            ),
            notes="رزرو تا پایان هفته؛ هماهنگی با شعبه مشهد.",
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
                "هیوندای توسان ۲۰۲۲ مشکی پرمیوم، کارکرد ۱۸ هزار. "
                "آپشن کامل؛ مناسب نمایشگاه و مشتری سازمانی."
            ),
            notes="گارانتی کارخانه تا ۱۴۰۵/۰۶.",
        )

        # —— SLA ——
        policy = await sla.create_policy(
            organization_id=org.id,
            name="پیگیری فروش فوری",
            priority=Priority.HIGH,
            response_minutes=240,
            warning_minutes=120,
            escalate_on_breach=True,
        )

        now = datetime.now(UTC)

        # —— Shared work: Camry sell (main demo) ——
        wi_camry = await work.create_work_item(
            organization_id=org.id,
            title="فروش Camry #124",
            owner_id=ali.id,
            description="برای این کمری، رضا مشتری را پیگیری کند و سارا آگهی را آماده کند.",
            priority=Priority.HIGH,
            branch_id=branch.id,
            vehicle_id=camry.id,
            customer_id=c1.id,
            deadline=now + timedelta(days=3),
            participant_ids=[reza.id, sara.id],
        )
        t_reza = await work.create_task(
            organization_id=org.id,
            title="تماس و پیگیری با حسین خریدار",
            owner_id=ali.id,
            work_item_id=wi_camry.id,
            description="هماهنگ کردن بازدید حضوری",
            assignee_ids=[reza.id],
            priority=Priority.HIGH,
            deadline=now + timedelta(hours=4),
            sla_policy_id=policy.id,
            actor_permissions=perms,
        )
        t_sara = await work.create_task(
            organization_id=org.id,
            title="آماده‌سازی آگهی دیوار / مارکتینگ",
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
            title="بررسی نتیجه و تأیید قیمت",
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
            subject="علاقه حسین به Camry #124",
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
            title="پیگیری فروش Elantra #210",
            owner_id=ali.id,
            priority=Priority.MEDIUM,
            branch_id=branch.id,
            vehicle_id=elantra.id,
            customer_id=c2.id,
            participant_ids=[reza.id],
        )
        t_done = await work.create_task(
            organization_id=org.id,
            title="ارسال مشخصات برای فاطمه",
            owner_id=ali.id,
            work_item_id=wi_el.id,
            assignee_ids=[reza.id],
            actor_permissions=perms,
        )
        await work.complete_task(t_done.id, reza.id)
        await work.create_task(
            organization_id=org.id,
            title="هماهنگی تست‌درایو",
            owner_id=ali.id,
            work_item_id=wi_el.id,
            assignee_ids=[reza.id],
            deadline=now + timedelta(days=2),
            actor_permissions=perms,
        )

        # —— Overdue task for demo ——
        wi_old = await work.create_work_item(
            organization_id=org.id,
            title="پاسخ به درخواست شعبه مشهد — Peugeot #307",
            owner_id=ali.id,
            priority=Priority.URGENT,
            branch_id=mashhad.id if mashhad else branch.id,
            vehicle_id=peugeot.id,
            participant_ids=[reza.id, maryam.id] if maryam else [reza.id],
        )
        await work.create_task(
            organization_id=org.id,
            title="تأیید امکان انتقال به مشهد",
            owner_id=ali.id,
            work_item_id=wi_old.id,
            assignee_ids=[reza.id],
            deadline=now - timedelta(hours=6),  # overdue
            priority=Priority.URGENT,
            actor_permissions=perms,
        )
        await work.create_case(
            organization_id=org.id,
            subject="درخواست شعبه مشهد برای ۲۰۷ قرمز",
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
            title="کمپین آگهی Tucson #440",
            owner_id=ali.id,
            priority=Priority.MEDIUM,
            vehicle_id=tucson.id,
            participant_ids=[sara.id],
        )
        await work.create_task(
            organization_id=org.id,
            title="عکس‌برداری و کپشن فارسی",
            owner_id=ali.id,
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
            topic="هماهنگی فروش Camry #124",
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
            text="رضا مشتری رو امروز پیگیری کن؛ سارا آگهی رو آماده کنه.",
            channel=Channel.WEB,
        )
        await comm.post_message(
            organization_id=org.id,
            conversation_id=conv1.id,
            sender_id=reza.id,
            text="با حسین هماهنگ کردم — فردا ساعت ۱۱ میاد بازدید.",
            channel=Channel.WEB,
        )
        await comm.post_message(
            organization_id=org.id,
            conversation_id=conv1.id,
            sender_id=sara.id,
            text="پیش‌نویس آگهی آماده است؛ بعد از تأیید علی منتشر می‌کنم.",
            channel=Channel.WEB,
        )

        conv2 = await comm.create_conversation(
            organization_id=org.id,
            channel=Channel.WEB,
            participant_ids=[ali.id, maryam.id] if maryam else [ali.id, reza.id],
            topic="درخواست شعبه مشهد",
            work_item_id=wi_old.id,
            vehicle_id=peugeot.id,
            actor_id=maryam.id if maryam else ali.id,
        )
        await comm.post_message(
            organization_id=org.id,
            conversation_id=conv2.id,
            sender_id=maryam.id if maryam else ali.id,
            text="مشهد این ۲۰۷ رو می‌خواد — امکان انتقال هست؟",
            channel=Channel.WEB,
        )

        # —— Knowledge ——
        from app.models.knowledge import DocumentCategory

        await kb.upload(
            organization_id=org.id,
            uploaded_by=ali.id,
            title="دستورالعمل پیگیری مشتری",
            category=DocumentCategory.COMMUNICATION_RULES,
            content=(
                "۱. هر علاقه مشتری باید ظرف ۲ ساعت پیگیری شود.\n"
                "۲. کار مشترک برای فروش خودرو بسازید و وظایف را به فروش و بازاریابی بسپارید.\n"
                "۳. بدون تأیید مدیر، قیمت را تغییر ندهید.\n"
                "۴. درخواست شعبه را در پیگیری ثبت کنید و مسئول تعیین کنید.\n"
            ),
            filename="sop-followup.txt",
            content_type="text/plain",
            actor_permissions=perms,
        )

        # —— Extra notifications for Home attention ——
        await notify(
            db,
            organization_id=org.id,
            user_id=ali.id,
            title="۳ مورد نیازمند توجه",
            body="یک وظیفه معوق و دو پیگیری باز دارید.",
            entity_type="work_item",
            entity_id=wi_old.id,
        )
        await notify(
            db,
            organization_id=org.id,
            user_id=reza.id,
            title="بازدید فردا — Camry #124",
            body="حسین ساعت ۱۱ می‌آید؛ آماده‌سازی خودرو را فراموش نکنید.",
            entity_type="task",
            entity_id=t_reza.id,
        )

        await db.commit()
        return {
            "status": "ok",
            "org": org.slug,
            "vehicles": 4,
            "customers": 3,
            "work_items": 4,
            "campaigns": 2,
            "login": {
                "slug": "autoco",
                "manager": "ali@autoco.example / password",
                "seller": "reza@autoco.example / password",
                "marketing": "sara@autoco.example / password",
                "mashhad": "maryam@autoco.example / password",
            },
        }


def main() -> None:
    result = asyncio.run(seed())
    print(result)


if __name__ == "__main__":
    main()
