"""مرحله ۶: نگهداری داده (آرشیو با archived_at) و خروج/پاک‌سازی مشتری."""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    CommunicationCase,
    Conversation,
    Customer,
    WorkItem,
)
from app.models.enums import CaseType, Channel, WorkItemStatus
from app.services import OrgService
from tests.conftest import auth, login, seeded  # noqa: F401


async def _org_admin(client: AsyncClient, seeded: dict, db: AsyncSession) -> str:
    """کاربر واقعی org.admin برای endpointهای مدیریتی."""
    svc = OrgService(db)
    await svc.create_user(
        organization_id=seeded["org"].id,
        email="boss@autoco.example",
        full_name="Boss Admin",
        password="password",
        role_id=seeded["admin_role"].id,
        branch_id=seeded["branch"].id,
    )
    await db.commit()
    return await login(client, "boss@autoco.example")


async def _audit_actions(db: AsyncSession) -> list[str]:
    await db.commit()
    rows = (await db.execute(select(AuditLog.action))).scalars().all()
    return sorted(set(rows))


async def test_archive_uses_archived_at_and_keeps_topic(
    client: AsyncClient, seeded: dict, db: AsyncSession
):
    """آرشیو باید archived_at را پر کند، نه اینکه topic را دستکاری کند."""
    token = await _org_admin(client, seeded, db)

    old = Conversation(
        organization_id=seeded["org"].id,
        channel=Channel.WEB,
        topic="Old topic",
        created_at=datetime.now(UTC) - timedelta(days=500),
    )
    fresh = Conversation(
        organization_id=seeded["org"].id,
        channel=Channel.WEB,
        topic="Fresh topic",
        created_at=datetime.now(UTC) - timedelta(days=2),
    )
    db.add_all([old, fresh])
    await db.commit()
    old_id, fresh_id = str(old.id), str(fresh.id)

    res = await client.post(
        "/admin/retention/archive?older_than_days=365", headers=auth(token)
    )
    assert res.status_code == 200, res.text
    assert res.json()["archived"] == 1

    await db.refresh(old)
    await db.refresh(fresh)
    assert old.archived_at is not None
    assert fresh.archived_at is None
    # topic دست‌نخورده می‌ماند (Consistency)
    assert old.topic == "Old topic"
    assert "[archived]" not in (old.topic or "")

    # لیست عادی گفتگوها آرشیوشده را نشان نمی‌دهد
    seller = await login(client, "reza@autoco.example")
    res = await client.get("/conversations", headers=auth(seller))
    assert res.status_code == 200
    ids = {row["id"] for row in res.json()}
    assert fresh_id in ids
    assert old_id not in ids

    # فقط با archived=true
    res = await client.get(
        "/conversations?archived=true", headers=auth(seller)
    )
    assert res.status_code == 200
    ids = {row["id"] for row in res.json()}
    assert old_id in ids
    assert fresh_id not in ids

    assert "retention.archive" in await _audit_actions(db)


async def test_customer_export_contains_cases_and_work_items(
    client: AsyncClient, seeded: dict, db: AsyncSession
):
    token = await login(client, "ali@autoco.example")
    res = await client.post(
        "/customers",
        json={"full_name": "Maryam Karimi", "phone": "+989121112233"},
        headers=auth(token),
    )
    assert res.status_code in (200, 201), res.text
    customer_id = res.json()["id"]

    case = CommunicationCase(
        organization_id=seeded["org"].id,
        case_number="C-EXP-1",
        type=CaseType.CUSTOMER_INTEREST,
        subject="Follow up on the inquiry",
        customer_id=uuid.UUID(customer_id),
        created_by=seeded["ali"].id,
    )
    work = WorkItem(
        organization_id=seeded["org"].id,
        title="Prepare an offer",
        owner_id=seeded["ali"].id,
        customer_id=uuid.UUID(customer_id),
        status=WorkItemStatus.OPEN,
    )
    db.add_all([case, work])
    await db.commit()

    res = await client.get(f"/customers/{customer_id}/export", headers=auth(token))
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["customer"]["full_name"] == "Maryam Karimi"
    assert [c["subject"] for c in payload["cases"]] == ["Follow up on the inquiry"]
    assert [w["title"] for w in payload["work_items"]] == ["Prepare an offer"]
    assert "customer.export" in await _audit_actions(db)

    # بینندهٔ محدود (بدون CUSTOMER_READ) اجازه خروجی ندارد
    viewer = await login(client, "viewer@autoco.example")
    res = await client.get(f"/customers/{customer_id}/export", headers=auth(viewer))
    assert res.status_code == 403


async def test_customer_erase_requires_org_admin_and_keeps_row(
    client: AsyncClient, seeded: dict, db: AsyncSession
):
    token = await login(client, "ali@autoco.example")
    res = await client.post(
        "/customers",
        json={"full_name": "Omid Sadri", "phone": "+989120001122", "notes": "VIP"},
        headers=auth(token),
    )
    assert res.status_code in (200, 201), res.text
    customer_id = res.json()["id"]

    # مدیر شعبه اجازهٔ پاک‌سازی ندارد
    res = await client.post(f"/customers/{customer_id}/erase", headers=auth(token))
    assert res.status_code == 403

    admin = await _org_admin(client, seeded, db)
    res = await client.post(f"/customers/{customer_id}/erase", headers=auth(admin))
    assert res.status_code == 200, res.text
    assert res.json()["erased"] is True

    # رکورد حذف نمی‌شود؛ فقط دادهٔ شخصی پاک می‌شود
    count = (
        await db.execute(
            select(func.count()).select_from(Customer).where(Customer.id == uuid.UUID(customer_id))
        )
    ).scalar_one()
    assert count == 1
    row = await db.get(Customer, uuid.UUID(customer_id))
    assert row is not None
    await db.refresh(row)
    assert row.full_name == "حذف‌شده"
    assert row.phone is None and row.email is None and row.notes is None
    assert "customer.erased" in await _audit_actions(db)
