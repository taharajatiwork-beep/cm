"""قیمت پست: مارکتینگ درخواست می‌دهد، مالی تأیید می‌کند، تغییر قیمت دوباره بررسی می‌خواهد."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.permissions import PermissionCode
from app.models.pricing import PostSlot
from app.services import OrgService
from app.services.inventory import InventoryService
from app.services.pricing import PricingService
from app.services.vehicle_paste import parse_stock_message
from tests.conftest import auth, login

SAMPLE = """
گروه خودرویی ستوده، 11 مهر
مکث موتور:
لوکانو
سبز 7800
آئودی:
Q4 سفید و مشکی 2024 کارکرد 12000 موجود در شعبه مرزداران قیمت 15700
اف ایکس سفید 403 کارکرد 5000 موجود در شعبه کاشانی 6700
تیگو ۷ پرو سفید موجود در شعبه مرزداران تحویل یک ماه کاری قیمت 18500
A5 مشکی موجود در شعبه کاشانی قیمت 14200
آریزو M5 سفید قیمت 9800
ID4 خاکستری 2025 موجود در شعبه ایرانمال قیمت 21000
بیجینگ X7 مشکی قیمت 12500
شرایط لیزینگ جداگانه اعلام می‌شود
خودروهایی که در لیست نیستند فروخته شده‌اند
"""


def test_parser_reads_sample_stock_message():
    rows = parse_stock_message(SAMPLE)
    models = " ".join(row["model"] for row in rows)
    for token in ("Q4", "اف ایکس", "تیگو", "A5", "آریزو", "ID4", "بیجینگ", "لوکانو"):
        assert token in models, models
    q4 = next(row for row in rows if "Q4" in row["model"])
    assert q4["price_million"] == 15700
    assert q4["color"] == "سفید و مشکی"
    assert q4["branch_name"] == "مرزداران"
    fx = next(row for row in rows if "اف ایکس" in row["model"])
    assert fx["year"] == 1403
    assert fx["price_million"] == 6700
    id4 = next(row for row in rows if "ID4" in row["model"])
    assert id4["year"] == 2025
    lucano = next(row for row in rows if "لوکانو" in row["model"])
    assert lucano["price_million"] == 7800
    assert lucano["color"] == "سبز"


@pytest.mark.asyncio
async def test_marketing_cannot_confirm_and_price_change_rechecks(client, seeded, db):
    ali = await login(client, "ali@autoco.example")
    created = await client.post(
        "/inventory/vehicles",
        headers=auth(ali),
        json={"vin": "PRICEVIN001", "brand": "Audi", "model": "Q4", "year": 2024, "sale_price": 15_700_000_000},
    )
    assert created.status_code == 200, created.text
    vehicle_id = created.json()["id"]

    sara = await login(client, "sara@autoco.example")
    slot = await client.post(
        "/pricing/slots",
        headers=auth(sara),
        json={"vehicle_id": vehicle_id, "post_at": (datetime.now(UTC) + timedelta(hours=5)).isoformat(), "slot_type": "video"},
    )
    assert slot.status_code == 200, slot.text
    slot_id = slot.json()["id"]
    denied = await client.post(f"/pricing/slots/{slot_id}/confirm", headers=auth(sara), json={})
    assert denied.status_code == 403

    svc = OrgService(db)
    role = await svc.create_role(
        seeded["org"].id,
        "Finance",
        "finance",
        [PermissionCode.PRICE_APPROVE, PermissionCode.INVENTORY_READ, PermissionCode.NOTIFICATION_READ],
        "organization",
    )
    await svc.create_user(
        organization_id=seeded["org"].id,
        email="finance@autoco.example",
        full_name="Neda",
        password="password",
        role_id=role.id,
        branch_id=seeded["branch"].id,
    )
    await db.commit()
    finance = await login(client, "finance@autoco.example")
    confirmed = await client.post(f"/pricing/slots/{slot_id}/confirm", headers=auth(finance), json={})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"

    changed = await client.post(
        f"/pricing/slots/{slot_id}/confirm",
        headers=auth(finance),
        json={"amount": 16_000_000_000},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["sale_price"] == 16_000_000_000
    stored = await client.get(f"/inventory/vehicles/{vehicle_id}", headers=auth(finance))
    assert stored.status_code == 200, stored.text
    assert stored.json()["sale_price"] == 16_000_000_000
    changed = await client.post(
        f"/inventory/vehicles/{vehicle_id}/price",
        headers=auth(finance),
        json={"amount": 17_000_000_000, "note": "new"},
    )
    assert changed.status_code == 200, changed.text
    board = await client.get("/pricing/board", headers=auth(sara))
    assert board.status_code == 200, board.text
    row = next(item for item in board.json()["slots"] if item["id"] == slot_id)
    assert row["status"] == "needs_recheck"


@pytest.mark.asyncio
async def test_price_reminder_fires_once(db, seeded):
    inv = InventoryService(db)
    vehicle = await inv.create_vehicle(
        organization_id=seeded["org"].id,
        vin="REMINDVIN01",
        brand="Audi",
        model="A5",
        year=1403,
        actor_id=seeded["ali"].id,
        actor_permissions={PermissionCode.INVENTORY_WRITE},
    )
    soon = datetime.now(UTC) + timedelta(minutes=30)
    db.add(
        PostSlot(
            organization_id=seeded["org"].id,
            vehicle_id=vehicle.id,
            post_at=soon,
            requester_id=seeded["sara"].id,
            status="requested",
        )
    )
    await db.flush()
    svc = PricingService(db)
    first = await svc.remind_due(now=datetime.now(UTC))
    assert first >= 1
    second = await svc.remind_due(now=datetime.now(UTC))
    assert second == 0


@pytest.mark.asyncio
async def test_request_price_for_several_vehicles(client, seeded):
    ali = await login(client, "ali@autoco.example")
    ids = []
    for vin, model in (("MULTI-A", "One"), ("MULTI-B", "Two")):
        created = await client.post(
            "/inventory/vehicles",
            headers=auth(ali),
            json={"vin": vin, "brand": "Test", "model": model, "year": 2024},
        )
        assert created.status_code == 200, created.text
        ids.append(created.json()["id"])

    sara = await login(client, "sara@autoco.example")
    when = (datetime.now(UTC) + timedelta(hours=4)).isoformat()
    slots = await client.post(
        "/pricing/slots",
        headers=auth(sara),
        json={"vehicle_ids": ids, "post_at": when, "slot_type": "video"},
    )
    assert slots.status_code == 200, slots.text
    body = slots.json()
    assert len(body) == 2
    assert {row["vehicle_id"] for row in body} == set(ids)
    assert {row["status"] for row in body} == {"requested"}
