"""Vehicle detail fields + CSV/Excel import."""

import io

import pytest
from httpx import AsyncClient
from openpyxl import Workbook

from tests.conftest import auth, login


@pytest.mark.asyncio
async def test_create_vehicle_with_details(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    r = await client.post(
        "/inventory/vehicles",
        headers=auth(token),
        json={
            "vin": "JTDBDETAIL0000001",
            "brand": "Toyota",
            "model": "Corolla",
            "year": 2021,
            "stock_number": "DET1",
            "color": "Blue",
            "trim": "XLE",
            "mileage": 12000,
            "body_type": "sedan",
            "transmission": "automatic",
            "fuel_type": "petrol",
            "engine": "1.8L",
            "plate_number": "11الف111-11",
            "doors": 4,
            "seats": 5,
            "options": "camera, sensors",
            "description": "Low mileage family sedan ready for listing",
            "notes": "Spare key in safe",
            "exterior_condition": "excellent",
            "interior_condition": "good",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["description"].startswith("Low mileage")
    assert body["transmission"] == "automatic"
    assert body["plate_number"] == "11الف111-11"

    found = await client.get(
        "/inventory/vehicles?q=listing",
        headers=auth(token),
    )
    assert found.status_code == 200
    assert any(v["id"] == body["id"] for v in found.json())


@pytest.mark.asyncio
async def test_import_vehicles_csv(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    csv_body = (
        "vin,brand,model,year,stock_number,color,description,گیربکس\n"
        "JTDBIMPORTCSV0001,Kia,Sportage,2020,IMP1,White,CSV import demo,اتومات\n"
        "JTDBIMPORTCSV0002,Kia,Cerato,2019,IMP2,Black,Second row,manual\n"
    ).encode("utf-8-sig")
    r = await client.post(
        "/inventory/vehicles/import",
        headers=auth(token),
        files={"file": ("fleet.csv", csv_body, "text/csv")},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["created"] == 2
    assert data["vehicles"][0]["import_source"].startswith("csv:")
    sportage = next(v for v in data["vehicles"] if v["stock_number"] == "IMP1")
    assert sportage["transmission"] == "اتومات"
    assert sportage["description"] == "CSV import demo"

    # Duplicate VIN skipped
    again = await client.post(
        "/inventory/vehicles/import",
        headers=auth(token),
        files={"file": ("fleet.csv", csv_body, "text/csv")},
    )
    assert again.status_code == 200
    assert again.json()["created"] == 0
    assert again.json()["skipped"] == 2


@pytest.mark.asyncio
async def test_import_vehicles_xlsx_and_template(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    tpl = await client.get(
        "/inventory/vehicles/import-template?format=xlsx",
        headers=auth(token),
    )
    assert tpl.status_code == 200
    assert "spreadsheet" in tpl.headers.get("content-type", "")

    wb = Workbook()
    ws = wb.active
    ws.append(["شاسی", "برند", "مدل", "سال", "توضیحات", "آپشن"])
    ws.append(["JTDBIMPORTXLSX01", "Hyundai", "i20", 2022, "Excel import", "A/C"])
    buf = io.BytesIO()
    wb.save(buf)
    r = await client.post(
        "/inventory/vehicles/import",
        headers=auth(token),
        files={
            "file": (
                "cars.xlsx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1
    v = r.json()["vehicles"][0]
    assert v["description"] == "Excel import"
    assert v["options"] == "A/C"
