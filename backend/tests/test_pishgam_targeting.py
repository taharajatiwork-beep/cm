"""هدف‌گیری پیشگام: قفل مسیر تغییردهنده، و همگام‌سازی فقط‌خواندنی با پاسخ ساختگی."""

import asyncio
import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.permissions import PermissionCode
from app.perf.models import PmPishgamAudit
from app.perf.services.common import PerfError
from app.perf.services.pishgam_targeting import classify, execute, load_areas
from app.services import OrgService
from tests.conftest import auth, login


def test_poll_accepts_status_seven_as_done():
    from app.perf.services.pishgam_targeting import _SMART_DONE

    assert 7 in _SMART_DONE


def test_rows_reads_private_numbers_list():
    from app.perf.services.pishgam_targeting import _rows

    assert _rows({"statusCode": 0, "privateNumbers": []}) == []
    rows = _rows({"statusCode": 0, "privateNumbers": [{"operator": 2, "number": "30001234"}]})
    assert rows[0]["number"] == "30001234"


def test_catalog_locks_send_and_keeps_polygon_check_readable():
    assert classify("POST", "/Messages/Send")[0] == "mutating"
    assert classify("POST", "/SmartSms/CreateSimpleSmartSmsRequest")[0] == "build"
    assert classify("POST", "/SmartSms/RefreshSmartSmsRequest")[0] == "build"
    assert classify("POST", "/SmartSms/SendSimpleSmartSms")[0] == "mutating"
    assert classify("POST", "/SmartSms/CheckPolygonCells")[0] == "read"
    assert classify("GET", "/SmartSms/GetProvinces")[0] == "read"
    assert classify("POST", "/SmartSms/CheckNumbersClass")[0] == "gated"
    assert classify("POST", "/ZonePostalCodes/GetZonePostalCodesForSend")[0] == "unknown"


def test_areas_are_closed_and_unverified():
    areas = load_areas()
    assert len(areas) == 14
    zaferanieh = next(row for row in areas if row["key"] == "zaferanieh")
    assert zaferanieh["name_fa"] == "زعفرانیه"
    assert zaferanieh["tier"] == "A"
    assert zaferanieh["verified"] is False
    assert zaferanieh["closed"] is True
    assert all(row["closed"] for row in areas)


async def test_execute_refuses_send_without_calling_network(db, seeded):
    called = False

    async def fetch(*_args, **_kwargs):
        nonlocal called
        called = True
        return 200, "{}"

    with pytest.raises(PerfError) as caught:
        await execute(
            db,
            organization_id=seeded["org"].id,
            actor_id=seeded["ali"].id,
            method="POST",
            path="/Messages/Send",
            token="super-secret-token-value",
            api_base="https://smsapi.pishgamrayan.com",
            payload={"senderNumber": "5000", "messageBodies": ["سلام لغو11"], "token": "super-secret-token-value"},
            fetch=fetch,
        )
    assert caught.value.status == 403
    assert called is False
    row = await db.scalar(select(PmPishgamAudit))
    assert row is not None
    assert row.endpoint == "/Messages/Send"
    assert row.status_code == -1
    assert row.is_mutating is True
    stored = f"{row.method} {row.endpoint} {row.request_hash}"
    assert "super-secret-token-value" not in stored


async def _nadia(db, seeded):
    svc = OrgService(db)
    role = await svc.create_role(
        seeded["org"].id,
        "Perf",
        "perf-targeting",
        [PermissionCode.PERF_READ, PermissionCode.PERF_WRITE],
        "organization",
    )
    user = await svc.create_user(
        organization_id=seeded["org"].id,
        email="nadia-target@autoco.example",
        full_name="نادیا هدف",
        password="password",
        role_id=role.id,
        branch_id=seeded["branch"].id,
    )
    await db.commit()
    return user


async def test_sync_reads_reference_and_skips_send(client, seeded, db, monkeypatch):
    await _nadia(db, seeded)
    seen: list[str] = []

    async def fetch(method, url, token, params, payload):
        seen.append(f"{method} {url}")
        assert token == "plain-token"
        assert payload is None
        if url.endswith("/GetProvinces"):
            body = {"statusCode": 0, "data": [{"id": 8, "name": "تهران"}]}
        elif url.endswith("/GetCities"):
            assert params == {"ProvinceId": 8}
            body = {"statusCode": 0, "data": [{"id": 950, "name": "تهران"}]}
        elif url.endswith("/GetDeviceBrands"):
            body = [{"id": 1, "name": "Apple"}]
        elif url.endswith("/GetDeviceTypes"):
            body = {"statusCode": 0, "data": [{"id": 3, "name": "Mobile"}]}
        else:
            raise AssertionError(url)
        return 200, json.dumps(body)

    monkeypatch.setattr("app.perf.services.pishgam_targeting.fetch_http", fetch)
    monkeypatch.setattr("app.perf.services.pishgam_targeting.get_settings", lambda: type("S", (), {
        "pishgam_sms_api_url": "https://smsapi.pishgamrayan.com",
        "pishgam_sms_token": "plain-token",
    })())

    token = await login(client, "nadia-target@autoco.example")
    view = await client.get("/perf/pishgam/targeting", headers=auth(token))
    assert view.status_code == 200, view.text
    assert len(view.json()["areas"]) == 14
    assert view.json()["refs"]["provinces"] == 0
    assert view.json()["catalog"]["mutating"] > 0
    assert view.json()["smart"]["preview_enabled"] is True
    assert view.json()["smart"]["send_enabled"] is False

    synced = await client.post("/perf/pishgam/targeting/sync", headers=auth(token))
    assert synced.status_code == 200, synced.text
    assert synced.json() == {"provinces": 1, "cities": 1, "brands": 1, "types": 1}
    assert all("/Messages/Send" not in item for item in seen)
    assert any(item.endswith("/GetProvinces") for item in seen)

    again = await client.get("/perf/pishgam/targeting", headers=auth(token))
    assert again.json()["refs"] == {"provinces": 1, "cities": 1, "brands": 1, "types": 1}
    assert any(row["endpoint"] == "/SmartSms/GetProvinces" and row["status_code"] == 200 for row in again.json()["audit"])


