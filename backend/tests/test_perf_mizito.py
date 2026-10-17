"""میزیتو (فقط خواندنی): ساختار پاسخ، وضعیت بردها و فیلدهای نگه‌داشته. همهٔ داده‌ها ساختگی‌اند."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.perf.services import mizito
from app.perf.services.common import PerfError
from app.perf.services.mizito import _unwrap, board_status, read_cards, saved_mizito

FAKE_TOKEN = "fake-jwt-not-a-real-token"

PROJECTS = {
    "projects": [
        {
            "_id": "p-money",
            "title": "مالی و مارکتینگ",
            "kanban_boards": [
                {"_id": "b-ask", "title": "درخواست پرداخت", "color": "red"},
                {"_id": "b-paid", "title": "پرداخت شده", "color": "green"},
                {"_id": "b-cost", "title": "ثبت نشده در Cost Tracking", "color": "blue"},
            ],
        },
        {"_id": "p-other", "title": "پروژهٔ دیگر", "kanban_boards": [{"_id": "b-x", "title": "برای انجام"}]},
    ],
    "project_status": [],
}

TASKS = [
    {
        "_id": "t-1",
        "title": "شارژ پنل X12",
        "notes": "متن آزاد ساختگی که نباید ذخیره شود",
        "project": "p-money",
        "kanban_board": "b-ask",
        "kanban_weight": 2,
        "assignee": [None, "u-a", "u-a"],
        "owner": "u-owner",
        "created_at": "2026-01-01T08:00:00.000Z",
        "modified_at": "2026-01-03T09:30:00.000Z",
        "has_deadline": False,
        "completed": False,
        "completed_at": None,
        "deleted": False,
        "checklist": [
            {"_id": "c1", "title": "قدم یک", "checked": True},
            {"_id": "c2", "title": "قدم دو", "checked": False},
            {"_id": "c3", "title": "قدم سه", "checked": False},
        ],
        "progress": 33,
        "attachments": [{"_id": "a1", "media": {"url": "https://media.example.invalid/signed?sig=fake"}}],
        "has_attachments": True,
        "has_comments": True,
        "last_comment": {"comment": "نظر ساختگی", "comment_at": "2026-01-02T10:00:00.000Z", "comment_owner": "u-a"},
        "labels": ["l-1"],
        "access_token": FAKE_TOKEN,
    },
    {
        "_id": "t-2",
        "title": "پرداخت قدیمی Y7",
        "project": "p-money",
        "kanban_board": "b-paid",
        "kanban_weight": 1,
        "assignee": [None],
        "owner": "u-owner",
        "created_at": "2025-12-01T08:00:00.000Z",
        "modified_at": "2025-12-02T08:00:00.000Z",
        "deadline": "2025-12-05T20:30:00.000Z",
        "access_token": FAKE_TOKEN,
    },
    {"_id": "t-3", "title": "ثبت نشده", "project": "p-money", "kanban_board": "b-cost", "access_token": FAKE_TOKEN},
    {"_id": "t-4", "title": "حذف‌شده", "project": "p-money", "kanban_board": "b-ask", "deleted": True},
    {"_id": "t-5", "title": "پروژهٔ بیرون", "project": "p-other", "kanban_board": "b-x"},
]


def test_unwrapped_response_keeps_safe_fields_only():
    parsed = read_cards(PROJECTS, TASKS)
    assert parsed["total_count"] == 3
    assert parsed["open_count"] == 2
    assert [card["id"] for card in parsed["cards"]] == ["t-1", "t-3", "t-2"]
    card = parsed["cards"][0]
    assert card["project"] == "مالی و مارکتینگ"
    assert card["board_id"] == "b-ask"
    assert card["board"] == "درخواست پرداخت"
    assert card["board_position"] == 0
    assert card["code"] == "X12"
    assert card["status"] == "waiting_payment"
    assert card["active"] is True
    assert card["assignees"] == ["u-a"]
    assert card["owner"] == "u-owner"
    assert card["created_at"] == "2026-01-01T08:00:00.000Z"
    assert card["modified_at"] == "2026-01-03T09:30:00.000Z"
    assert card["deadline"] is None
    assert (card["checklist_done"], card["checklist_total"], card["progress"]) == (1, 3, 33)
    assert card["attachments"] == 1
    assert card["has_comments"] is True
    assert card["last_comment_at"] == "2026-01-02T10:00:00.000Z"
    paid = parsed["cards"][2]
    assert paid["status"] == "paid"
    assert paid["active"] is False
    assert paid["assignees"] == []
    assert paid["deadline"] == "2025-12-05T20:30:00.000Z"
    assert parsed["cards"][1]["status"] == "not_in_cost_tracking"
    text = json.dumps(parsed, ensure_ascii=False)
    for secret in (FAKE_TOKEN, "access_token", "https://", "متن آزاد", "نظر ساختگی"):
        assert secret not in text


def test_wrapped_response_reads_the_same():
    wrapped_projects = {"status": 1, "msg": "", "data": PROJECTS}
    wrapped_tasks = {"status": "ok", "data": {"tasks": TASKS}}
    assert read_cards(_unwrap(wrapped_projects), _unwrap(wrapped_tasks)) == read_cards(PROJECTS, TASKS)
    assert read_cards(wrapped_projects, {"status": True, "data": TASKS}) == read_cards(PROJECTS, TASKS)
    assert _unwrap(TASKS) is TASKS
    assert _unwrap(PROJECTS) is PROJECTS


def test_wrapped_error_is_reported():
    with pytest.raises(PerfError):
        _unwrap({"status": 0, "msg": "توکن نامعتبر"})


def test_completed_card_keeps_board_status_but_is_not_active():
    task = {**TASKS[0], "completed": True, "completed_at": "2026-01-04T07:00:00.000Z"}
    card = read_cards(PROJECTS, [task])["cards"][0]
    assert card["status"] == "waiting_payment"
    assert card["completed"] is True
    assert card["completed_at"] == "2026-01-04T07:00:00.000Z"
    assert card["active"] is False
    assert read_cards(PROJECTS, TASKS)["cards"][0]["completed"] is False


def test_same_card_twice_is_kept_once():
    parsed = read_cards(PROJECTS, [TASKS[0], {**TASKS[0], "completed": True}])
    assert parsed["total_count"] == 1
    assert parsed["cards"][0]["completed"] is False


@pytest.mark.parametrize(
    ("board", "status"),
    [
        ("ایده ها و پیشنهاد", "idea"),
        ("پیشنهاد", "idea"),
        ("برای انجام", "todo"),
        ("تایید شده", "todo"),
        ("تأیید شده", "todo"),
        ("تایید (میان مدت)", "todo"),
        ("در حال انجام", "in_progress"),
        ("در حال بررسی", "review"),
        ("بررسی/تحلیل", "review"),
        ("انجام شده/منتظر بررسی", "review"),
        ("تایید مدیر مالی", "waiting_approval"),
        ("تاييد مدير مالي", "waiting_approval"),
        ("درخواست پرداخت", "waiting_payment"),
        ("پرداخت های چند بخشی/عودت", "waiting_payment"),
        ("پرداخت شده", "paid"),
        ("پرداخت\u200cشده", "paid"),
        ("ثبت نشده در Cost Tracking", "not_in_cost_tracking"),
        ("ثبت نشده در cost  tracking", "not_in_cost_tracking"),
        ("انجام شده/تکمیل شده", "done"),
        ("اتمام کمپین/تحلیل", "done"),
        ("کنسل", "cancelled"),
        ("كنسل شد", "cancelled"),
        ("قوانین و اطلاعیه ها", "info"),
        ("روش\u200cها", "info"),
        ("اعلام برندهای پرداختی", "info"),
        ("فروش", "other"),
        ("پلن کلی", "other"),
        ("توقف کوتاه مدت", "paused"),
        ("توقف", "paused"),
        ("", "other"),
        (None, "other"),
    ],
)
def test_board_title_maps_to_standard_status(board, status):
    assert board_status(board) == status


def test_arabic_letters_in_project_title_still_match():
    projects = {"projects": [{"_id": "p1", "title": "كمپين ها", "kanban_boards": [{"_id": "b1", "title": "كنسل"}]}]}
    parsed = read_cards(projects, [{"_id": "t", "title": "کارت", "project": "p1", "kanban_board": "b1"}])
    assert parsed["cards"][0]["status"] == "cancelled"
    assert parsed["open_count"] == 0


CAMPAIGN_PROJECTS = {
    "projects": [
        *PROJECTS["projects"],
        {"_id": "p-camp", "title": "کمپین ها", "kanban_boards": [{"_id": "b-end", "title": "اتمام کمپین/تحلیل"}]},
    ],
    "project_status": [],
}


def _fake(project_id: str, number: int, **extra) -> dict:
    return {
        "_id": f"{project_id}-{number}",
        "title": f"کارت ساختگی Z{number}",
        "project": project_id,
        "kanban_board": "b-end",
        "access_token": FAKE_TOKEN,
        **extra,
    }


def _mock(monkeypatch, handler) -> None:
    real_client = httpx.AsyncClient

    def factory(**kw):
        return real_client(transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(mizito.httpx, "AsyncClient", factory)


async def test_snapshot_reads_open_and_completed_pages_per_project(monkeypatch):
    calls = []
    open_camp = [_fake("p-camp", 0)]
    done_camp = [_fake("p-camp", n, completed=True, completed_at="2026-02-01T08:00:00.000Z") for n in range(1, 29)]
    done_camp[3] = {**open_camp[0], "completed": True}  # همان کارت باز دوباره در صفحهٔ تکمیل‌شده‌ها

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-token"] == FAKE_TOKEN
        body = json.loads(request.content or b"{}")
        calls.append((request.url.path, body.get("project_id"), body.get("from")))
        if request.url.path == "/api/projects/getList":
            return httpx.Response(200, json=CAMPAIGN_PROJECTS)
        assert request.url.path == "/api/tasks/upcoming"
        project_id = body["project_id"]
        if body.get("filter") is None:
            assert body["kanban"] is True
            return httpx.Response(200, json=open_camp if project_id == "p-camp" else TASKS[:3])
        assert body["filter"] == {"done_status": True, "completed": True}
        if project_id != "p-camp":
            return httpx.Response(200, json=[])
        start = body["from"]
        return httpx.Response(200, json=done_camp[start : start + 25])

    _mock(monkeypatch, handler)
    snap = await mizito.mizito_snapshot(FAKE_TOKEN)
    assert snap["connected"] is True
    assert ("/api/tasks/upcoming", "p-other", None) not in calls
    assert [call for call in calls if call[1] == "p-camp"] == [
        ("/api/tasks/upcoming", "p-camp", None),
        ("/api/tasks/upcoming", "p-camp", 0),
        ("/api/tasks/upcoming", "p-camp", 25),
    ]
    camp = [card for card in snap["cards"] if card["project"] == "کمپین ها"]
    assert len(camp) == 28
    assert len({card["id"] for card in camp}) == 28
    first = next(card for card in camp if card["id"] == "p-camp-0")
    assert first["completed"] is False
    assert sum(card["completed"] for card in camp) == 27
    assert all(card["status"] == "done" and not card["active"] for card in camp)
    assert snap["open_count"] == 2
    assert FAKE_TOKEN not in json.dumps(snap)


async def test_completed_pages_stop_at_the_cap(monkeypatch):
    monkeypatch.setattr(mizito, "_MAX_PAGES", 3)
    pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        if request.url.path == "/api/projects/getList":
            return httpx.Response(200, json={"projects": [CAMPAIGN_PROJECTS["projects"][-1]]})
        if body.get("filter") is None:
            return httpx.Response(200, json=[])
        pages.append(body["from"])
        return httpx.Response(200, json=[_fake("p-camp", 1000 + len(pages) * 25 + n) for n in range(25)])

    _mock(monkeypatch, handler)
    snap = await mizito.mizito_snapshot(FAKE_TOKEN)
    assert pages == [0, 25, 50]
    assert snap["total_count"] == 75


async def test_server_ignoring_from_does_not_loop(monkeypatch):
    pages = []
    same = [_fake("p-camp", n) for n in range(25)]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        if request.url.path == "/api/projects/getList":
            return httpx.Response(200, json={"projects": [CAMPAIGN_PROJECTS["projects"][-1]]})
        if body.get("filter") is None:
            return httpx.Response(200, json=[])
        pages.append(body["from"])
        return httpx.Response(200, json=same)

    _mock(monkeypatch, handler)
    snap = await mizito.mizito_snapshot(FAKE_TOKEN)
    assert pages == [0, 25]
    assert snap["total_count"] == 25


async def test_no_token_means_no_call():
    snap = await mizito.mizito_snapshot("")
    assert snap["connected"] is False
    assert snap["cards"] == []


async def test_old_snapshot_without_status_still_reads(db, seeded):
    from app.perf.models import PmIntegration

    old = {
        "connected": True,
        "reason": "",
        "projects": [{"title": "مالی و مارکتینگ", "id": "p1"}],
        "cards": [
            {"project": "مالی و مارکتینگ", "board": "درخواست پرداخت", "title": "شارژ X12", "code": "X12"},
            {"project": "مالی و مارکتینگ", "board": "پلن کلی", "title": "یادداشت", "code": ""},
        ],
        "open_count": 2,
    }
    db.add(PmIntegration(organization_id=seeded["org"].id, mizito_snapshot=json.dumps(old, ensure_ascii=False)))
    await db.commit()
    data = await saved_mizito(db, seeded["org"].id)
    assert [card["status"] for card in data["cards"]] == ["waiting_payment", "other"]
    assert all(card["active"] for card in data["cards"])
    assert data["open_count"] == 2
    assert data["total_count"] == 2
    assert data["read_at"] is None


def test_paused_board_is_not_active():
    projects = {
        "projects": [{"_id": "p1", "title": "کمپین ها", "kanban_boards": [{"_id": "b1", "title": "توقف کوتاه مدت"}]}]
    }
    card = read_cards(projects, [{"_id": "t", "title": "کارت", "project": "p1", "kanban_board": "b1"}])["cards"][0]
    assert card["status"] == "paused"
    assert card["active"] is False


def test_campaign_code_ignores_case_and_persian_digits():
    from app.perf.services.mizito import campaign_code, code_key

    assert campaign_code("شارژ پنل s۹۵") == "S95"
    assert campaign_code("کمپین fm٥٤-2 تست") == "FM54-2"
    assert campaign_code("بدون کد") == ""
    assert code_key(" fm۵۴ ") == "FM54"
    assert code_key("S 95") == "S95"


def test_missing_codes_skip_panel_codes_and_put_active_first():
    from app.perf.services.mizito import missing_codes

    cards = [
        {"code": "S95", "title": "در پنل هست", "active": True, "modified_at": "2026-03-01T00:00:00.000Z"},
        {
            "code": "Q7",
            "title": "قدیمی",
            "project": "کمپین ها",
            "status": "done",
            "active": False,
            "completed": True,
            "modified_at": "2026-01-01T00:00:00.000Z",
        },
        {
            "code": "Q7",
            "title": "تازه‌تر",
            "project": "کمپین ها",
            "status": "done",
            "active": False,
            "completed": True,
            "modified_at": "2026-02-01T00:00:00.000Z",
        },
        {
            "code": "X3",
            "title": "فعال",
            "project": "مالی و مارکتینگ",
            "status": "waiting_payment",
            "active": True,
            "modified_at": "2025-12-01T00:00:00.000Z",
        },
        {
            "code": "Z9",
            "title": "تکمیل‌شدهٔ تازه",
            "status": "done",
            "active": False,
            "completed": True,
            "modified_at": "2026-05-01T00:00:00.000Z",
        },
        {"code": "", "title": "بی‌کد", "active": True},
    ]
    found = missing_codes(cards, ["s۹۵", "FM54"])
    assert [row["code"] for row in found] == ["X3", "Z9", "Q7"]
    q7 = found[2]
    assert q7["cards"] == 2
    assert q7["title"] == "تازه‌تر"
    assert q7["completed"] is True
    assert q7["active"] is False
    assert found[0]["status"] == "waiting_payment"


async def test_missing_codes_endpoint_reads_only_the_saved_list(client, seeded, db):
    from app.perf.models import PmCampaign, PmIntegration
    from tests.conftest import auth, login
    from tests.test_perf import _nadia

    await _nadia(db, seeded)
    org = seeded["org"].id
    db.add(PmCampaign(organization_id=org, code="S95", title="کمپین ساختگی"))
    snapshot = {
        "connected": True,
        "reason": "",
        "projects": [],
        "cards": [
            {"project": "کمپین ها", "board": "اتمام کمپین/تحلیل", "title": "کارت s95", "code": "s95"},
            {"project": "کمپین ها", "board": "در حال انجام", "title": "کارت Q7", "code": "Q7"},
        ],
        "open_count": 1,
    }
    db.add(
        PmIntegration(
            organization_id=org, mizito_token=FAKE_TOKEN, mizito_snapshot=json.dumps(snapshot, ensure_ascii=False)
        )
    )
    await db.commit()
    token = await login(client, "nadia-test@autoco.example")
    page = await client.get("/perf/integrations/mizito/missing", headers=auth(token))
    assert page.status_code == 200
    body = page.json()
    assert [row["code"] for row in body["codes"]] == ["Q7"]
    assert body["codes"][0]["status"] == "in_progress"
    assert FAKE_TOKEN not in page.text
    viewer = await login(client, "viewer@autoco.example")
    denied = await client.get("/perf/integrations/mizito/missing", headers=auth(viewer))
    assert denied.status_code == 403


def test_code_can_come_from_notes_without_keeping_the_notes():
    task = {
        "_id": "t-n",
        "title": "پرداخت بدون کد",
        "notes": "یادداشت ساختگی برای کمپین k۴۲",
        "project": "p-money",
        "kanban_board": "b-paid",
    }
    card = read_cards(PROJECTS, [task])["cards"][0]
    assert card["code"] == "K42"
    assert card["code_source"] == "notes"
    assert "یادداشت ساختگی" not in json.dumps(card, ensure_ascii=False)
    assert read_cards(PROJECTS, TASKS)["cards"][0]["code_source"] == "title"


FINANCE = "مالی و مارکتینگ"


def _money_card(card_id, status, code="", completed=False, modified="2026-03-01T00:00:00.000Z", **extra):
    return {
        "id": card_id,
        "project": FINANCE,
        "title": f"کارت {card_id}",
        "status": status,
        "code": code,
        "completed": completed,
        "modified_at": modified,
        **extra,
    }


def test_finance_view_groups_and_suggests_matches_by_code_only():
    from app.perf.services.mizito_finance import finance_view

    cards = [
        _money_card("a", "not_in_cost_tracking", "S95"),
        _money_card("b", "not_in_cost_tracking", completed=True),
        _money_card("c", "paid", "Q7", completed=True, modified="2026-01-01T00:00:00.000Z"),
        _money_card("d", "paid", "", modified="2026-04-01T00:00:00.000Z"),
        _money_card("e", "paid", "s95"),
        _money_card("f", "waiting_payment"),
        _money_card("g", "waiting_approval"),
        {"id": "h", "project": "پرفورمنس مارکتینگ", "title": "بیرون", "status": "paid", "code": "Q8"},
        {"id": "i", "project": FINANCE, "title": "عکس قدیمی", "board": "پرداخت شده", "code": "Q9"},
        "junk",
    ]
    view = finance_view(cards, [("S95", 12), ("s۹۵", 14), ("", 3), ("Z1", 20, 5000, "پیامک", "بدون کارت"), ("Q8", 21, 8000, "سوشال", "فقط در پرفورمنس")])
    assert view["match_basis"] == "code"
    assert view["counts"]["not_in_cost_tracking"] == {"total": 2, "open": 1}
    assert view["counts"]["paid"] == {"total": 4, "open": 3}
    assert view["counts"]["waiting_payment"]["total"] == 1
    assert view["counts"]["waiting_approval"]["total"] == 1
    assert [row["id"] for row in view["to_register"]] == ["a"]
    assert view["to_register"][0]["match"] == "suggested"
    assert view["to_register"][0]["suggested_costs"] == [12, 14]
    assert view["paid_suggested_count"] == 1
    assert [row["id"] for row in view["paid_without_cost"]] == ["c", "i", "d"]
    assert [row["match"] for row in view["paid_without_cost"]] == ["no_cost_row", "no_cost_row", "no_code"]
    assert view["paid_without_cost_count"] == 3
    assert view["panel_without_card_count"] == 1
    assert view["panel_without_card"][0]["campaign_code"] == "Q8"
    assert view["panel_without_card"][0]["cost_number"] == 21
    assert view["panel_without_card"][0]["amount_toman"] == 8000


async def test_finance_endpoint_is_read_only_and_safe_with_old_snapshots(client, seeded, db):
    from app.perf.models import PmCost, PmIntegration
    from tests.conftest import auth, login
    from tests.test_perf import _nadia

    await _nadia(db, seeded)
    token = await login(client, "nadia-test@autoco.example")
    empty = await client.get("/perf/integrations/mizito/finance", headers=auth(token))
    assert empty.status_code == 200
    assert empty.json()["counts"]["paid"] == {"total": 0, "open": 0}
    assert empty.json()["to_register"] == []

    org = seeded["org"].id
    db.add(PmCost(organization_id=org, cost_number=12, amount_toman=1_000_000, campaign_code="S95"))
    old = {
        "connected": True,
        "reason": "",
        "projects": [],
        "cards": [
            {"project": FINANCE, "board": "ثبت نشده در Cost Tracking", "title": "واریز ساختگی S95", "code": "S95"},
            {"project": FINANCE, "board": "پرداخت شده", "title": "پرداخت ساختگی Q7", "code": "Q7"},
            "junk",
        ],
        "open_count": 2,
    }
    db.add(
        PmIntegration(organization_id=org, mizito_token=FAKE_TOKEN, mizito_snapshot=json.dumps(old, ensure_ascii=False))
    )
    await db.commit()
    page = await client.get("/perf/integrations/mizito/finance", headers=auth(token))
    assert page.status_code == 200
    body = page.json()
    assert body["to_register"][0]["suggested_costs"] == [12]
    assert body["paid_without_cost"][0]["code"] == "Q7"
    assert body["counts"]["paid"]["total"] == 1
    assert FAKE_TOKEN not in page.text
    viewer = await login(client, "viewer@autoco.example")
    denied = await client.get("/perf/integrations/mizito/finance", headers=auth(viewer))
    assert denied.status_code == 403


TRIAGE_NOW = datetime(2026, 10, 6, 7, 0, tzinfo=UTC)


def _ago(days: int) -> str:
    return (TRIAGE_NOW - timedelta(days=days, hours=1)).isoformat().replace("+00:00", "Z")


def _triage_card(card_id, project="پرفورمنس مارکتینگ", **extra):
    base = {
        "id": card_id,
        "project": project,
        "board": "برای انجام",
        "title": f"کارت {card_id}",
        "status": "todo",
        "active": True,
        "completed": False,
        "code": "S1",
        "assignees": ["u-1"],
        "modified_at": _ago(1),
    }
    return {**base, **extra}


def test_triage_flags_and_order():
    from app.perf.services.mizito_triage import triage_view

    cards = [
        _triage_card("a", code="", modified_at=_ago(30), assignees=[], deadline=_ago(2)),
        _triage_card("b", project="کمپین ها", modified_at=_ago(20)),
        _triage_card("c", project="مالی و مارکتینگ", code="", status="waiting_payment"),
        _triage_card("d", modified_at=_ago(2), assignees=[]),
        _triage_card("e", code="", completed=True, active=False),
        _triage_card("f", code="", status="paused", active=False),
        _triage_card("g", code="", status="done", active=False),
        _triage_card("h", modified_at=_ago(40), deadline=(TRIAGE_NOW + timedelta(days=3)).isoformat()),
        {"project": "پرفورمنس مارکتینگ", "board": "برای انجام", "title": "عکس قدیمی", "code": ""},
        "junk",
    ]
    view = triage_view(cards, 14, TRIAGE_NOW)
    assert view["checked"] == 6
    assert [row["title"] for row in view["cards"]] == ["کارت a", "کارت h", "کارت b", "کارت d", "عکس قدیمی"]
    assert view["cards"][0]["flags"] == ["no_code", "stuck", "no_assignee", "overdue"]
    assert view["cards"][0]["days_since_change"] == 30
    assert view["cards"][-1]["flags"] == ["no_code"]
    assert view["cards"][-1]["days_since_change"] is None
    assert view["counts"] == {"no_code": 2, "stuck": 3, "no_assignee": 2, "overdue": 1}
    assert view["total"] == 5
    assert [row["title"] for row in triage_view(cards, 25, TRIAGE_NOW)["cards"]][:3] == ["کارت a", "کارت h", "کارت d"]


def test_triage_days_are_clamped():
    from app.perf.services.mizito_triage import clamp_days, triage_view

    assert clamp_days(0) == 1
    assert clamp_days(-5) == 1
    assert clamp_days(999) == 365
    assert clamp_days("x") == 14
    assert clamp_days(None) == 14
    assert triage_view([], 0, TRIAGE_NOW)["days"] == 1


async def test_triage_endpoint_reads_saved_list_only(client, seeded, db, monkeypatch):
    from app.core.config import get_settings
    from app.perf.models import PmIntegration
    from tests.conftest import auth, login
    from tests.test_perf import _nadia

    await _nadia(db, seeded)
    token = await login(client, "nadia-test@autoco.example")
    empty = await client.get("/perf/integrations/mizito/triage", headers=auth(token))
    assert empty.status_code == 200
    assert empty.json()["cards"] == []
    assert empty.json()["days"] == 14

    old = {
        "connected": True,
        "reason": "",
        "projects": [],
        "cards": [{"project": "کمپین ها", "board": "در حال انجام", "title": "بی‌کد ساختگی", "code": ""}, "junk"],
        "open_count": 1,
    }
    db.add(
        PmIntegration(
            organization_id=seeded["org"].id,
            mizito_token=FAKE_TOKEN,
            mizito_snapshot=json.dumps(old, ensure_ascii=False),
        )
    )
    await db.commit()
    page = await client.get("/perf/integrations/mizito/triage?days=500", headers=auth(token))
    assert page.status_code == 200
    body = page.json()
    assert body["days"] == 365
    assert body["cards"][0]["flags"] == ["no_code"]
    assert body["counts"]["no_code"] == 1
    assert FAKE_TOKEN not in page.text

    monkeypatch.setenv("PERF_MIZITO_STUCK_DAYS", "3")
    get_settings.cache_clear()
    assert (await client.get("/perf/integrations/mizito/triage", headers=auth(token))).json()["days"] == 3
    viewer = await login(client, "viewer@autoco.example")
    denied = await client.get("/perf/integrations/mizito/triage", headers=auth(viewer))
    assert denied.status_code == 403


def test_checklist_items_are_capped_truncated_and_optional():
    long_title = "م" * 200
    items = [{"_id": f"c{n}", "title": long_title if n == 0 else f"قدم {n}", "checked": n % 2 == 0} for n in range(35)]
    task = {**TASKS[0], "checklist": [*items, "junk"]}
    card = read_cards(PROJECTS, [task])["cards"][0]
    assert card["checklist_total"] == 35
    assert len(card["checklist_items"]) == 30
    assert card["checklist_items"][0] == {"id": "c0", "title": "م" * 120, "checked": True}
    assert card["checklist_items"][1] == {"id": "c1", "title": "قدم 1", "checked": False}
    assert set(card["checklist_items"][0]) == {"id", "title", "checked"}
    bare = read_cards(PROJECTS, [{"_id": "t-x", "title": "بی‌چک‌لیست", "project": "p-money", "kanban_board": "b-ask"}])
    assert bare["cards"][0]["checklist_items"] == []
    odd = read_cards(PROJECTS, [{**TASKS[0], "checklist": [{"_id": "c", "checked": True}]}])
    assert odd["cards"][0]["checklist_items"] == [{"id": "c", "title": "", "checked": True}]


def test_missing_codes_carry_the_newest_card_id():
    from app.perf.services.mizito import missing_codes

    cards = [
        {"id": "old", "code": "Q7", "title": "قدیمی", "modified_at": "2026-01-01T00:00:00.000Z"},
        {"id": "new", "code": "Q7", "title": "تازه", "modified_at": "2026-02-01T00:00:00.000Z"},
    ]
    assert missing_codes(cards, [])[0]["id"] == "new"


async def test_card_link_needs_a_valid_workspace_id(db, seeded, monkeypatch):
    from app.core.config import get_settings
    from app.perf.services.mizito import card_url_prefix

    assert card_url_prefix() == ""
    assert (await saved_mizito(db, seeded["org"].id))["card_url_prefix"] == ""
    monkeypatch.setenv("PERF_MIZITO_WORKSPACE_ID", "abc123")
    get_settings.cache_clear()
    assert card_url_prefix() == "https://office.mizito.ir/#/ws/tasks/inbox/abc123_"
    assert (await saved_mizito(db, seeded["org"].id))["card_url_prefix"].endswith("/abc123_")
    monkeypatch.setenv("PERF_MIZITO_WORKSPACE_ID", "x/../y")
    get_settings.cache_clear()
    assert card_url_prefix() == ""
