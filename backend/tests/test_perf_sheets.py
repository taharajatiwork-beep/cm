"""Performance-marketing Google Sheets sync."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import parse_qs
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

from app.core.config import get_settings
from app.models.campaign import Campaign
from app.models.customer import Customer
from app.models.enums import CampaignStatus
from app.models.inventory import Vehicle, VehiclePrice
from app.models.pricing import PostSlot
from app.perf.services.sheets import (
    Bundle,
    GoogleSheetsClient,
    SheetsError,
    cost_rows,
    ensure_ready,
    load_bundle,
    sms_rows,
    specs_for,
)


def _rsa_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def _bundle() -> Bundle:
    customer_id = uuid4()
    vehicle_id = uuid4()
    when = datetime(2026, 10, 5, tzinfo=UTC)
    customer = SimpleNamespace(
        id=customer_id,
        full_name="Mina",
        phone="09120000000",
        email="mina@example.com",
        stage="lead",
        notes="callback",
        updated_at=when,
    )
    no_phone = SimpleNamespace(
        id=uuid4(),
        full_name="No Phone",
        phone="  ",
        email=None,
        stage="lead",
        notes=None,
        updated_at=when,
    )
    vehicle = SimpleNamespace(
        id=vehicle_id,
        brand="Toyota",
        model="Camry",
        year=2020,
        stock_number="12",
        purchase_price=100,
        sale_price=200,
        currency="IRR",
        status="IN_STOCK",
        price_updated_at=when,
        updated_at=when,
    )
    slot = SimpleNamespace(
        id=uuid4(),
        vehicle_id=vehicle_id,
        channel="instagram",
        slot_type="video",
        status="confirmed",
        post_at=when,
        confirmed_price=50,
        confirmed_at=when,
        created_at=when,
    )
    price = SimpleNamespace(
        id=uuid4(),
        vehicle_id=vehicle_id,
        amount=180,
        note="old",
        created_at=when,
    )
    campaign = SimpleNamespace(
        id=uuid4(),
        title="Spring",
        status=CampaignStatus.ACTIVE,
        channel=None,
        description="push",
        updated_at=when,
    )
    return Bundle(
        customers=[customer, no_phone],
        campaigns=[campaign],
        vehicles=[vehicle],
        slots=[slot],
        prices=[price],
        kpis={"open_tasks": 1, "as_of_jalali": "1405/07/13"},
    )


def test_row_mapping_uses_existing_domain_records():
    bundle = _bundle()
    sms = sms_rows(bundle)
    assert sms[0][0] == "name"
    assert len(sms) == 2
    assert sms[1][0] == "Mina"
    costs = cost_rows(bundle)
    kinds = [row[0] for row in costs[1:]]
    assert kinds == ["purchase", "sale", "sale_history", "post"]
    specs = specs_for("performance", bundle)
    assert [spec.title for spec in specs] == ["SMS", "Social", "Leads", "Costs", "Report"]
    campaign_spec = specs_for("register_campaign", bundle)[0]
    assert campaign_spec.rows[1][0] == "Spring"
    assert campaign_spec.preferences[-1] == "CM Campaigns"


def test_ensure_ready_names_missing_env(monkeypatch, tmp_path):
    key = tmp_path / "sa.json"
    key.write_text('{"client_email":"sa@example.com","private_key":"x"}', encoding="utf-8")
    monkeypatch.setenv("PERF_SHEETS_CREDENTIALS_FILE", "")
    monkeypatch.setenv("PERF_SHEETS_SPREADSHEET_ID", "")
    monkeypatch.setenv("PERF_SHEETS_COST_TRACKING_ID", "")
    monkeypatch.setenv("PERF_SHEETS_REGISTER_CAMPAIGN_ID", "")
    monkeypatch.setenv("PERF_SHEETS_REPORTER_ID", "")
    get_settings.cache_clear()
    with pytest.raises(SheetsError) as empty_file:
        ensure_ready(get_settings())
    assert "PERF_SHEETS_CREDENTIALS_FILE" in str(empty_file.value)

    monkeypatch.setenv("PERF_SHEETS_CREDENTIALS_FILE", str(key))
    get_settings.cache_clear()
    with pytest.raises(SheetsError) as no_ids:
        ensure_ready(get_settings())
    text = str(no_ids.value)
    assert "PERF_SHEETS_SPREADSHEET_ID" in text
    assert "PERF_SHEETS_COST_TRACKING_ID" in text
    assert "PERF_SHEETS_REGISTER_CAMPAIGN_ID" in text
    assert "PERF_SHEETS_REPORTER_ID" in text

    monkeypatch.setenv("PERF_SHEETS_SPREADSHEET_ID", "sheet-main")
    get_settings.cache_clear()
    configured, skipped = ensure_ready(get_settings())
    assert configured == [("performance", "sheet-main", "PERF_SHEETS_SPREADSHEET_ID")]
    assert {item["env"] for item in skipped} == {
        "PERF_SHEETS_COST_TRACKING_ID",
        "PERF_SHEETS_REGISTER_CAMPAIGN_ID",
        "PERF_SHEETS_REPORTER_ID",
    }


def test_missing_credentials_file_is_actionable(monkeypatch):
    monkeypatch.setenv("PERF_SHEETS_CREDENTIALS_FILE", r"C:\missing\perf-sheets.json")
    monkeypatch.setenv("PERF_SHEETS_SPREADSHEET_ID", "sheet-main")
    get_settings.cache_clear()
    with pytest.raises(SheetsError) as exc:
        ensure_ready(get_settings())
    assert "not a file this process can read" in str(exc.value)
    assert "perf-sheets.json" in str(exc.value)


class _FakeTransport:
    def __init__(self, tabs: list[str] | None = None):
        self.tabs = list(tabs or [])
        self.calls: list[tuple[str, str, bytes | None]] = []
        self.values: dict[str, list] = {}

    def __call__(self, method: str, url: str, headers: dict, body: bytes | None):
        self.calls.append((method, url, body))
        payload = json.loads(body) if body else None
        if method == "GET":
            sheets = [{"properties": {"title": title}} for title in self.tabs]
            return 200, json.dumps({"sheets": sheets}).encode()
        if ":batchUpdate" in url:
            title = payload["requests"][0]["addSheet"]["properties"]["title"]
            self.tabs.append(title)
            return 200, b"{}"
        if "batchClear" in url:
            return 200, b"{}"
        if method == "PUT":
            self.values[payload["range"]] = payload["values"]
            return 200, b"{}"
        return 500, b'{"error":{"message":"unexpected"}}'


def test_refresh_sheet_writes_sotoudeh_tabs_and_source_fallback():
    bundle = _bundle()
    transport = _FakeTransport(tabs=["Sheet1"])
    client = GoogleSheetsClient(token="tok", transport=transport)
    written = client.refresh_sheet("sheet-main", specs_for("performance", bundle))
    assert written["tabs"] == ["SMS", "Social", "Leads", "Costs", "Report"]
    assert set(written["created_tabs"]) == set(written["tabs"])
    sms_values = transport.values["'SMS'!A1"]
    assert sms_values[1][0] == "Mina"
    assert written["rows"]["SMS"] == 1

    source = _FakeTransport(tabs=["هزینه", "Other"])
    client = GoogleSheetsClient(token="tok", transport=source)
    cost = client.refresh_sheet("cost-book", specs_for("cost_tracking", bundle))
    assert cost["tabs"] == ["هزینه"]
    assert cost["created_tabs"] == []
    assert source.values["'هزینه'!A1"][1][0] == "purchase"
    assert not any("Other" in (call[1]) for call in source.calls if call[0] == "PUT")

    created = _FakeTransport(tabs=["Cover"])
    client = GoogleSheetsClient(token="tok", transport=created)
    report = client.refresh_sheet("reporter-book", specs_for("reporter", bundle))
    assert report["tabs"] == ["CM Report"]
    assert report["created_tabs"] == ["CM Report"]
    assert created.values["'CM Report'!A1"][0] == ["metric", "value"]


def test_google_permission_error_names_the_service_account():
    def deny(method, url, headers, body):
        return 403, b'{"error":{"message":"The caller does not have permission"}}'

    client = GoogleSheetsClient(
        token="tok",
        transport=deny,
        info={"client_email": "sync@project.iam.gserviceaccount.com"},
    )
    with pytest.raises(SheetsError) as exc:
        client.write_google("sheet-main", "SMS", [["name"], ["Mina"]])
    text = str(exc.value)
    assert "sync@project.iam.gserviceaccount.com" in text
    assert "Editor" in text
    assert exc.value.status == 502


def test_jwt_uses_service_account_email():
    pem = _rsa_pem()
    seen: dict[str, str] = {}

    def transport(method, url, headers, body):
        seen["body"] = body.decode()
        return 200, b'{"access_token":"ya29.test"}'

    client = GoogleSheetsClient(
        transport=transport,
        info={
            "client_email": "sync@project.iam.gserviceaccount.com",
            "private_key": pem,
            "token_uri": "https://oauth2.googleapis.com/token",
        },
    )
    assert client._token() == "ya29.test"
    assertion = parse_qs(seen["body"])["assertion"][0]
    claims = jwt.get_unverified_claims(assertion)
    assert claims["iss"] == "sync@project.iam.gserviceaccount.com"
    assert claims["scope"] == "https://www.googleapis.com/auth/spreadsheets"


@pytest.mark.asyncio
async def test_load_bundle_reads_org_rows(db, seeded):
    org_id = seeded["org"].id
    vehicle = Vehicle(
        organization_id=org_id,
        brand="Peugeot",
        model="206",
        year=1398,
        purchase_price=10,
        sale_price=20,
    )
    db.add(vehicle)
    await db.flush()
    db.add(
        Customer(
            organization_id=org_id,
            full_name="Lead One",
            phone="09121111111",
            stage="lead",
        )
    )
    db.add(
        Campaign(
            organization_id=org_id,
            title="Nowruz",
            status=CampaignStatus.ACTIVE,
        )
    )
    db.add(
        PostSlot(
            organization_id=org_id,
            vehicle_id=vehicle.id,
            post_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
            requester_id=seeded["sara"].id,
            confirmed_price=5,
            status="confirmed",
        )
    )
    db.add(
        VehiclePrice(
            organization_id=org_id,
            vehicle_id=vehicle.id,
            amount=15,
            actor_id=seeded["sara"].id,
        )
    )
    await db.commit()
    bundle = await load_bundle(db, org_id)
    assert any(row.full_name == "Lead One" for row in bundle.customers)
    assert any(row.title == "Nowruz" for row in bundle.campaigns)
    assert bundle.kpis["vehicles"] >= 1
    social = specs_for("performance", bundle)[1]
    assert any(row[0].startswith("Peugeot") for row in social.rows[1:])


@pytest.mark.asyncio
async def test_sync_endpoint_missing_config_and_permission(client, seeded, monkeypatch):
    monkeypatch.setenv("PERF_SHEETS_CREDENTIALS_FILE", "")
    monkeypatch.setenv("PERF_SHEETS_SPREADSHEET_ID", "")
    monkeypatch.setenv("PERF_SHEETS_COST_TRACKING_ID", "")
    monkeypatch.setenv("PERF_SHEETS_REGISTER_CAMPAIGN_ID", "")
    monkeypatch.setenv("PERF_SHEETS_REPORTER_ID", "")
    get_settings.cache_clear()

    sara = await client.post(
        "/auth/login",
        json={"organization_slug": "autoco", "email": "sara@autoco.example", "password": "password"},
    )
    assert sara.status_code == 200
    headers = {"Authorization": f"Bearer {sara.json()['access_token']}"}
    missing = await client.post("/perf/sheets/sync", headers=headers)
    assert missing.status_code == 503
    assert "PERF_SHEETS_CREDENTIALS_FILE" in missing.json()["detail"]

    viewer = await client.post(
        "/auth/login",
        json={"organization_slug": "autoco", "email": "viewer@autoco.example", "password": "password"},
    )
    denied = await client.post(
        "/perf/sheets/sync",
        headers={"Authorization": f"Bearer {viewer.json()['access_token']}"},
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_sync_endpoint_returns_writer_result(client, seeded, monkeypatch):
    async def fake_sync(db, organization_id):
        return {
            "ok": True,
            "targets": [
                {
                    "key": "performance",
                    "env": "PERF_SHEETS_SPREADSHEET_ID",
                    "spreadsheet_id": "sheet-main",
                    "updated": True,
                    "tabs": ["SMS"],
                    "created_tabs": [],
                    "rows": {"SMS": 1},
                    "error": "",
                }
            ],
            "skipped": [],
        }

    monkeypatch.setattr("app.api.routes.perf_sheets.sync_performance_sheets", fake_sync)
    sara = await client.post(
        "/auth/login",
        json={"organization_slug": "autoco", "email": "sara@autoco.example", "password": "password"},
    )
    response = await client.post(
        "/perf/sheets/sync",
        headers={"Authorization": f"Bearer {sara.json()['access_token']}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["targets"][0]["tabs"] == ["SMS"]
