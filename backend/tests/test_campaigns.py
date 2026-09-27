"""Campaigns linked to communication threads."""

import pytest


@pytest.mark.asyncio
async def test_campaign_list_and_link_conversation(client, seeded):
    login = await client.post(
        "/auth/login",
        json={
            "organization_slug": "autoco",
            "email": "sara@autoco.example",
            "password": "password",
        },
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = await client.post(
        "/campaigns",
        headers=headers,
        json={"title": "Instagram Camry push", "status": "ACTIVE"},
    )
    assert created.status_code == 200, created.text
    camp_id = created.json()["id"]

    listed = await client.get("/campaigns", headers=headers)
    assert listed.status_code == 200
    assert any(c["id"] == camp_id for c in listed.json())

    conv = await client.post(
        "/conversations",
        headers=headers,
        json={
            "topic": "Discuss Instagram Camry",
            "participant_ids": [str(seeded["sara"].id)],
            "channel": "WEB",
            "campaign_id": camp_id,
        },
    )
    assert conv.status_code == 200, conv.text
    assert conv.json()["campaign_id"] == camp_id

    threads = await client.get(f"/conversations?campaign_id={camp_id}", headers=headers)
    assert threads.status_code == 200
    assert len(threads.json()) >= 1
    assert threads.json()[0]["campaign_id"] == camp_id