def _fake_settings():
    return type("S", (), {
        "pishgam_sms_api_url": "https://smsapi.pishgamrayan.com",
        "pishgam_sms_token": "plain-token",
    })()


async def test_polygon_check_reads_only_the_selected_ring(client, seeded, db, monkeypatch):
    await _nadia(db, seeded)
    seen: list[tuple[str, object]] = []

    async def fetch(method, url, token, params, payload):
        seen.append((f"{method} {url}", payload))
        return 200, json.dumps({
            "statusCode": 0,
            "data": [
                {"mobileOperator": 1, "isValid": True, "isValidArea": True},
                {"mobileOperator": 2, "isValid": True, "isValidArea": False},
            ],
        })

    monkeypatch.setattr("app.perf.services.pishgam_targeting.fetch_http", fetch)
    monkeypatch.setattr("app.perf.services.pishgam_targeting.get_settings", _fake_settings)
    token = await login(client, "nadia-target@autoco.example")
    response = await client.post(
        "/perf/pishgam/targeting/check-polygons",
        headers=auth(token),
        json={"keys": ["zaferanieh"]},
    )
    assert response.status_code == 200, response.text
    assert seen[0][0].endswith("/SmartSms/CheckPolygonCells")
    assert "CreateSimple" not in seen[0][0]
    assert seen[0][1]["polygon"][0] == [51.405, 35.812]
    row = response.json()["areas"][0]
    assert row["name_fa"] == "زعفرانیه"
    assert row["checks"][0]["operator_name"] == "همراه اول"
    assert row["checks"][1]["is_valid_area"] is False


async def test_preview_blocks_links(client, seeded, db):
    await _nadia(db, seeded)
    token = await login(client, "nadia-target@autoco.example")
    response = await client.post(
        "/perf/pishgam/targeting/preview",
        headers=auth(token),
        json={
            "keys": ["zaferanieh"],
            "operators": [1, 2],
            "sms_body": "سلام https://x.ir لغو11",
            "links_allowed": False,
        },
    )
    assert response.status_code == 422
    assert "لینک" in response.json()["detail"]


