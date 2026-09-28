"""Org admin: deactivate, password reset, role permissions, team membership."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import AuditLog, User
from app.services import OrgService
from tests.conftest import auth, login


async def _admin_token(client: AsyncClient, seeded, db) -> str:
    """The seed has an org-admin role but no user on it — make one for tests."""
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


async def _audit_actions(db, *names: str) -> set[str]:
    await db.commit()
    rows = list((await db.execute(select(AuditLog))).scalars())
    found = {r.action for r in rows}
    missing = [n for n in names if n not in found]
    assert not missing, f"missing audit actions: {missing} (found {sorted(found)})"
    return found


@pytest.mark.asyncio
async def test_non_admin_cannot_manage_users(client: AsyncClient, seeded):
    ali = await login(client, "ali@autoco.example")
    reza = seeded["reza"]
    manager_role = seeded["manager_role"]

    # Ali has USER_WRITE but not org.admin, so every admin surface is 403.
    r = await client.patch(
        f"/org/users/{reza.id}", headers=auth(ali), json={"is_active": False}
    )
    assert r.status_code == 403

    r = await client.patch(
        f"/org/roles/{manager_role.id}",
        headers=auth(ali),
        json={"permission_codes": ["task.read"]},
    )
    assert r.status_code == 403

    r = await client.get(f"/org/roles/{manager_role.id}/permissions", headers=auth(ali))
    assert r.status_code == 403

    r = await client.post(
        f"/org/users/{reza.id}/teams",
        headers=auth(ali),
        json={"user_id": str(reza.id), "team_id": str(seeded["mkt_team"].id)},
    )
    assert r.status_code == 403

    # Deactivation must not have happened behind the 403.
    still = await client.get("/people", headers=auth(ali))
    assert any(str(u["id"]) == str(reza.id) and u["is_active"] for u in still.json())


@pytest.mark.asyncio
async def test_deactivate_blocks_login_and_existing_token(
    client: AsyncClient, seeded, db
):
    admin = await _admin_token(client, seeded, db)
    reza = seeded["reza"]
    old_token = await login(client, "reza@autoco.example")

    r = await client.patch(
        f"/org/users/{reza.id}", headers=auth(admin), json={"is_active": False}
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    # Login refused and the already-issued access token stops working.
    bad = await client.post(
        "/auth/login",
        json={"organization_slug": "autoco", "email": "reza@autoco.example", "password": "password"},
    )
    assert bad.status_code == 401
    me = await client.get("/auth/me", headers=auth(old_token))
    assert me.status_code == 401

    await _audit_actions(db, "user.deactivated")

    # The row survives (history and foreign keys), and reactivation works.
    row = await db.get(User, reza.id)
    assert row is not None
    await db.refresh(row)  # the API wrote through another session
    assert row.is_active is False

    back = await client.patch(
        f"/org/users/{reza.id}", headers=auth(admin), json={"is_active": True}
    )
    assert back.status_code == 200
    ok = await client.post(
        "/auth/login",
        json={"organization_slug": "autoco", "email": "reza@autoco.example", "password": "password"},
    )
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_admin_password_reset_with_validation(client: AsyncClient, seeded, db):
    admin = await _admin_token(client, seeded, db)
    sara = seeded["sara"]

    weak = await client.patch(
        f"/org/users/{sara.id}", headers=auth(admin), json={"password": "abc"}
    )
    assert weak.status_code == 400

    good = await client.patch(
        f"/org/users/{sara.id}", headers=auth(admin), json={"password": "NewPass123"}
    )
    assert good.status_code == 200

    old = await client.post(
        "/auth/login",
        json={"organization_slug": "autoco", "email": "sara@autoco.example", "password": "password"},
    )
    assert old.status_code == 401
    new = await client.post(
        "/auth/login",
        json={"organization_slug": "autoco", "email": "sara@autoco.example", "password": "NewPass123"},
    )
    assert new.status_code == 200

    await _audit_actions(db, "user.password_reset")


@pytest.mark.asyncio
async def test_role_permissions_read_and_update(client: AsyncClient, seeded, db):
    admin = await _admin_token(client, seeded, db)
    manager = seeded["manager_role"]

    r = await client.get(f"/org/roles/{manager.id}/permissions", headers=auth(admin))
    assert r.status_code == 200
    current = r.json()
    assert "task.read" in current["permission_codes"]
    assert current["data_scope_level"] == "branch"

    r = await client.patch(
        f"/org/roles/{manager.id}",
        headers=auth(admin),
        json={"permission_codes": ["task.read", "case.read"], "data_scope_level": "team"},
    )
    assert r.status_code == 200

    after = (
        await client.get(f"/org/roles/{manager.id}/permissions", headers=auth(admin))
    ).json()
    assert set(after["permission_codes"]) == {"task.read", "case.read"}
    assert after["data_scope_level"] == "team"

    await _audit_actions(db, "role.updated")


@pytest.mark.asyncio
async def test_team_membership_keeps_primary_team(client: AsyncClient, seeded, db):
    admin = await _admin_token(client, seeded, db)
    reza = seeded["reza"]
    primary = str(reza.team_id)

    r = await client.post(
        f"/org/users/{reza.id}/teams",
        headers=auth(admin),
        json={"user_id": str(reza.id), "team_id": str(seeded["mkt_team"].id)},
    )
    assert r.status_code == 200
    assert r.json()["team_id"] == str(seeded["mkt_team"].id)

    # users.team_id is the primary team and must not move.
    person = await client.get(f"/people/{reza.id}", headers=auth(admin))
    assert person.status_code == 200
    assert str(person.json()["team_id"]) == primary

    await _audit_actions(db, "user.team_added")
