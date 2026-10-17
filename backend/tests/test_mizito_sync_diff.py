"""diff همگام‌سازی میزیتو با دادهٔ ساختگی؛ بدون شبکه."""

from unittest.mock import AsyncMock

import pytest

from app.models import Task, User
from app.perf.services.mizito import _project_tasks, for_perf, read_cards
from app.requests.mizito_sync import apply_mizito_cards, card_hash, decide_change, sync_mizito_cards_to_projects
from app.requests.models import WorkMizitoChange, WorkProject, WorkProjectMember
from app.core.permissions import PermissionCode
from tests.conftest import auth, login
from app.worker import acquire_job, release_job
from sqlalchemy import select


def _card(card_id="c1", board="b1", board_name="برای انجام", title="کارت", checklist=None):
    return {
        "id": card_id,
        "project": "پرفورمنس مارکتینگ",
        "project_id": "p1",
        "board_id": board,
        "board": board_name,
        "board_position": 0,
        "title": title,
        "code": "",
        "status": "todo",
        "completed": False,
        "weight": 1,
        "progress": 0,
        "assignees": [],
        "checklist_items": checklist or [],
        "checklist_done": 0,
        "checklist_total": len(checklist or []),
        "attachments": 0,
        "has_comments": False,
        "created_at": "2026-01-01T00:00:00+00:00",
        "modified_at": "2026-01-02T00:00:00+00:00",
        "deadline": None,
        "completed_at": None,
    }


def _snap(cards, boards=None, truncated=None):
    return {
        "cards": cards,
        "lane_boards": boards
        or [{"lane_slug": "performance", "board_id": "b1", "title": "برای انجام", "position": 0}],
        "truncated_projects": truncated or [],
        "truncated": bool(truncated),
        "projects": [{"id": "p1", "title": "پرفورمنس مارکتینگ"}],
    }


@pytest.mark.asyncio
async def test_unchanged_card_keeps_cm_budget_and_member(db, seeded):
    org = seeded["org"].id
    actor = await db.scalar(select(User.id).where(User.organization_id == org))
    card = _card()
    first = await apply_mizito_cards(db, org, _snap([card]), actor=actor)
    assert first["created"] == 1
    project = await db.scalar(select(WorkProject).where(WorkProject.mizito_card_id == "c1"))
    project.planned_budget = 5000
    db.add(WorkProjectMember(organization_id=org, project_id=project.id, user_id=actor))
    await db.flush()
    second = await apply_mizito_cards(db, org, _snap([card]), actor=actor)
    assert second["unchanged"] == 1
    await db.refresh(project)
    assert project.planned_budget == 5000
    members = list(await db.scalars(select(WorkProjectMember).where(WorkProjectMember.project_id == project.id)))
    assert len(members) == 1


@pytest.mark.asyncio
async def test_board_change_logs_only_that_field(db, seeded):
    org = seeded["org"].id
    actor = await db.scalar(select(User.id).where(User.organization_id == org))
    await apply_mizito_cards(db, org, _snap([_card()]), actor=actor)
    moved = _card(board="b2", board_name="در حال انجام")
    moved["status"] = "in_progress"
    result = await apply_mizito_cards(
        db,
        org,
        _snap(
            [moved],
            boards=[
                {"lane_slug": "performance", "board_id": "b1", "title": "برای انجام", "position": 0},
                {"lane_slug": "performance", "board_id": "b2", "title": "در حال انجام", "position": 1},
            ],
        ),
        actor=actor,
    )
    assert result["updated"] == 1
    logs = list(await db.scalars(select(WorkMizitoChange).where(WorkMizitoChange.kind == "updated")))
    fields = {row.field for row in logs}
    assert "mizito_board" in fields
    assert "status" in fields


@pytest.mark.asyncio
async def test_missing_twice_then_approve_archives(db, seeded):
    org = seeded["org"].id
    actor = await db.scalar(select(User.id).where(User.organization_id == org))
    await apply_mizito_cards(db, org, _snap([_card()]), actor=actor)
    await apply_mizito_cards(db, org, _snap([]), actor=actor)
    pending = await apply_mizito_cards(db, org, _snap([]), actor=actor)
    assert pending["pending"] == 1
    change = await db.scalar(select(WorkMizitoChange).where(WorkMizitoChange.status == "pending"))
    await decide_change(db, org, change.id, actor, True)
    project = await db.scalar(select(WorkProject).where(WorkProject.mizito_card_id == "c1"))
    assert project.mizito_removed_at is not None
    ignored = await apply_mizito_cards(db, org, _snap([_card(card_id="c2")]), actor=actor)
    other = await db.scalar(select(WorkProject).where(WorkProject.mizito_card_id == "c1"))
    assert other.mizito_removed_at is not None
    assert ignored["created"] == 1


@pytest.mark.asyncio
async def test_ignore_resets_missing_counter(db, seeded):
    org = seeded["org"].id
    actor = await db.scalar(select(User.id).where(User.organization_id == org))
    await apply_mizito_cards(db, org, _snap([_card()]), actor=actor)
    await apply_mizito_cards(db, org, _snap([]), actor=actor)
    await apply_mizito_cards(db, org, _snap([]), actor=actor)
    change = await db.scalar(select(WorkMizitoChange).where(WorkMizitoChange.status == "pending"))
    await decide_change(db, org, change.id, actor, False)
    project = await db.scalar(select(WorkProject).where(WorkProject.mizito_card_id == "c1"))
    assert project.mizito_missing_runs == 0
    assert project.mizito_removed_at is None


