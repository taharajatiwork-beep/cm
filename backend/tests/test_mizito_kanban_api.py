"""کانبان و فهرست صفحه‌بندی‌شدهٔ پروژه‌ها."""

import pytest
from sqlalchemy import select

from app.api.deps import AuthContext, load_data_scope
from app.core.permissions import PermissionCode
from app.models import User
from app.requests.mizito_kanban import mizito_kanban_column, mizito_lane_kanban
from app.requests.mizito_lanes import is_archive_board_title
from app.requests.models import WorkMizitoLaneBoard, WorkProject, WorkRequest
from app.services import OrgService, get_user_permissions
from tests.conftest import auth, login


async def _triage_user(db, seeded) -> User:
    svc = OrgService(db)
    role = await svc.create_role(
        seeded["org"].id,
        "Kanban triage",
        "kanban_page_triage",
        [PermissionCode.REQUEST_TRIAGE, PermissionCode.TASK_READ],
        "organization",
    )
    return await svc.create_user(
        organization_id=seeded["org"].id,
        email="kanban-page-triage@autoco.example",
        full_name="Kanban Triage",
        password="password",
        role_id=role.id,
        branch_id=seeded["branch"].id,
        team_id=seeded["mkt_team"].id,
    )


def test_is_archive_board_title():
    assert is_archive_board_title("پرداخت شده")
    assert not is_archive_board_title("درخواست پرداخت")


async def _ctx(db, user: User) -> AuthContext:
    perms = await get_user_permissions(db, user)
    scope = await load_data_scope(db, user, perms)
    return AuthContext(user=user, permissions=perms, organization_id=user.organization_id, scope=scope)


@pytest.mark.asyncio
async def test_kanban_respects_visibility(db, seeded):
    org = seeded["org"].id
    svc = OrgService(db)
    triage_role = await svc.create_role(
        org, "ترییج", "kanban_triage", [PermissionCode.REQUEST_TRIAGE, PermissionCode.TASK_READ], "organization"
    )
    req_role = await svc.create_role(org, "مدیر", "kanban_req", [PermissionCode.REQUEST_CREATE], "organization")
    triage_user = await svc.create_user(
        organization_id=org,
        email="kanban-triage@autoco.example",
        full_name="Triage",
        password="password",
        role_id=triage_role.id,
        branch_id=seeded["branch"].id,
    )
    requester = await svc.create_user(
        organization_id=org,
        email="kanban-req@autoco.example",
        full_name="Requester",
        password="password",
        role_id=req_role.id,
        branch_id=seeded["branch"].id,
    )
    req = WorkRequest(
        organization_id=org,
        code="REQ-900",
        title="فقط من",
        kind="عمومی",
        status="new",
        requested_by=requester.id,
    )
    db.add(req)
    await db.flush()
    mine = WorkProject(
        organization_id=org,
        code="MZ-MINE",
        title="پروژه من",
        kind="عمومی",
        status="in_progress",
        request_id=req.id,
        mizito_lane="finance_marketing",
        mizito_card_id="card-mine",
        mizito_board_id="b-open",
        mizito_board="باز",
    )
    other = WorkProject(
        organization_id=org,
        code="MZ-OTHER",
        title="پروژه دیگران",
        kind="عمومی",
        status="done",
        mizito_lane="finance_marketing",
        mizito_card_id="card-other",
        mizito_board_id="b-open",
        mizito_board="باز",
    )
    db.add_all([mine, other])
    db.add(
        WorkMizitoLaneBoard(
            organization_id=org,
            lane_slug="finance_marketing",
            board_id="b-open",
            title="باز",
            position=0,
        )
    )
    await db.commit()

    board_admin = await mizito_lane_kanban(db, await _ctx(db, triage_user), "finance_marketing")
    assert board_admin["lane_total"] == 2

    board_req = await mizito_lane_kanban(db, await _ctx(db, requester), "finance_marketing")
    assert board_req["lane_total"] == 1
    assert board_req["columns"][0]["projects"][0]["code"] == "MZ-MINE"


@pytest.mark.asyncio
async def test_kanban_hide_done_and_column_page(db, seeded):
    org = seeded["org"].id
    triage = await _triage_user(db, seeded)
    ctx = await _ctx(db, triage)
    db.add(
        WorkMizitoLaneBoard(
            organization_id=org,
            lane_slug="performance",
            board_id="b1",
            title="کار",
            position=0,
        )
    )
    for idx, st in enumerate(["done", "done", "in_progress"]):
        db.add(
            WorkProject(
                organization_id=org,
                code=f"MZ-P{idx}",
                title=f"کارت {idx}",
                kind="عمومی",
                status=st,
                team_id=seeded["mkt_team"].id,
                mizito_lane="performance",
                mizito_card_id=f"c{idx}",
                mizito_board_id="b1",
                mizito_board="کار",
            )
        )
    await db.commit()

    full = await mizito_lane_kanban(db, ctx, "performance", per_column=1)
    col = full["columns"][0]
    assert col["total"] == 3
    assert col["open_count"] == 1
    assert col["has_more"] is True

    hidden = await mizito_lane_kanban(db, ctx, "performance", hide_done=True)
    assert hidden["columns"][0]["total"] == 1

    page = await mizito_kanban_column(db, ctx, "performance", "b1", offset=1, limit=2)
    assert page["total"] == 3
    assert len(page["projects"]) == 2


@pytest.mark.asyncio
async def test_projects_page_search_and_total(db, seeded, client):
    org = seeded["org"].id
    db.add(
        WorkProject(
            organization_id=org,
            code="MZ-SEARCH",
            title="پرداخت استوری",
            kind="عمومی",
            status="new",
            mizito_lane="content",
            team_id=seeded["mkt_team"].id,
        )
    )
    triage = await _triage_user(db, seeded)
    await db.commit()
    token = await login(client, triage.email)
    res = await client.get(
        "/requests/projects/page",
        params={"q": "MZ-SEARCH", "mizito_lane": "content"},
        headers=auth(token),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 1
    assert any(item["code"] == "MZ-SEARCH" for item in body["items"])
