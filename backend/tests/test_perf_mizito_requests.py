"""درخواست‌های تبلیغ میزیتو → پیش‌نویس کمپین. همهٔ متن‌ها، شناسه‌ها و برندها ساختگی‌اند؛ هیچ تماس واقعی زده نمی‌شود."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.perf.services import mizito_requests as mr
from app.perf.services.common import PerfError
from app.perf.services.mizito import ALLOWED_ENDPOINTS, mizito_post

FAKE_TOKEN = "fake-jwt-not-a-real-token"
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)

CONFIG = mr.RequestConfig(
    dialogs=("گروه تست پروژه", "گروه تست بخشنامه"),
    task_boards={"b-circ": "circular", "b-sms": "sms"},
    requester_ids=frozenset({"u-asker"}),
    ignore_ids=frozenset({"u-bot"}),
    brands=(
        mr.Brand(tag="Z", name="زیبا خودرو", patterns=("زیبا خودرو", "زیبا")),
        mr.Brand(tag="Q", name="کوشا موتور", patterns=("کوشا موتور", "kosha", "کوشا")),
    ),
    car_models=("آلفا ۷",),
    branches=("مرکزی",),
    lookback_days=7,
)


def _when(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def _report(index: int, comment: str, *, title: str = "تبلیغات زیبا خودرو", author: str = "u-asker", days: float = 1):
    return {
        "_id": f"m{index}",
        "_": "message",
        "from": author,
        "date": _when(days),
        "dialog": "d-proj",
        "msg_index": index,
        "deleted": False,
        "message": "",
        "mention": ["u-someone"],
        "media": {
            "_": "messageMediaTask",
            "task": {
                "_id": "t-brand",
                "title": title,
                "notes": "کمپین زیبا از 28 شهریور (Z12)",
                "access_token": "card-access-token-never-stored",
            },
            "changes": {"from": {"user_comment": ""}, "to": {"user_comment": comment, "user_comment_id": "c1"}},
        },
    }


def _text(index: int, text: str, *, days: float = 1, kind: str = "message"):
    return {"_id": f"x{index}", "_": kind, "from": "u-sales", "date": _when(days), "msg_index": index, "message": text}


# ---------------------------------------------------------------- فهرست مجاز


def test_allowed_endpoints_are_only_the_read_calls():
    assert ALLOWED_ENDPOINTS == {
        "projects/getList",
        "tasks/getAll",
        "tasks/upcoming",
        "chat/getDialogs",
        "chat/getHistory",
    }


@pytest.mark.parametrize(
    "path",
    [
        "chat/seen",
        "chat/getChatView",
        "tasks/get",
        "tasks/getComments",
        "inbox/getHistory",
        "inbox/seen",
        "dashboard/notifySeen",
        "chat/setTyping",
        "labels/sendUsage",
        "monitor/ping",
        "tasks/add",
        "chat/sendMessage",
        "chat/getHistory/../seen",
        "",
    ],
)
async def test_any_other_endpoint_is_refused_before_the_network(path):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PerfError):
            await mizito_post(client, "https://mizito.example", path, {"x-token": FAKE_TOKEN}, {})
        reader = mr.Reader(client, "https://mizito.example", FAKE_TOKEN)
        with pytest.raises(PerfError):
            await reader.call(path, {})
    assert calls == []


# ---------------------------------------------------------------- متن و استخراج


def test_clean_text_normalises_digits_letters_and_spaces():
    assert mr.clean_text("كمپين  ۱۲\u200cتايي ٣٤") == "کمپین 12 تایی 34"
    assert mr.fold("ID.۴ Kosha") == "id.4 kosha"


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("لطفا تبلیغات برای این خودرو انجام شود", "start"),
        ("حجم تبلیغات بیشتر شود و بلاگر هم اضافه شود", "start"),
        ("با توجه به اتمام شرایط فروش تبلیغات متوقف شود", "stop"),
        ("تمام تبلیغات‌ها كنسل شود", "stop"),
        ("عدم تبلیغ محصولات این برند تا اطلاع ثانوی", "stop"),
        ("جلسه ساعت ۱۰ برگزار می‌شود", "info"),
    ],
)
def test_classify(text, kind):
    assert mr.classify(text) == kind


def test_execution_reports_are_recognised():
    assert mr.looks_like_execution_report("پیامک به ۱۲۰۰ نفر ارسال شد")
    assert mr.looks_like_execution_report("گزارش اجرای کمپین")
    assert not mr.looks_like_execution_report("تبلیغات انجام شود")


def test_extract_reads_brand_cars_offer_channels_branch_dates_and_code():
    text = (
        "خودروهای آلفا ۷ و ZX-300 از هفته آینده باز می‌شود؛ تبلیغات بدون قیمت باشد و تحویل ۴۵ روزه. "
        "پیش پرداخت ۳۰۰ میلیون تومان، قیمت نهایی 2.6 میلیارد. پیامک و استوری و بلاگر، شعبه مرکزی، "
        "از ۲۸ شهریور و 1405/07/10."
    )
    fields = mr.extract(text, title="تبلیغات زیبا خودرو", notes="کمپین زیبا (Z12)", config=CONFIG)
    assert fields["intent"] == "start"
    assert (fields["brand"], fields["tag"]) == ("زیبا خودرو", "Z")
    assert fields["cars"][:2] == ["آلفا ۷", "ZX-300"]
    assert "Z12" not in fields["cars"]
    offer = fields["offer"]
    assert offer["no_price"] is True
    assert offer["delivery_days"] == 45
    assert offer["prepayment"].startswith("300 میلیون")
    assert "2.6 میلیارد" in offer["prices"]
    assert fields["channels"] == ["sms", "ig_story", "influencer"]
    assert fields["branches"] == ["مرکزی"]
    assert "28 شهریور" in fields["dates"] and "1405/07/10" in fields["dates"] and "هفته آینده" in fields["dates"]
    assert fields["code"] == "Z12"
    assert fields["card_title"] == "تبلیغات زیبا خودرو"


def test_longer_car_names_win_over_their_parts():
    models = ("آلفا", "آلفا پلاس", "بتا X2")
    assert mr.find_cars("فروش آلفا پلاس و بتا X2 و Q9", "", models) == ["آلفا پلاس", "بتا X2", "Q9"]
    assert mr.find_cars("فروش آلفا", "", models) == ["آلفا"]


def test_branch_words_skip_common_words():
    assert mr.find_branches("شعبه پیش از این گفته شد", ()) == []
    assert mr.find_branches("در شعبه شرقی", ()) == ["شرقی"]


def test_brand_falls_back_to_the_card_title_and_text():
    assert mr.find_brand("متن", "تبلیغات برند ناشناس نو", CONFIG.brands) == ("ناشناس نو", "")
    assert mr.find_brand("لطفا برای kosha تبلیغ شود", "", CONFIG.brands) == ("کوشا موتور", "Q")
    assert mr.find_brand("زیبایی", "", CONFIG.brands) == ("", "")


def test_only_the_campaign_code_is_taken_from_notes():
    assert mr.extract_code("کمپین زیبا خودروهای آلفا از ۲۸ شهریور (Z12)") == "Z12"
    assert mr.extract_code("کمپین z7") == "Z7"
    assert mr.extract_code("یادداشت بدون کد") == ""


def test_suggestion_maps_channels_to_panel_channels():
    fields = mr.extract("تبلیغ آلفا ۷ با پیامک و پیج", title="تبلیغات زیبا خودرو", config=CONFIG)
    hint = mr.suggest(fields, "start")
    assert hint == {
        "title": "کمپین زیبا خودرو آلفا ۷",
        "tag": "Z",
        "brand": "زیبا خودرو",
        "channels": ["sms", "ig_story"],
    }
    assert mr.suggest({}, "sms")["channels"] == ["sms"]
    assert mr.suggest({"cars": ["ZX-300"]}, "circular")["title"] == "مینی کمپین بخشنامه ZX-300"


# ---------------------------------------------------------------- تشخیص از پیام


DIALOG = {"_id": "d-proj", "title": "گروه تست پروژه", "is_project_group": True}
CIRCULAR = {"_id": "d-circ", "title": "گروه تست بخشنامه", "is_group": True}


def test_report_on_brand_card_becomes_a_request_without_secrets():
    found = mr.message_candidate(_report(5, "لطفا تبلیغات آلفا ۷ انجام شود"), DIALOG, "cards", CONFIG)
    assert found is not None
    assert (found.kind, found.source_key, found.msg_index) == ("start", "dialog:d-proj:5", 5)
    assert "access_token" not in repr(found) and "card-access-token" not in repr(found)
    assert "u-someone" not in repr(found)


def test_stop_report_and_new_brand_card():
    stop = mr.message_candidate(_report(6, "تبلیغات زیبا متوقف شود"), DIALOG, "cards", CONFIG)
    assert stop is not None and stop.kind == "stop"
    new_card = _report(7, "")
    new_card["media"].pop("changes")
    created = mr.message_candidate(new_card, DIALOG, "cards", CONFIG)
    assert created is not None and created.kind == "start" and created.text == "تبلیغات زیبا خودرو"


def test_messages_that_are_not_requests_are_skipped():
    skip = [
        _report(1, "پیامک به ۵۰۰ نفر ارسال شد", author="u-perf"),  # گزارش اجرا
        _report(2, "تبلیغات انجام شود", title="کارت داخلی", author="u-other"),  # کارت برند نیست
        _report(3, "تبلیغات انجام شود", author="u-bot"),  # فرستندهٔ نادیده
        _report(4, "سلام، دیدم"),  # اطلاع
        {**_report(8, "تبلیغات انجام شود"), "deleted": True},
        _text(9, "پیام متنی معمولی در گروه پروژه که کارت ندارد"),
    ]
    assert [mr.message_candidate(item, DIALOG, "cards", CONFIG) for item in skip] == [None] * len(skip)
    asked = mr.message_candidate(_report(10, "تبلیغات انجام شود", title="کارت داخلی"), DIALOG, "cards", CONFIG)
    assert asked is not None  # از فرستندهٔ تعریف‌شده، حتی روی کارت غیر برند


def test_circular_group_text_messages():
    found = mr.message_candidate(_text(3, "فروش آلفا ۷ با تحویل ۳۰ روزه از فردا آغاز می‌شود"), CIRCULAR, "texts", CONFIG)
    assert found is not None and found.kind == "circular"
    assert mr.message_candidate(_text(4, "باشه"), CIRCULAR, "texts", CONFIG) is None
    assert (
        mr.message_candidate(_text(5, "کاربر به گروه اضافه شد", kind="messageService"), CIRCULAR, "texts", CONFIG)
        is None
    )


def test_dialog_roles_come_from_the_setting_or_the_dialog_type():
    dialogs = [
        {"_id": "d1", "title": "گروه تست پروژه", "is_project_group": True},
        {"_id": "d2", "title": "گروه تست بخشنامه", "is_project_group": True, "project_entity": "p2"},
        {"_id": "d3", "title": "گروه تست ساده", "is_group": True},
        {"_id": "d4", "title": "گروه نامربوط"},
    ]
    roles = mr.tracked(dialogs, ["گروه تست پروژه", "گروه تست بخشنامه=texts", "گروه تست ساده"])
    assert [(dialog["_id"], role) for dialog, role in roles] == [("d1", "cards"), ("d2", "texts"), ("d3", "texts")]
    text = _text(1, "فروش آلفا ۷ با تحویل ۳۰ روزه از فردا آغاز می‌شود")
    assert mr.message_candidate(text, dialogs[0], "cards", CONFIG) is None
    both = mr.message_candidate(text, dialogs[0], "both", CONFIG)
    assert both is not None and both.kind == "circular"
    assert mr.message_candidate(_report(2, "تبلیغات انجام شود"), dialogs[1], "texts", CONFIG) is None


def _task(task_id: str, board: str, *, created: float, comment: float | None = None, text: str = "برنامه فروش"):
    row = {
        "_id": task_id,
        "title": "فروش آلفا ۷",
        "kanban_board": board,
        "created_at": _when(created),
        "owner": "u-sales",
        "notes": "زمان ارسال پیامک: ۵ مهر",
        "access_token": "card-access-token-never-stored",
    }
    if comment is not None:
        row["last_comment"] = {"comment": text, "comment_at": _when(comment), "comment_owner": "u-sales"}
    return row


def test_task_diff_uses_board_config_and_time():
    since = NOW - timedelta(days=2)
    fresh = mr.task_candidate(_task("t1", "b-circ", created=1), CONFIG, since)
    assert fresh is not None and fresh.kind == "circular" and fresh.source_kind == "task"
    commented = mr.task_candidate(_task("t2", "b-sms", created=30, comment=0.5, text="متن پیامک ساختگی"), CONFIG, since)
    assert commented is not None and commented.kind == "sms" and "متن پیامک ساختگی" in commented.text
    assert "card-access-token" not in repr(commented)
    assert mr.task_candidate(_task("t3", "b-circ", created=10), CONFIG, since) is None  # قدیمی
    assert mr.task_candidate(_task("t4", "b-other", created=1), CONFIG, since) is None  # برد دیگر


# ---------------------------------------------------------------- نشانه‌ها و صفحه‌ها


def _history(newest: int, count: int, *, step_days: float = 0.5, project: bool = True) -> list[dict]:
    rows = []
    for index in range(newest, newest - count, -1):
        days = (newest - index) * step_days
        if project:
            rows.append(_report(index, f"تبلیغات آلفا ۷ شماره {index} انجام شود", days=days))
        else:
            rows.append(_text(index, f"بخشنامه فروش شماره {index} با تحویل ۳۰ روزه", days=days))
    return rows


class FakeMizito:
    def __init__(self, dialogs, histories, tasks=None):
        self.dialogs = dialogs
        self.histories = histories  # dialog id → همهٔ پیام‌ها، جدید به قدیم
        self.tasks = tasks or []
        self.calls: list[tuple[str, dict]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        import json

        path = request.url.path.removeprefix("/api/")
        body = json.loads(request.content or b"{}")
        assert request.headers["x-token"] == FAKE_TOKEN
        self.calls.append((path, body))
        if path == "chat/getDialogs":
            return httpx.Response(200, json={"dialogs": self.dialogs, "pin_dialogs": []})
        if path == "chat/getHistory":
            rows = self.histories.get(body["dialog"], [])
            return httpx.Response(200, json=rows[body["offset"] : body["offset"] + 15])
        if path == "tasks/getAll":
            return httpx.Response(200, json=self.tasks)
        return httpx.Response(500)

    def paths(self):
        return [path for path, _ in self.calls]


async def _collect(fake, positions=None, stamps=None, config=CONFIG):
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as client:
        reader = mr.Reader(client, "https://mizito.example", FAKE_TOKEN)
        return await mr.collect(reader, positions or {}, stamps or {}, config, NOW)


def _dialogs(total: int, unread: int = 0):
    return [
        {**DIALOG, "messages_count": total, "unread_count": unread, "members": ["u-a", "u-b"]},
        {**CIRCULAR, "messages_count": 0, "unread_count": 0},
        {"_id": "d-other", "title": "گروه نامربوط", "messages_count": 50, "unread_count": 0},
    ]


async def test_first_run_looks_back_only_the_window_and_sets_cursors():
    fake = FakeMizito(_dialogs(40), {"d-proj": _history(40, 40)}, tasks=[_task("t1", "b-circ", created=3)])
    found = await _collect(fake)
    indexes = sorted(item.msg_index for item in found.candidates if item.source_kind == "dialog")
    assert indexes == list(range(26, 41))  # نیم‌روز فاصله → فقط ۷ روز اخیر
    assert found.positions["dialog:d-proj"] == 40
    assert "dialog:d-other" not in found.positions
    assert [item.source_id for item in found.candidates if item.source_kind == "task"] == ["t1"]
    assert set(fake.paths()) <= ALLOWED_ENDPOINTS
    assert all(body.get("dialog") != "d-other" for _, body in fake.calls)


async def test_first_run_with_no_lookback_only_marks_cursors():
    config = mr.RequestConfig(**{**CONFIG.__dict__, "lookback_days": 0})
    fake = FakeMizito(_dialogs(40), {"d-proj": _history(40, 40)}, tasks=[_task("t1", "b-circ", created=0.1)])
    found = await _collect(fake, config=config)
    assert found.candidates == []
    assert found.positions["dialog:d-proj"] == 40
    assert found.stamps["tasks"] == NOW
    assert "chat/getHistory" not in fake.paths()


async def test_next_run_reads_only_new_messages_and_stops_at_the_cursor():
    fake = FakeMizito(_dialogs(60), {"d-proj": _history(60, 60, step_days=0.01)})
    found = await _collect(fake, positions={"dialog:d-proj": 41, "dialog:d-circ": 0})
    assert sorted(item.msg_index for item in found.candidates) == list(range(42, 61))
    assert found.positions["dialog:d-proj"] == 60
    offsets = [body["offset"] for path, body in fake.calls if path == "chat/getHistory"]
    assert offsets == [0, 15]


async def test_nothing_new_means_no_history_call():
    fake = FakeMizito(_dialogs(60), {"d-proj": _history(60, 60)})
    found = await _collect(fake, positions={"dialog:d-proj": 60, "dialog:d-circ": 0})
    assert found.candidates == [] and "chat/getHistory" not in fake.paths()


async def test_reading_starts_after_unread_messages_and_never_passes_them():
    fake = FakeMizito(_dialogs(60, unread=5), {"d-proj": _history(60, 60, step_days=0.01)})
    found = await _collect(fake, positions={"dialog:d-proj": 50, "dialog:d-circ": 0})
    offsets = [body["offset"] for path, body in fake.calls if path == "chat/getHistory"]
    assert offsets[0] == 5
    assert sorted(item.msg_index for item in found.candidates) == list(range(51, 56))
    assert found.positions["dialog:d-proj"] == 55  # پیام‌های خوانده‌نشده دفعهٔ بعد خوانده می‌شوند


async def test_unread_can_be_ignored_by_setting():
    config = mr.RequestConfig(**{**CONFIG.__dict__, "respect_unread": False})
    fake = FakeMizito(_dialogs(60, unread=5), {"d-proj": _history(60, 60, step_days=0.01)})
    await _collect(fake, positions={"dialog:d-proj": 58, "dialog:d-circ": 0}, config=config)
    assert [body["offset"] for path, body in fake.calls if path == "chat/getHistory"] == [0]


async def test_history_pages_are_capped():
    config = mr.RequestConfig(**{**CONFIG.__dict__, "max_pages": 2})
    fake = FakeMizito(_dialogs(200), {"d-proj": _history(200, 200, step_days=0.001)})
    found = await _collect(fake, positions={"dialog:d-proj": 1, "dialog:d-circ": 0}, config=config)
    assert fake.paths().count("chat/getHistory") == 2
    assert len(found.candidates) == 30


# ---------------------------------------------------------------- پایگاه داده و API


def _use_fake(monkeypatch, fake, config=CONFIG):
    real = httpx.AsyncClient
    monkeypatch.setattr(mr, "_client", lambda: real(transport=httpx.MockTransport(fake.handler)))
    monkeypatch.setattr(mr.RequestConfig, "from_settings", classmethod(lambda cls: config))


async def _token(db, org):
    from app.perf.models import PmIntegration

    db.add(PmIntegration(organization_id=org, mizito_token=FAKE_TOKEN))
    await db.commit()


async def test_check_stores_drafts_once_and_marks_repeats(db, seeded, monkeypatch):
    from sqlalchemy import select

    from app.perf.models import PmMizitoCursor, PmMizitoRequest

    org = seeded["org"].id
    await _token(db, org)
    history = _history(20, 3, step_days=0.1)
    history.append(_report(17, "تبلیغات آلفا ۷ شماره 20 انجام شود", days=0.5))  # همان متن پیام 20
    fake = FakeMizito(_dialogs(20), {"d-proj": history})
    _use_fake(monkeypatch, fake)
    first = await mr.check_requests(db, org, now=NOW)
    assert first["checked"] is True and first["added"] == 4
    again = await mr.check_requests(db, org, now=NOW)
    assert again["added"] == 0
    rows = (await db.scalars(select(PmMizitoRequest).where(PmMizitoRequest.organization_id == org))).all()
    assert len(rows) == 4
    statuses = {row.msg_index: row.status for row in rows}
    assert statuses[17] == "new" and statuses[20] == "duplicate"
    assert all(len(row.excerpt) <= mr.EXCERPT_CHARS for row in rows)
    assert all("card-access-token" not in row.fields + row.excerpt for row in rows)
    cursors = (await db.scalars(select(PmMizitoCursor).where(PmMizitoCursor.organization_id == org))).all()
    assert {row.source_key: row.position for row in cursors}["dialog:d-proj"] == 20


async def test_check_without_token_calls_nothing(db, seeded, monkeypatch):
    fake = FakeMizito(_dialogs(20), {})
    _use_fake(monkeypatch, fake)
    result = await mr.check_requests(db, seeded["org"].id, now=NOW)
    assert result["checked"] is False and fake.calls == []


async def _reader_user(db, seeded):
    from app.core.permissions import PermissionCode
    from app.services import OrgService

    svc = OrgService(db)
    role = await svc.create_role(
        seeded["org"].id, "فقط دیدن", "perf_reader", [PermissionCode.PERF_READ], "organization"
    )
    await svc.create_user(
        organization_id=seeded["org"].id,
        email="reader-test@autoco.example",
        full_name="کاربر ساختگی",
        password="password",
        role_id=role.id,
        branch_id=seeded["branch"].id,
    )
    await db.commit()


async def _seed_requests(db, org):
    long_text = "لطفا تبلیغات آلفا ۷ بدون قیمت و تحویل ۳۰ روز انجام شود. " + "توضیح بیشتر " * 60
    items = [
        mr.Candidate(
            "dialog:d-proj:1",
            "dialog",
            "d-proj",
            "گروه تست پروژه",
            "start",
            long_text,
            title="تبلیغات زیبا خودرو",
            msg_index=1,
            happened_at=NOW,
        ),
        mr.Candidate(
            "dialog:d-proj:2",
            "dialog",
            "d-proj",
            "گروه تست پروژه",
            "stop",
            "تبلیغات زیبا متوقف شود",
            title="تبلیغات زیبا خودرو",
            notes="کمپین (S7)",
            msg_index=2,
            happened_at=NOW,
        ),
        mr.Candidate(
            "task:t1:x",
            "task",
            "t1",
            "کال سنتر",
            "circular",
            "فروش ZX-300 از فردا",
            title="فروش ZX-300",
            happened_at=NOW,
        ),
    ]
    assert await mr.save_candidates(db, org, items, CONFIG) == 3
    await db.commit()


async def test_request_endpoints_and_permissions(client, seeded, db, monkeypatch):
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.perf.campaign_register import next_code
    from app.perf.models import PmCampaign, PmMizitoRequest
    from tests.conftest import auth, login
    from tests.test_perf import _nadia

    settings = get_settings()
    assert not settings.perf_sheets_spreadsheet_id and not settings.perf_sheets_webhook  # گوگل شیت در تست خاموش است
    await _nadia(db, seeded)
    await _reader_user(db, seeded)
    org = seeded["org"].id
    db.add(PmCampaign(organization_id=org, code="S7", title="کمپین ساختگی در حال اجرا"))
    await db.commit()
    await _seed_requests(db, org)
    fake = FakeMizito(_dialogs(0), {})
    _use_fake(monkeypatch, fake)

    viewer = await login(client, "viewer@autoco.example")
    assert (await client.get("/perf/integrations/mizito/requests", headers=auth(viewer))).status_code == 403
    assert (await client.post("/perf/integrations/mizito/requests/check", headers=auth(viewer))).status_code == 403

    reader = await login(client, "reader-test@autoco.example")
    listed = await client.get("/perf/integrations/mizito/requests", headers=auth(reader))
    assert listed.status_code == 200
    body = listed.json()
    assert body["counts"]["new"] == 3 and len(body["requests"]) == 3
    by_kind = {row["kind"]: row for row in body["requests"]}
    assert len(by_kind["start"]["excerpt"]) <= 300
    assert by_kind["start"]["fields"]["offer"]["no_price"] is True
    assert by_kind["stop"]["matched_campaign"]["code"] == "S7"
    first_id = by_kind["start"]["id"]
    denied = await client.post(f"/perf/integrations/mizito/requests/{first_id}/approve", headers=auth(reader), json={})
    assert denied.status_code == 403
    assert (
        await client.post(f"/perf/integrations/mizito/requests/{first_id}/reject", headers=auth(reader))
    ).status_code == 403
    checked = await client.post("/perf/integrations/mizito/requests/check", headers=auth(reader))
    assert checked.status_code == 200 and checked.json()["checked"] is False  # بدون توکن
    assert fake.calls == []

    nadia = await login(client, "nadia-test@autoco.example")
    stop = await client.post(
        f"/perf/integrations/mizito/requests/{by_kind['stop']['id']}/approve", headers=auth(nadia), json={}
    )
    assert stop.status_code == 422
    codes = list((await db.scalars(select(PmCampaign.code).where(PmCampaign.organization_id == org))).all())
    approved = await client.post(
        f"/perf/integrations/mizito/requests/{first_id}/approve",
        headers=auth(nadia),
        json={"title": "کمپین ساختگی آلفا", "tag": "S", "channels": ["sms", "ig_story"]},
    )
    assert approved.status_code == 200, approved.text
    result = approved.json()
    assert result["campaign"]["code"] == next_code("S", codes)
    assert result["campaign"]["title"] == "کمپین ساختگی آلفا"
    assert result["campaign"]["channels"] == ["sms", "ig_story"]
    assert "بدون قیمت" in result["campaign"]["goal"]
    assert result["request"]["status"] == "approved"
    assert result["request"]["campaign"]["code"] == result["campaign"]["code"]
    again = await client.post(f"/perf/integrations/mizito/requests/{first_id}/approve", headers=auth(nadia), json={})
    assert again.status_code == 409

    circular = by_kind["circular"]["id"]
    from_draft = await client.post(
        f"/perf/integrations/mizito/requests/{circular}/approve", headers=auth(nadia), json={}
    )
    assert from_draft.status_code == 200, from_draft.text
    assert from_draft.json()["campaign"]["title"] == "مینی کمپین بخشنامه ZX-300"

    rejected = await client.post(
        f"/perf/integrations/mizito/requests/{by_kind['stop']['id']}/reject", headers=auth(nadia)
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    left = (await client.get("/perf/integrations/mizito/requests", headers=auth(nadia))).json()
    assert left["requests"] == [] and left["counts"] == {"new": 0, "approved": 2, "rejected": 1, "duplicate": 0}
    done = (await client.get("/perf/integrations/mizito/requests?status=approved", headers=auth(nadia))).json()
    assert len(done["requests"]) == 2
    missing = await client.post(
        "/perf/integrations/mizito/requests/00000000-0000-0000-0000-000000000000/reject", headers=auth(nadia)
    )
    assert missing.status_code == 404
    db.expire_all()
    rows = (await db.scalars(select(PmMizitoRequest).where(PmMizitoRequest.organization_id == org))).all()
    assert all(row.decided_at is not None for row in rows)
