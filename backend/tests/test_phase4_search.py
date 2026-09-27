import pytest
from httpx import AsyncClient

from tests.conftest import auth, login


@pytest.mark.asyncio
async def test_exact_vin_and_stock_search(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    vin = "JTDBR32E720012424"
    created = await client.post(
        "/inventory/vehicles",
        headers=auth(token),
        json={
            "vin": vin,
            "brand": "Toyota",
            "model": "Camry",
            "year": 2020,
            "stock_number": "124",
            "branch_id": str(seeded["branch"].id),
        },
    )
    assert created.status_code == 200, created.text
    vid = created.json()["id"]

    by_vin = await client.get(f"/search?vin={vin}&types=vehicle", headers=auth(token))
    assert by_vin.status_code == 200
    assert by_vin.json()["total"] >= 1
    assert by_vin.json()["hits"][0]["entity_id"] == vid
    assert by_vin.json()["hits"][0]["match_kind"] == "exact"

    by_stock = await client.get(
        "/search?stock_number=124&types=vehicle", headers=auth(token)
    )
    assert any(h["entity_id"] == vid for h in by_stock.json()["hits"])


@pytest.mark.asyncio
async def test_text_search_vehicle_and_work_item(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    vehicle = await client.post(
        "/inventory/vehicles",
        headers=auth(token),
        json={
            "vin": "JTDBR32E720099777",
            "brand": "Toyota",
            "model": "Camry",
            "year": 2018,
            "stock_number": "777",
            "branch_id": str(seeded["branch"].id),
        },
    )
    assert vehicle.status_code == 200
    wi = await client.post(
        "/work-items",
        headers=auth(token),
        json={"title": "Sell Camry #777", "vehicle_id": vehicle.json()["id"]},
    )
    assert wi.status_code == 200

    r = await client.get("/search?q=Camry", headers=auth(token))
    assert r.status_code == 200
    types = {h["entity_type"] for h in r.json()["hits"]}
    assert "vehicle" in types
    assert "work_item" in types


@pytest.mark.asyncio
async def test_case_number_and_employee_search(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    case = await client.post(
        "/cases",
        headers=auth(token),
        json={
            "subject": "Branch availability check",
            "type": "BRANCH_REQUEST",
            "owner_id": str(seeded["reza"].id),
        },
    )
    assert case.status_code == 200
    case_number = case.json()["case_number"]

    by_case = await client.get(
        f"/search?case_number={case_number}&types=case",
        headers=auth(token),
    )
    assert by_case.status_code == 200
    assert by_case.json()["hits"][0]["title"] == case_number
    assert by_case.json()["hits"][0]["match_kind"] == "exact"

    by_q = await client.get(f"/search?q={case_number}&types=case", headers=auth(token))
    assert any(h["title"] == case_number for h in by_q.json()["hits"])

    emp = await client.get(
        "/search?employee=Reza&types=user",
        headers=auth(token),
    )
    assert emp.status_code == 200
    assert any(h["title"] == "Reza Seller" for h in emp.json()["hits"])


@pytest.mark.asyncio
async def test_branch_and_status_filters(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    await client.post(
        "/inventory/vehicles",
        headers=auth(token),
        json={
            "vin": "JTDBR32E720088001",
            "brand": "Kia",
            "model": "Sportage",
            "year": 2019,
            "stock_number": "801",
            "branch_id": str(seeded["branch"].id),
            "status": "IN_STOCK",
        },
    )
    r = await client.get(
        f"/search?types=vehicle&branch_id={seeded['branch'].id}&status=IN_STOCK",
        headers=auth(token),
    )
    assert r.status_code == 200
    assert r.json()["total"] >= 1
    assert all(h["metadata"]["status"] == "IN_STOCK" for h in r.json()["hits"])


@pytest.mark.asyncio
async def test_search_permission_denied(client: AsyncClient, seeded):
    token = await login(client, "viewer@autoco.example")
    r = await client.get("/search?q=Camry", headers=auth(token))
    assert r.status_code == 403
