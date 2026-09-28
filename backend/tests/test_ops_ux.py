"""Ops and UX endpoints added for the operational plan."""

import pytest
from httpx import AsyncClient

from app.core.pdf import build_pdf
from tests.conftest import auth, login


def test_pdf_embeds_persian():
    payload = build_pdf(title="گزارش", lines=["کارهای باز: ۳"])
    assert payload.startswith(b"%PDF")
    assert b"Vazirmatn" in payload


@pytest.mark.asyncio
async def test_customer_list_envelope(client: AsyncClient, seeded):
    token = await login(client, "ali@autoco.example")
    created = await client.post(
        "/customers",
        headers=auth(token),
        json={"full_name": "مشتری تست", "phone": "09120000000"},
    )
    assert created.status_code == 200, created.text
    customer_id = created.json()["id"]
    moved = await client.patch(
        f"/customers/{customer_id}",
        headers=auth(token),
        json={"stage": "visit"},
    )
    assert moved.status_code == 200
    assert moved.json()["stage"] == "visit"

    listed = await client.get("/customers?envelope=1&limit=1", headers=auth(token))
    assert listed.status_code == 200
    body = listed.json()
    assert "items" in body
    assert "next_cursor" in body
