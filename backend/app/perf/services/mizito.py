"""خواندن میزیتو. بدون توکن هیچ تماسی زده نمی‌شود و چیزی نوشته نمی‌شود."""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.perf.models import PmCampaign, PmIntegration
from app.perf.services.common import PerfError, iso, now

_CODE = re.compile(r"\b([A-Z]{1,3}\d{1,3}(?:-\d+)?)\b", re.IGNORECASE)
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_PROJECTS = ("پرفورمنس", "کمپین", "مالی")
_MAX_CARDS = 2000
_CHECKLIST_ITEMS = 30
_CHECKLIST_TITLE = 120
_WORKSPACE = re.compile(r"^[A-Za-z0-9]{1,64}$")
_PAGE_SIZE = 25
_MAX_PAGES = 40

# وضعیت استاندارد هر کارت از روی اسم بردش. ترتیب مهم است: اولین تطبیق برنده است.
# تطبیق روی متن نرمال‌شده (ی/ک فارسی، بدون نیم‌فاصله، حروف کوچک) و از ابتدای کلمه است،
# پس «روش» با «فروش» جور نمی‌شود.
# تصمیم‌ها:
# - «تایید شده» و «تایید (میان مدت)» یعنی کار تأییدشده و منتظر شروع -> todo.
# - بقیهٔ «تایید ...» (مثل «تایید مدیر مالی») یعنی منتظر تأیید -> waiting_approval.
# - «انجام شده/منتظر بررسی» -> review؛ «اتمام کمپین/تحلیل» -> done.
# - «پرداخت های چند بخشی/عودت» -> waiting_payment؛ «اعلام ...» -> info.
# - «توقف ...» -> paused (فعال حساب نمی‌شود).
# - بردی که هیچ قاعده‌ای ندارد (مثل «پلن کلی») -> other و فعال می‌ماند.
BOARD_RULES: tuple[tuple[str, str], ...] = (
    ("cost tracking", "not_in_cost_tracking"),
    ("کنسل", "cancelled"),
    ("لغو", "cancelled"),
    ("توقف", "paused"),
    ("پرداخت شده", "paid"),
    ("درخواست پرداخت", "waiting_payment"),
    ("چند بخشی", "waiting_payment"),
    ("قوانین", "info"),
    ("اطلاعیه", "info"),
    ("روش", "info"),
    ("دستورالعمل", "info"),
    ("اعلام", "info"),
    ("منتظر بررسی", "review"),
    ("اتمام", "done"),
    ("انجام شد", "done"),
    ("تکمیل", "done"),
    ("در حال انجام", "in_progress"),
    ("بررسی", "review"),
    ("تحلیل", "review"),
    ("تایید شده", "todo"),
    ("میان مدت", "todo"),
    ("تایید", "waiting_approval"),
    ("برای انجام", "todo"),
    ("پیشنهاد", "idea"),
    ("ایده", "idea"),
)
STATUSES = (
    "idea",
    "todo",
    "in_progress",
    "review",
    "waiting_approval",
    "waiting_payment",
    "paid",
    "not_in_cost_tracking",
    "done",
    "cancelled",
    "paused",
    "info",
    "other",
)
INACTIVE = frozenset({"done", "paid", "cancelled", "info", "paused"})

_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "أ": "ا", "إ": "ا", "ـ": None})
_SPACES = re.compile(r"[\s\u200c\u200d\u200e\u200f\u00a0]+")


def normalize(text: Any) -> str:
    """ی/ک عربی به فارسی، نیم‌فاصله و فاصله‌های اضافه به یک فاصله، حروف کوچک."""
    value = str(text or "").translate(_LETTERS)
    return _SPACES.sub(" ", value).strip().lower()


def _has(text: str, key: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(key)}", text) is not None


def board_status(board_title: Any) -> str:
    text = normalize(board_title)
    if not text:
        return "other"
    for key, status in BOARD_RULES:
        if _has(text, key):
            return status
    return "other"


def is_active(status: str) -> bool:
    return status not in INACTIVE


def wanted_project(title: str) -> bool:
    text = normalize(title)
    return any(normalize(name) in text for name in _PROJECTS)


def _id(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("_id") or value.get("id") or "")
    return str(value or "")