@pytest.mark.asyncio
async def test_checklist_title_change_keeps_one_task(db, seeded):
    org = seeded["org"].id
    actor = await db.scalar(select(User.id).where(User.organization_id == org))
    first = _card(checklist=[{"id": "item-1", "title": "قدم", "checked": False}])
    await apply_mizito_cards(db, org, _snap([first]), actor=actor)
    renamed = _card(checklist=[{"id": "item-1", "title": "قدم تازه", "checked": True}])
    renamed["modified_at"] = "2026-02-01T00:00:00+00:00"
    await apply_mizito_cards(db, org, _snap([renamed]), actor=actor)
    tasks = list(await db.scalars(select(Task).where(Task.external_ref == "item-1")))
    assert len(tasks) == 1
    assert tasks[0].title == "قدم تازه"


@pytest.mark.asyncio
async def test_auth_failure_does_not_write_projects(db, seeded, monkeypatch):
    org = seeded["org"].id
    monkeypatch.setattr(
        "app.requests.mizito_sync.mizito_full_read",
        AsyncMock(return_value={"connected": False, "reason": "توکن میزیتو پذیرفته نشد (۴۰۱)."}),
    )
    before = list(await db.scalars(select(WorkProject.id).where(WorkProject.mizito_card_id.is_not(None))))
    result = await sync_mizito_cards_to_projects(db, org, token="x")
    assert result["ok"] is False
    after = list(await db.scalars(select(WorkProject.id).where(WorkProject.mizito_card_id.is_not(None))))
    assert after == before


def test_perf_snapshot_drops_content_lane():
    projects = {
        "projects": [
            {"_id": "p1", "title": "تولید محتوا", "kanban_boards": [{"_id": "b", "title": "ایده"}]},
            {"_id": "p2", "title": "پرفورمنس مارکتینگ", "kanban_boards": [{"_id": "b2", "title": "برای انجام"}]},
        ]
    }
    tasks = [
        {"_id": "a", "title": "محتوا", "project": "p1", "kanban_board": "b"},
        {"_id": "b", "title": "تبلیغ", "project": "p2", "kanban_board": "b2"},
    ]
    parsed = for_perf(read_cards(projects, tasks, checklist_limit=None, max_cards=100))
    assert [row["title"] for row in parsed["projects"]] == ["پرفورمنس مارکتینگ"]
    assert [card["id"] for card in parsed["cards"]] == ["b"]


@pytest.mark.asyncio
async def test_page_cap_sets_truncated(monkeypatch):
    async def fake_post(_client, _base, _path, _headers, body):
        if body.get("kanban"):
            return []
        return [{"_id": f"d{body.get('from')}-{i}"} for i in range(25)]

    monkeypatch.setattr("app.perf.services.mizito.mizito_post", fake_post)
    _rows, truncated = await _project_tasks(None, "https://example.invalid", {}, "p", max_pages=1)
    assert truncated is True


@pytest.mark.asyncio
async def test_job_lock_blocks_second_acquire(monkeypatch):
    monkeypatch.setattr("app.worker._redis_mode", AsyncMock(return_value="absent"))

    async def no_db(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.worker.try_acquire_db_lock", no_db)
    assert await acquire_job("mizito_sync_test", ttl_seconds=30)
    assert await acquire_job("mizito_sync_test", ttl_seconds=30) is False
    await release_job("mizito_sync_test")


def test_hash_stable():
    card = _card()
    assert card_hash(card, "performance") == card_hash(card, "performance")


@pytest.mark.asyncio
async def test_patch_mizito_owned_field_is_rejected(client, seeded, db):
    from app.services import OrgService

    org = seeded["org"].id
    svc = OrgService(db)
    role = await svc.create_role(org, "ترییج میزیتو", "mizito_triage_role", [PermissionCode.REQUEST_TRIAGE], "organization")
    await svc.create_user(
        organization_id=org,
        email="mizito-triage@autoco.example",
        full_name="ترییج",
        password="password",
        role_id=role.id,
        branch_id=seeded["branch"].id,
    )
    await db.commit()
    actor = await db.scalar(select(User.id).where(User.organization_id == org))
    await apply_mizito_cards(db, org, _snap([_card()]), actor=actor)
    await db.commit()
    project = await db.scalar(select(WorkProject).where(WorkProject.mizito_card_id == "c1"))
    headers = auth(await login(client, "mizito-triage@autoco.example"))
    listed = await client.get("/requests/projects?source=mizito", headers=headers)
    assert listed.status_code == 200
    assert any(row["id"] == str(project.id) for row in listed.json())
    native = await client.get("/requests/projects?source=cm", headers=headers)
    assert all(row["id"] != str(project.id) for row in native.json())
    patched = await client.patch(f"/requests/projects/{project.id}", headers=headers, json={"title": "دستی"})
    assert patched.status_code == 409
