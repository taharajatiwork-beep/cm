import pytest
from httpx import AsyncClient

from app.models.enums import VehicleStatus
from tests.conftest import auth, login


@pytest.mark.asyncio
async def test_create_search_vehicle(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    r = await client.post(
        "/inventory/vehicles",
        headers=auth(token),
        json={
            "vin": "JTDBR32E720099001",
            "brand": "Toyota",
            "model": "Camry",
            "year": 2019,
            "stock_number": "901",
            "branch_id": str(seeded["branch"].id),
            "mileage": 45000,
            "sale_price": 2_100_000_000,
        },
    )
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    assert r.json()["status"] == VehicleStatus.IN_STOCK.value

    found = await client.get(
        "/inventory/vehicles?q=Camry",
        headers=auth(token),
    )
    assert found.status_code == 200
    assert any(v["id"] == vid for v in found.json())

    by_stock = await client.get(
        "/inventory/vehicles?stock_number=901",
        headers=auth(token),
    )
    assert len(by_stock.json()) == 1


@pytest.mark.asyncio
async def test_vehicle_status_history_and_timeline(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    created = await client.post(
        "/inventory/vehicles",
        headers=auth(token),
        json={
            "vin": "JTDBR32E720099002",
            "brand": "Hyundai",
            "model": "Elantra",
            "year": 2021,
            "stock_number": "902",
            "branch_id": str(seeded["branch"].id),
        },
    )
    vid = created.json()["id"]

    status = await client.post(
        f"/inventory/vehicles/{vid}/status",
        headers=auth(token),
        json={"to_status": VehicleStatus.RESERVED.value, "note": "Customer hold"},
    )
    assert status.status_code == 200
    assert status.json()["status"] == VehicleStatus.RESERVED.value

    history = await client.get(f"/inventory/vehicles/{vid}/history", headers=auth(token))
    assert len(history.json()) >= 2
    assert history.json()[-1]["to_status"] == VehicleStatus.RESERVED.value

    timeline = await client.get(f"/timeline/vehicle/{vid}", headers=auth(token))
    types = {e["event_type"] for e in timeline.json()}
    assert "vehicle.created" in types
    assert "vehicle.status_changed" in types


@pytest.mark.asyncio
async def test_work_item_linked_to_vehicle_context(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    vehicle = await client.post(
        "/inventory/vehicles",
        headers=auth(token),
        json={
            "vin": "JTDBR32E720012424",
            "brand": "Toyota",
            "model": "Camry",
            "year": 2020,
            "stock_number": "124",
            "branch_id": str(seeded["branch"].id),
        },
    )
    assert vehicle.status_code == 200, vehicle.text
    vid = vehicle.json()["id"]

    wi = await client.post(
        "/work-items",
        headers=auth(token),
        json={
            "title": "Sell Camry #124",
            "vehicle_id": vid,
            "participant_ids": [str(seeded["reza"].id), str(seeded["sara"].id)],
        },
    )
    assert wi.status_code == 200, wi.text

    case = await client.post(
        "/cases",
        headers=auth(token),
        json={
            "subject": "Buyer interest in Camry #124",
            "type": "CUSTOMER_INTEREST",
            "work_item_id": wi.json()["id"],
            "vehicle_id": vid,
            "owner_id": str(seeded["reza"].id),
        },
    )
    assert case.status_code == 200, case.text

    req = await client.post(
        "/inventory/requests",
        headers=auth(token),
        json={
            "subject": "Mashhad asked about Camry #124",
            "requesting_branch_id": str(seeded["branch"].id),
            "vehicle_id": vid,
            "request_type": "INTEREST",
            "work_item_id": wi.json()["id"],
            "case_id": case.json()["id"],
        },
    )
    assert req.status_code == 200, req.text

    ctx = await client.get(f"/inventory/vehicles/{vid}/context", headers=auth(token))
    assert ctx.status_code == 200
    body = ctx.json()
    assert body["vehicle"]["stock_number"] == "124"
    assert len(body["work_items"]) == 1
    assert len(body["cases"]) == 1
    assert len(body["inventory_requests"]) == 1
    assert len(body["history"]) >= 1


@pytest.mark.asyncio
async def test_inventory_permission_denial(client: AsyncClient, seeded):
    token = await login(client, "viewer@autoco.example")
    r = await client.post(
        "/inventory/vehicles",
        headers=auth(token),
        json={
            "vin": "JTDBR32E720099099",
            "brand": "Kia",
            "model": "Sportage",
            "year": 2018,
        },
    )
    assert r.status_code == 403