def _boards(project: dict) -> dict[str, tuple[str, int]]:
    """شناسهٔ برد -> (اسم، جای ستون). ترتیب آرایه همان ترتیب ستون‌هاست."""
    raw = project.get("kanban_boards") or project.get("boards") or []
    found: dict[str, tuple[str, int]] = {}
    if isinstance(raw, dict):
        raw = list(raw.values())
    if not isinstance(raw, list):
        return found
    for position, item in enumerate(item for item in raw if isinstance(item, dict)):
        found[_id(item)] = (str(item.get("title") or item.get("name") or ""), position)
    return found


def _rows(payload: Any, keys: tuple[str, ...]) -> list[dict]:
    """لیست خام یا پیچیده در {status, data} یا {projects/tasks: [...]}، هر دو را می‌پذیرد."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in keys:
            rows = payload.get(key)
            if isinstance(rows, list):
                return [item for item in rows if isinstance(item, dict)]
        inner = payload.get("data")
        if isinstance(inner, (list, dict)):
            return _rows(inner, keys)
    return []


def _tasks(payload: Any) -> list[dict]:
    return _rows(payload, ("tasks", "items", "list", "rows"))


def _projects(payload: Any) -> list[dict]:
    return _rows(payload, ("projects", "items", "list"))


def code_key(code: Any) -> str:
    """کد برای مقایسه: رقم فارسی/عربی به انگلیسی، حروف بزرگ، بدون فاصله."""
    return re.sub(r"\s+", "", str(code or "").translate(_DIGITS)).upper()


def campaign_code(title: str) -> str:
    match = _CODE.search(str(title or "").translate(_DIGITS))
    return match.group(1).upper() if match else ""


def missing_codes(cards: list[dict], panel_codes: list[str]) -> list[dict]:
    """کدهایی که در کارت‌های میزیتو هستند ولی کمپینی با آن کد در پنل نیست. فعال‌ها اول، بعد تازه‌ترها."""
    known = {code_key(code) for code in panel_codes if code}
    groups: dict[str, list[dict]] = {}
    for card in cards:
        key = code_key(card.get("code"))
        if key and key not in known:
            groups.setdefault(key, []).append(card)
    found = []
    for key, rows in groups.items():
        latest = max(rows, key=lambda row: str(row.get("modified_at") or ""))
        found.append(
            {
                "code": key,
                "id": str(latest.get("id") or ""),
                "title": str(latest.get("title") or ""),
                "project": str(latest.get("project") or ""),
                "status": str(latest.get("status") or board_status(latest.get("board"))),
                "active": any(bool(row.get("active")) for row in rows),
                "completed": all(bool(row.get("completed")) for row in rows),
                "cards": len(rows),
                "modified_at": latest.get("modified_at"),
            }
        )
    found.sort(key=lambda row: str(row["modified_at"] or ""), reverse=True)
    found.sort(key=lambda row: not row["active"])
    return found


def _date(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _card(task: dict, project_id: str, project: dict, boards: dict[str, tuple[str, int]]) -> dict:
    """فقط فیلدهای لازم نگه داشته می‌شود؛ access_token، متن یادداشت و لینک پیوست‌ها نه."""
    board_id = _id(task.get("kanban_board") or task.get("board"))
    board, position = boards.get(board_id, ("", None))
    status = board_status(board)
    completed = bool(task.get("completed"))
    title = str(task.get("title") or "")
    # اگر عنوان کد نداشت، فقط خودِ کد از یادداشت برداشته می‌شود؛ متن یادداشت ذخیره نمی‌شود.
    code = campaign_code(title)
    code_source = "title" if code else ""
    if not code:
        code = campaign_code(str(task.get("notes") or ""))
        code_source = "notes" if code else ""
    raw_assignees = task.get("assignee")
    if not isinstance(raw_assignees, list):
        raw_assignees = [raw_assignees]
    assignees: list[str] = []
    for person in raw_assignees:
        person_id = _id(person)
        if person_id and person_id not in assignees:
            assignees.append(person_id)
    checklist = [item for item in task.get("checklist") or [] if isinstance(item, dict)]
    total = len(checklist)
    done = sum(1 for item in checklist if item.get("checked"))
    progress = _number(task.get("progress"))
    if progress is None:
        progress = done * 100 / total if total else 0
    attachments = task.get("attachments")
    last_comment = task.get("last_comment")
    return {
        "id": _id(task),
        "project": str(project.get("title") or ""),
        "project_id": project_id,
        "board_id": board_id,
        "board": board,
        "board_position": position,
        "title": title,
        "code": code,
        "code_source": code_source,
        "status": status,
        "completed": completed,
        "completed_at": _date(task.get("completed_at")),
        "active": not completed and is_active(status),
        "assignees": assignees,
        "owner": _id(task.get("owner")),
        "created_at": _date(task.get("created_at")),
        "modified_at": _date(task.get("modified_at")),
        "deadline": _date(task.get("deadline")),
        "checklist_done": done,
        "checklist_total": total,
        "checklist_items": [
            {"title": str(item.get("title") or "")[:_CHECKLIST_TITLE], "checked": bool(item.get("checked"))}
            for item in checklist[:_CHECKLIST_ITEMS]
        ],
        "progress": max(0, min(100, round(progress))),
        "attachments": len(attachments) if isinstance(attachments, list) else 0,
        "has_comments": bool(task.get("has_comments")),
        "last_comment_at": _date(last_comment.get("comment_at")) if isinstance(last_comment, dict) else None,
    }


def read_cards(projects_payload: Any, tasks_payload: Any) -> dict:
    """همهٔ کارت‌های سه پروژهٔ مارکتینگ، هر کدام با وضعیت استاندارد برد."""
    projects = [row for row in _projects(projects_payload) if wanted_project(str(row.get("title") or ""))]
    by_id = {_id(row): row for row in projects}
    boards = {pid: _boards(row) for pid, row in by_id.items()}
    ranked = []
    seen: set[str] = set()
    for task in _tasks(tasks_payload):
        project_id = _id(task.get("project"))
        project = by_id.get(project_id)
        task_id = _id(task)
        if project is None or task.get("deleted") or (task_id and task_id in seen):
            continue
        seen.add(task_id)
        card = _card(task, project_id, project, boards.get(project_id, {}))
        weight = _number(task.get("kanban_weight")) or 0.0
        position = card["board_position"] if card["board_position"] is not None else 999
        ranked.append(((not card["active"], card["project"], position, weight, card["title"]), card))
    ranked.sort(key=lambda pair: pair[0])
    cards = [card for _, card in ranked]
    return {
        "projects": [{"title": str(row.get("title") or ""), "id": _id(row)} for row in projects],
        "cards": cards[:_MAX_CARDS],
        "open_count": sum(1 for card in cards if card["active"]),
        "total_count": len(cards),
    }


def _ok(status: Any) -> bool:
    return str(status).strip().lower() in {"1", "true", "ok", "success", "200"}


def _unwrap(payload: Any) -> Any:
    """پاسخ {status, data, msg} را باز می‌کند؛ پاسخ خام (که میزیتو الان می‌دهد) همان‌طور برمی‌گردد."""
    if not isinstance(payload, dict) or "status" not in payload:
        return payload
    if not _ok(payload.get("status")):
        raise PerfError(str(payload.get("msg") or payload.get("message") or "میزیتو پاسخ نداد"))
    return payload.get("data") if "data" in payload else payload


def _offline(reason: str) -> dict:
    return {
        "connected": False,
        "reason": reason,
        "projects": [],
        "cards": [],
        "open_count": 0,
        "total_count": 0,
    }


# تنها مسیرهایی که پنل حق دارد صدا بزند؛ همه فقط خواندنی‌اند. هر چیز دیگری (chat/seen، getChatView،
# tasks/get، inbox، هر نوشتن یا علامت خواندن) پیش از رفتن به شبکه رد می‌شود.
ALLOWED_ENDPOINTS = frozenset(
    {"projects/getList", "tasks/getAll", "tasks/upcoming", "chat/getDialogs", "chat/getHistory"}
)


async def mizito_post(client: httpx.AsyncClient, base: str, path: str, headers: dict, body: dict) -> Any:
    """تنها درگاه تماس با میزیتو."""
    if path not in ALLOWED_ENDPOINTS:
        raise PerfError(f"مسیر میزیتو مجاز نیست: {path}")
    response = await client.post(f"{base.rstrip('/')}/api/{path}", headers=headers, json=body)
    response.raise_for_status()
    return _unwrap(response.json())


async def _project_tasks(client: httpx.AsyncClient, base: str, headers: dict, project_id: str) -> list[dict]:
    """کارت‌های باز و تکمیل‌شدهٔ یک پروژه، همان خواندنی که خود وب‌اپ میزیتو می‌زند (فقط خواندن)."""
    path = "tasks/upcoming"
    rows = _tasks(
        await mizito_post(
            client, base, path, headers, {"project_id": project_id, "kanban": True, "from": None, "filter": None}
        )
    )
    seen = {_id(row) for row in rows}
    loaded = 0
    for _ in range(_MAX_PAGES):
        body = {"project_id": project_id, "from": loaded, "filter": {"done_status": True, "completed": True}}
        page = _tasks(await mizito_post(client, base, path, headers, body))
        loaded += len(page)
        fresh = [row for row in page if _id(row) not in seen]
        seen.update(_id(row) for row in fresh)
        rows.extend(fresh)
        if len(page) < _PAGE_SIZE or not fresh:
            break
    for row in rows:
        row.setdefault("project", project_id)
    return rows


async def mizito_snapshot(token: str | None = None) -> dict:
    settings = get_settings()
    token = settings.perf_mizito_token.strip() if token is None else token.strip()
    if not token:
        return _offline("توکن میزیتو تنظیم نشده است")
    base = settings.perf_mizito_base.rstrip("/")
    headers = {"x-token": token, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            projects = await mizito_post(client, base, "projects/getList", headers, {})
            tasks: list[dict] = []
            for project in _projects(projects):
                if wanted_project(str(project.get("title") or "")) and _id(project):
                    tasks.extend(await _project_tasks(client, base, headers, _id(project)))
        parsed = read_cards(projects, tasks)
    except httpx.HTTPError as exc:
        return _offline(f"میزیتو خوانده نشد: {exc}")
    except (PerfError, ValueError) as exc:
        return _offline(str(exc))
    return {"connected": True, "reason": "", **parsed}


_EMPTY = {**_offline("هنوز از میزیتو خوانده نشده است"), "read_at": None}


def card_url_prefix() -> str:
    """پیشوند لینک «باز کردن در میزیتو»؛ شکلش از مسیر ws.tasks.inbox وب‌اپ میزیتو است: /#/ws/tasks/inbox/<workspace>_<task>.

    فقط اگر شناسهٔ فضای کاری تنظیم شده باشد؛ وگرنه خالی و لینکی نشان داده نمی‌شود.
    """
    settings = get_settings()
    workspace = settings.perf_mizito_workspace_id.strip()
    if not _WORKSPACE.match(workspace):
        return ""
    return f"{settings.perf_mizito_web.rstrip('/')}/#/ws/tasks/inbox/{workspace}_"


def _with_defaults(data: dict) -> dict:
    """عکس‌های قدیمی (بدون status/active) هم بدون خطا خوانده شوند."""
    raw = data.get("cards")
    cards = [card for card in raw if isinstance(card, dict)] if isinstance(raw, list) else []
    for card in cards:
        if not card.get("status"):
            card["status"] = board_status(card.get("board"))
        if "active" not in card:
            card["active"] = not card.get("completed") and is_active(card["status"])
    data["cards"] = cards
    if not isinstance(data.get("projects"), list):
        data["projects"] = []
    data.setdefault("open_count", sum(1 for card in cards if card["active"]))
    data.setdefault("total_count", len(cards))
    return data


async def saved_mizito(db: AsyncSession, organization_id: UUID) -> dict:
    row = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
    raw = (row.mizito_snapshot if row else "").strip()
    if not raw:
        return {**_EMPTY, "card_url_prefix": card_url_prefix()}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return dict(_EMPTY)
    if not isinstance(data, dict):
        return dict(_EMPTY)
    data = _with_defaults(data)
    data["read_at"] = iso(row.mizito_read_at) if row and row.mizito_read_at else None
    data["card_url_prefix"] = card_url_prefix()
    return data


async def mizito_missing(db: AsyncSession, organization_id: UUID) -> dict:
    """فقط از عکس ذخیره‌شده؛ به میزیتو وصل نمی‌شود."""
    data = await saved_mizito(db, organization_id)
    codes = (await db.scalars(select(PmCampaign.code).where(PmCampaign.organization_id == organization_id))).all()
    return {
        "connected": bool(data.get("connected")),
        "read_at": data.get("read_at"),
        "codes": missing_codes(data.get("cards") or [], list(codes)),
    }


def _fa_code(status: int) -> str:
    return str(status).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def mizito_http_reason(status: int, body: object) -> str:
    """خطای میزیتو با کد وضعیت. توکن داخل متن نیست."""
    message = ""
    if isinstance(body, dict):
        message = str(body.get("msg") or body.get("message") or "")[:180]
    if status in (401, 403):
        text = f"توکن میزیتو پذیرفته نشد ({_fa_code(status)}). x-token منقضی شده یا عوض شده است."
    else:
        text = f"میزیتو پاسخ {_fa_code(status)} داد."
    return f"{text} {message}".strip()


async def probe_mizito(db: AsyncSession, organization_id: UUID) -> dict:
    """فقط projects/getList را می‌خواند تا وضعیت اتصال تازه بماند. کارت‌ها عوض نمی‌شوند."""
    from app.perf.services.connections import mizito_token_for

    token = await mizito_token_for(db, organization_id)
    if not token:
        return {"ok": False, "reason": "توکن میزیتو ذخیره نشده است. بدون x-token هیچ کارتی خوانده نمی‌شود.", "at": None}
    settings = get_settings()
    headers = {"x-token": token, "Content-Type": "application/json"}
    ok = False
    reason = ""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await mizito_post(client, settings.perf_mizito_base, "projects/getList", headers, {})
        ok = True
    except httpx.HTTPStatusError as exc:
        try:
            body = exc.response.json()
        except ValueError:
            body = {}
        reason = mizito_http_reason(exc.response.status_code, body)
    except httpx.HTTPError as exc:
        reason = f"به میزیتو وصل نشدیم: {exc}"[:240]
    except PerfError as exc:
        reason = str(exc)[:240]
    if token and token in reason:
        reason = reason.replace(token, "…")
    row = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
    if row is None:
        row = PmIntegration(organization_id=organization_id)
        db.add(row)
    stored: dict | None = None
    if (row.mizito_snapshot or "").strip():
        try:
            parsed = json.loads(row.mizito_snapshot)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            stored = parsed
    if stored is None:
        stored = _offline("هنوز از میزیتو خوانده نشده است")
    stamped = iso(now())
    stored["probed_ok"] = ok
    stored["probe_reason"] = reason
    stored["probed_at"] = stamped
    if not ok:
        stored["last_error"] = reason
        stored["last_error_at"] = stamped
    else:
        stored.pop("last_error", None)
        stored.pop("last_error_at", None)
    row.mizito_snapshot = json.dumps(stored, ensure_ascii=False)
    await db.flush()
    return {"ok": ok, "reason": reason, "at": stamped}


async def refresh_mizito(db: AsyncSession, organization_id: UUID) -> dict:
    from app.perf.services.connections import mizito_token_for

    fresh = await mizito_snapshot(await mizito_token_for(db, organization_id))
    if not fresh.get("connected"):
        previous = await saved_mizito(db, organization_id)
        fresh["read_at"] = previous.get("read_at")
        reason = str(fresh.get("reason") or "میزیتو وصل نشد")
        row = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
        if row is None:
            row = PmIntegration(organization_id=organization_id)
            db.add(row)
        stored: dict | None = None
        if (row.mizito_snapshot or "").strip():
            try:
                parsed = json.loads(row.mizito_snapshot)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                stored = parsed
        if stored is None:
            stored = _offline(reason)
        stored["last_error"] = reason
        stored["last_error_at"] = iso(now())
        row.mizito_snapshot = json.dumps(stored, ensure_ascii=False)
        await db.flush()
        return fresh
    row = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
    if row is None:
        row = PmIntegration(organization_id=organization_id)
        db.add(row)
    payload = {
        "connected": True,
        "reason": "",
        "probed_ok": True,
        "probe_reason": "",
        "probed_at": iso(now()),
        "projects": fresh["projects"],
        "cards": fresh["cards"],
        "open_count": fresh["open_count"],
        "total_count": fresh.get("total_count", len(fresh["cards"])),
    }
    row.mizito_snapshot = json.dumps(payload, ensure_ascii=False)
    row.mizito_read_at = now()
    await db.flush()
    payload["read_at"] = iso(row.mizito_read_at)
    payload["card_url_prefix"] = card_url_prefix()
    return payload