async def test_pishgam_status_surfaces_in_detail(client, seeded, db, monkeypatch):
    await _nadia(db, seeded)

    async def fetch(method, url, token, params, payload):
        if url.endswith("/CheckPolygonCells"):
            return 200, json.dumps({"statusCode": 62, "message": "Forbidden"})
        return 200, "{}"

    monkeypatch.setattr("app.perf.services.pishgam_targeting.fetch_http", fetch)
    monkeypatch.setattr("app.perf.services.pishgam_targeting.get_settings", _fake_settings)
    token = await login(client, "nadia-target@autoco.example")
    response = await client.post(
        "/perf/pishgam/targeting/check-polygons",
        headers=auth(token),
        json={"keys": ["zaferanieh"]},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["pishgam_statusCode"] == 62
    assert "هوشمند" in detail["pishgam_message"]


async def test_preview_create_refresh_getbyid(client, seeded, db, db_engine, monkeypatch):
    await _nadia(db, seeded)
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.perf.services.pishgam_targeting.WorkerSessionLocal", session_factory)
    refresh_calls = 0
    create_calls = 0

    async def fetch(method, url, token, params, payload):
        nonlocal refresh_calls, create_calls
        if url.endswith("/CheckPolygonCells"):
            return 200, json.dumps({
                "statusCode": 0,
                "data": [{"mobileOperator": 1, "isValid": True, "isValidArea": True}],
            })
        if url.endswith("/CreateSimpleSmartSmsRequest"):
            create_calls += 1
            assert payload["polygons"][0][0] == [51.405, 35.812]
            assert payload["residenceState"] == 0
            return 200, json.dumps({"statusCode": 0, "smartSmsRequestId": 99, "items": [], "message": "ok"})
        if url.endswith("/RefreshSmartSmsRequest"):
            refresh_calls += 1
            status = 0 if refresh_calls > 1 else 1
            return 200, json.dumps({"statusCode": 0, "smartSmsRequestStatus": status, "message": "ok"})
        if url.endswith("/GetSmartSmsRequestById"):
            return 200, json.dumps({
                "statusCode": 0,
                "result": {
                    "status": 0,
                    "expireDate": "1405/12/29",
                    "recipients": [
                        {"id": 1, "operator": 1, "count": 10, "persianPrice": 500, "englishPrice": 1000, "coordinates": []},
                    ],
                },
            })
        if url.endswith("/GetCredit"):
            return 200, json.dumps({"statusCode": 0, "credit": 10000})
        if url.endswith("/GetSmartSmsPrivateNumbersByOperator"):
            return 200, json.dumps({"statusCode": 0, "privateNumbers": [{"operator": 1, "number": "50001234"}]})
        raise AssertionError(url)

    monkeypatch.setattr("app.perf.services.pishgam_targeting.fetch_http", fetch)
    monkeypatch.setattr("app.perf.services.pishgam_targeting.get_settings", _fake_settings)

    async def _no_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.perf.services.pishgam_targeting.asyncio.sleep", _no_sleep)
    bg: list[asyncio.Task] = []
    real_create_task = asyncio.create_task

    def track_task(coro):
        task = real_create_task(coro)
        bg.append(task)
        return task

    monkeypatch.setattr("app.perf.services.pishgam_targeting.asyncio.create_task", track_task)
    token = await login(client, "nadia-target@autoco.example")
    response = await client.post(
        "/perf/pishgam/targeting/preview",
        headers=auth(token),
        json={
            "keys": ["zaferanieh"],
            "operators": [1],
            "residence_enabled": True,
            "sms_body": "ستوده\nلغو11",
            "links_allowed": False,
        },
    )
    if bg:
        await asyncio.gather(*bg)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["started"] is True
    assert body["preview"]["status"] == "checking"
    assert create_calls == 1
    assert refresh_calls >= 2
    view = await client.get("/perf/pishgam/targeting", headers=auth(token))
    preview = view.json()["preview"]
    assert preview["status"] == "done"
    assert preview["recipients"][0]["count"] == 10
    assert preview["areas"][0]["key"] == "zaferanieh"
    assert preview["credit"] == 10000


async def test_preview_uses_cache_without_second_create(client, seeded, db, db_engine, monkeypatch):
    await _nadia(db, seeded)
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.perf.services.pishgam_targeting.WorkerSessionLocal", session_factory)
    create_calls = 0

    async def fetch(method, url, token, params, payload):
        nonlocal create_calls
        if url.endswith("/CheckPolygonCells"):
            return 200, json.dumps({
                "statusCode": 0,
                "data": [{"mobileOperator": 1, "isValid": True, "isValidArea": True}],
            })
        if url.endswith("/CreateSimpleSmartSmsRequest"):
            create_calls += 1
            return 200, json.dumps({"statusCode": 0, "smartSmsRequestId": 99})
        if url.endswith("/RefreshSmartSmsRequest"):
            return 200, json.dumps({"statusCode": 0, "smartSmsRequestStatus": 0})
        if url.endswith("/GetSmartSmsRequestById"):
            return 200, json.dumps({
                "statusCode": 0,
                "result": {
                    "expireDate": "1405/12/29",
                    "recipients": [{"operator": 1, "count": 5, "persianPrice": 500, "englishPrice": 1000}],
                },
            })
        if url.endswith("/GetCredit"):
            return 200, json.dumps({"statusCode": 0, "credit": 5000})
        if url.endswith("/GetSmartSmsPrivateNumbersByOperator"):
            return 200, json.dumps({"statusCode": 0, "data": []})
        raise AssertionError(url)

    monkeypatch.setattr("app.perf.services.pishgam_targeting.fetch_http", fetch)
    monkeypatch.setattr("app.perf.services.pishgam_targeting.get_settings", _fake_settings)
    monkeypatch.setattr("app.perf.services.pishgam_targeting.asyncio.sleep", lambda *_a, **_k: None)
    bg: list[asyncio.Task] = []
    real_create_task = asyncio.create_task

    def track_task(coro):
        task = real_create_task(coro)
        bg.append(task)
        return task

    monkeypatch.setattr("app.perf.services.pishgam_targeting.asyncio.create_task", track_task)
    token = await login(client, "nadia-target@autoco.example")
    payload = {
        "keys": ["zaferanieh"],
        "operators": [1],
        "residence_enabled": True,
        "sms_body": "ستوده\nلغو11",
        "links_allowed": False,
    }
    first = await client.post("/perf/pishgam/targeting/preview", headers=auth(token), json=payload)
    if bg:
        await asyncio.gather(*bg)
        bg.clear()
    assert first.status_code == 200
    await client.get("/perf/pishgam/targeting", headers=auth(token))
    assert create_calls == 1
    second = await client.post("/perf/pishgam/targeting/preview", headers=auth(token), json=payload)
    assert second.status_code == 200
    assert second.json()["from_cache"] is True
    assert create_calls == 1
