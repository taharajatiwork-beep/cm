import pytest
from httpx import AsyncClient

from app.api.routes import telegram as telegram_routes
from app.integrations.telegram.client import FakeTelegramClient
from tests.conftest import auth, login

WEBHOOK_SECRET = "dev-telegram-webhook-secret"


def tg_headers() -> dict:
    return {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}


@pytest.fixture
def fake_tg():
    client = FakeTelegramClient()
    telegram_routes.set_test_telegram_client(client)
    yield client
    telegram_routes.set_test_telegram_client(None)


async def _link_ali(client: AsyncClient, fake_tg: FakeTelegramClient) -> None:
    token = await login(client, "ali@autoco.example")
    code_resp = await client.post("/telegram/link-code", headers=auth(token))
    assert code_resp.status_code == 200, code_resp.text
    code = code_resp.json()["link_code"]

    r = await client.post(
        "/telegram/webhook",
        headers=tg_headers(),
        json={
            "update_id": 1,
            "message": {
                "message_id": 10,
                "text": f"/link {code}",
                "chat": {"id": 1001},
                "from": {"id": 9001, "username": "ali_mgr"},
            },
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert any("متصل" in m.text or "linked" in m.text.lower() for m in fake_tg.sent)


@pytest.mark.asyncio
async def test_webhook_rejects_bad_secret(client: AsyncClient):
    r = await client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        json={"update_id": 1},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_link_and_camry_work_item(client: AsyncClient, seeded, fake_tg: FakeTelegramClient):
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

    await _link_ali(client, fake_tg)
    fake_tg.sent.clear()

    persian = "برای این کمری، رضا مشتری رو پیگیری کنه و سارا تبلیغات رو انجام بده."
    r = await client.post(
        "/telegram/webhook",
        headers=tg_headers(),
        json={
            "update_id": 2,
            "message": {
                "message_id": 20,
                "text": persian,
                "chat": {"id": 1001},
                "from": {"id": 9001, "username": "ali_mgr"},
            },
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    # Phase 3: confirmation required before create
    assert body["clarification"] is True
    assert body["work_item_id"] is None
    assert any("بسازم" in m.text or "Create" in m.text for m in fake_tg.sent)

    # Extract confirm callback
    confirm_cb = None
    for m in fake_tg.sent:
        if m.reply_markup:
            for row in m.reply_markup.get("inline_keyboard", []):
                for btn in row:
                    data = btn.get("callback_data") or ""
                    if data.startswith("ok:"):
                        confirm_cb = data
    assert confirm_cb, "expected confirm button"

    fake_tg.sent.clear()
    r2 = await client.post(
        "/telegram/webhook",
        headers=tg_headers(),
        json={
            "update_id": 22,
            "callback_query": {
                "id": "cq1",
                "data": confirm_cb,
                "from": {"id": 9001, "username": "ali_mgr"},
                "message": {
                    "message_id": 21,
                    "chat": {"id": 1001},
                    "text": "preview",
                },
            },
        },
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["ok"] is True
    assert body2["work_item_id"] is not None
    assert "پروژه" in body2["reply_text"] or "Project" in body2["reply_text"]
    assert "Reza" in body2["reply_text"] or "رضا" in body2["reply_text"] or "Contact" in body2["reply_text"]

    progress = await client.get(
        f"/work-items/{body2['work_item_id']}/progress",
        headers=auth(token),
    )
    assert progress.status_code == 200
    assert progress.json()["total_tasks"] == 2


@pytest.mark.asyncio
async def test_ambiguous_vehicles_ask_clarification(
    client: AsyncClient, seeded, fake_tg: FakeTelegramClient
):
    token = await login(client, "ali@autoco.example")
    for stock, vin_suffix in [("124", "12424"), ("125", "12525")]:
        r = await client.post(
            "/inventory/vehicles",
            headers=auth(token),
            json={
                "vin": f"JTDBR32E7200{vin_suffix}",
                "brand": "Toyota",
                "model": "Camry",
                "year": 2020,
                "stock_number": stock,
                "branch_id": str(seeded["branch"].id),
            },
        )
        assert r.status_code == 200, r.text

    await _link_ali(client, fake_tg)
    fake_tg.sent.clear()

    r = await client.post(
        "/telegram/webhook",
        headers=tg_headers(),
        json={
            "update_id": 3,
            "message": {
                "message_id": 30,
                "text": "برای این کمری، رضا مشتری رو پیگیری کنه و سارا تبلیغات رو انجام بده.",
                "chat": {"id": 1001},
                "from": {"id": 9001, "username": "ali_mgr"},
            },
        },
    )
    assert r.status_code == 200
    assert r.json()["clarification"] is True
    assert r.json()["work_item_id"] is None
    reply = r.json()["reply_text"].lower()
    assert "multiple" in reply or "which one" in reply or "کدام" in r.json()["reply_text"]


@pytest.mark.asyncio
async def test_unlinked_user_prompted(client: AsyncClient, seeded, fake_tg: FakeTelegramClient):
    r = await client.post(
        "/telegram/webhook",
        headers=tg_headers(),
        json={
            "update_id": 4,
            "message": {
                "message_id": 40,
                "text": "hello",
                "chat": {"id": 2002},
                "from": {"id": 8002, "username": "stranger"},
            },
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "متصل" in r.json()["reply_text"] or "not linked" in r.json()["reply_text"].lower()


@pytest.mark.asyncio
async def test_duplicate_update_ignored(client: AsyncClient, seeded, fake_tg: FakeTelegramClient):
    await _link_ali(client, fake_tg)
    fake_tg.sent.clear()
    payload = {
        "update_id": 50,
        "message": {
            "message_id": 50,
            "text": "/help",
            "chat": {"id": 1001},
            "from": {"id": 9001, "username": "ali_mgr"},
        },
    }
    r1 = await client.post("/telegram/webhook", headers=tg_headers(), json=payload)
    assert r1.status_code == 200
    n1 = len(fake_tg.sent)
    r2 = await client.post("/telegram/webhook", headers=tg_headers(), json=payload)
    assert r2.status_code == 200
    assert len(fake_tg.sent) == n1  # no extra replies


@pytest.mark.asyncio
async def test_stable_dm_conversation(client: AsyncClient, seeded, fake_tg: FakeTelegramClient):
    token = await login(client, "ali@autoco.example")
    await _link_ali(client, fake_tg)
    for i, upd in enumerate([60, 61], start=1):
        await client.post(
            "/telegram/webhook",
            headers=tg_headers(),
            json={
                "update_id": upd,
                "message": {
                    "message_id": 100 + i,
                    "text": f"ping {i}",
                    "chat": {"id": 1001},
                    "from": {"id": 9001, "username": "ali_mgr"},
                },
            },
        )
    convs = await client.get("/conversations", headers=auth(token))
    assert convs.status_code == 200
    tg_convs = [c for c in convs.json() if str(c.get("topic") or "").startswith("telegram:")]
    assert len(tg_convs) == 1


@pytest.mark.asyncio
async def test_status_and_unlink(client: AsyncClient, seeded, fake_tg: FakeTelegramClient):
    token = await login(client, "ali@autoco.example")
    st0 = await client.get("/telegram/status", headers=auth(token))
    assert st0.status_code == 200
    assert st0.json()["linked"] is False

    await _link_ali(client, fake_tg)
    st1 = await client.get("/telegram/status", headers=auth(token))
    assert st1.json()["linked"] is True
    assert st1.json()["username"] == "ali_mgr"

    un = await client.post("/telegram/unlink", headers=auth(token))
    assert un.status_code == 200
    st2 = await client.get("/telegram/status", headers=auth(token))
    assert st2.json()["linked"] is False


@pytest.mark.asyncio
async def test_complete_task_via_callback(client: AsyncClient, seeded, fake_tg: FakeTelegramClient):
    token = await login(client, "ali@autoco.example")
    await _link_ali(client, fake_tg)

    # Create a task assigned to Ali
    wi = await client.post(
        "/work-items",
        headers=auth(token),
        json={"title": "Test project", "priority": "HIGH"},
    )
    assert wi.status_code == 200, wi.text
    task = await client.post(
        "/tasks",
        headers=auth(token),
        json={
            "title": "Do the thing",
            "work_item_id": wi.json()["id"],
            "assignee_ids": [str(seeded["ali"].id)],
            "priority": "HIGH",
        },
    )
    assert task.status_code == 200, task.text
    task_id = task.json()["id"]

    from app.integrations.telegram.callbacks import encode_callback

    cb = encode_callback("done", "task", task_id)
    r = await client.post(
        "/telegram/webhook",
        headers=tg_headers(),
        json={
            "update_id": 70,
            "callback_query": {
                "id": "cq-done",
                "data": cb,
                "from": {"id": 9001},
                "message": {"message_id": 70, "chat": {"id": 1001}, "text": "Do the thing"},
            },
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "انجام" in r.json()["reply_text"] or "Done" in r.json()["reply_text"]

    progress = await client.get(f"/work-items/{wi.json()['id']}/progress", headers=auth(token))
    assert progress.json()["completed_tasks"] == 1
