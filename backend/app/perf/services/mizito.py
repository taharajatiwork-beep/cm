"""خواندن میزیتو. بدون توکن هیچ تماسی زده نمی‌شود و چیزی نوشته نمی‌شود."""

from __future__ import annotations

import hashlib
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
_PROJECTS = ("پرفورمنس", "کمپین", "مالی")  # legacy substring fallback
_MAX_CARDS = 2000
_CHECKLIST_ITEMS = 30
_CHECKLIST_TITLE = 120
_WORKSPACE = re.compile(r"^[A-Za-z0-9]{1,64}$")
_PAGE_SIZE = 25
_MAX_PAGES = 40
_SYNC_MAX_PAGES = 200
_SYNC_MAX_CARDS = 8000

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
    from app.requests.mizito_lanes import wanted_marketing_mizito_project

    if wanted_marketing_mizito_project(title):
        return True
    text = normalize(title)
    return any(normalize(name) in text for name in _PROJECTS)


def perf_project(title: str) -> bool:
    """فقط سه پروژهٔ قدیمی پرفورمنس/کمپین/مالی — برای snapshot صفحهٔ هزینه و تریاژ."""
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
    weight = _number(task.get("kanban_weight")) or 0.0
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
        "weight": weight,
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
        "checklist_items": [_checklist_item(item, index) for index, item in enumerate(checklist)],
        "progress": max(0, min(100, round(progress))),
        "attachments": len(attachments) if isinstance(attachments, list) else 0,
        "has_comments": bool(task.get("has_comments")),
        "last_comment_at": _date(last_comment.get("comment_at")) if isinstance(last_comment, dict) else None,
    }


def _checklist_item(item: dict, index: int) -> dict:
    raw = _id(item)
    title = str(item.get("title") or "")
    if not raw:
        digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:10]
        raw = f"{index}:{digest}"
    return {
        "id": raw[:64],
        "title": title[:_CHECKLIST_TITLE],
        "checked": bool(item.get("checked")),
    }


def read_cards(
    projects_payload: Any,
    tasks_payload: Any,
    *,
    checklist_limit: int | None = _CHECKLIST_ITEMS,
    max_cards: int = _MAX_CARDS,
) -> dict:
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
        weight = card.get("weight") or 0.0
        position = card["board_position"] if card["board_position"] is not None else 999
        ranked.append(((not card["active"], card["project"], position, weight, card["title"]), card))
    ranked.sort(key=lambda pair: pair[0])
    cards = [card for _, card in ranked]
    if checklist_limit is not None:
        for card in cards:
            items = card.get("checklist_items") or []
            if len(items) > checklist_limit:
                card["checklist_items"] = items[:checklist_limit]
    if len(cards) > max_cards:
        cards = cards[:max_cards]
    from app.requests.mizito_lanes import lane_slug_for_mizito_project_title

    lane_boards: list[dict[str, Any]] = []
    for row in projects:
        slug = lane_slug_for_mizito_project_title(str(row.get("title") or ""))
        if not slug:
            continue
        pid = _id(row)
        for board_id, (board_title, position) in boards.get(pid, {}).items():
            if not board_id:
                continue
            lane_boards.append(
                {
                    "lane_slug": slug,
                    "board_id": board_id,
                    "title": board_title,
                    "position": position if position is not None else 999,
                }
            )
    lane_boards.sort(key=lambda item: (item["lane_slug"], item["position"], item["title"]))
    return {
        "projects": [{"title": str(row.get("title") or ""), "id": _id(row)} for row in projects],
        "lane_boards": lane_boards,
        "cards": cards,
        "open_count": sum(1 for card in cards if card["active"]),
        "total_count": len(cards),
        "truncated": len(ranked) > max_cards,
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


async def _project_tasks(
    client: httpx.AsyncClient,
    base: str,
    headers: dict,
    project_id: str,
    *,
    max_pages: int = _MAX_PAGES,
) -> tuple[list[dict], bool]:
    """کارت‌های باز و تکمیل‌شدهٔ یک پروژه. اگر به سقف صفحه برسد، truncated=True."""
    path = "tasks/upcoming"
    rows = _tasks(
        await mizito_post(
            client, base, path, headers, {"project_id": project_id, "kanban": True, "from": None, "filter": None}
        )
    )
    seen = {_id(row) for row in rows}
    loaded = 0
    truncated = False
    for _ in range(max_pages):
        body = {"project_id": project_id, "from": loaded, "filter": {"done_status": True, "completed": True}}
        page = _tasks(await mizito_post(client, base, path, headers, body))
        loaded += len(page)
        fresh = [row for row in page if _id(row) not in seen]
        seen.update(_id(row) for row in fresh)
        rows.extend(fresh)
        if len(page) < _PAGE_SIZE or not fresh:
            break
    else:
        truncated = True
    for row in rows:
        row.setdefault("project", project_id)
    return rows, truncated


def for_perf(parsed: dict) -> dict:
    """snapshot پرفورمنس فقط پروژه‌هایی که اسمشان پرفورمنس/کمپین/مالی است."""
    projects = [row for row in parsed.get("projects") or [] if perf_project(str(row.get("title") or ""))]
    ids = {str(row.get("id") or "") for row in projects}
    cards = []
    for card in parsed.get("cards") or []:
        if str(card.get("project_id") or "") not in ids:
            continue
        trimmed = dict(card)
        items = list(trimmed.get("checklist_items") or [])
        trimmed["checklist_items"] = items[:_CHECKLIST_ITEMS]
        cards.append(trimmed)
    boards = [
        row
        for row in parsed.get("lane_boards") or []
        if row.get("lane_slug") in {"finance_marketing", "performance", "campaigns"}
    ]
    out = dict(parsed)
    out["projects"] = projects
    out["cards"] = cards
    out["lane_boards"] = boards
    out["open_count"] = sum(1 for card in cards if card.get("active"))
    out["total_count"] = len(cards)
    return out


async def _read_projects(
    token: str,
    *,
    max_pages: int,
    checklist_limit: int | None,
    max_cards: int,
    timeout: float,
) -> dict:
    settings = get_settings()
    token = token.strip()
    if not token:
        return _offline("توکن میزیتو تنظیم نشده است")
    base = settings.perf_mizito_base.rstrip("/")
    headers = {"x-token": token, "Content-Type": "application/json"}
    truncated_projects: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            projects = await mizito_post(client, base, "projects/getList", headers, {})
            tasks: list[dict] = []
            for project in _projects(projects):
                if not wanted_project(str(project.get("title") or "")) or not _id(project):
                    continue
                rows, hit_cap = await _project_tasks(
                    client, base, headers, _id(project), max_pages=max_pages
                )
                tasks.extend(rows)
                if hit_cap:
                    truncated_projects.append(str(project.get("title") or _id(project)))
        parsed = read_cards(projects, tasks, checklist_limit=checklist_limit, max_cards=max_cards)
    except httpx.HTTPStatusError as exc:
        return _offline(mizito_http_reason(exc.response.status_code, _safe_json(exc.response)))
    except httpx.HTTPError as exc:
        return _offline(f"میزیتو خوانده نشد: {exc}")
    except (PerfError, ValueError) as exc:
        return _offline(str(exc))
    parsed["truncated_projects"] = truncated_projects
    parsed["truncated"] = bool(truncated_projects) or bool(parsed.get("truncated"))
    return {"connected": True, "reason": "", **parsed}


def _safe_json(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        return {}


async def mizito_full_read(token: str) -> dict:
    """شش پروژهٔ مارکتینگ، بردها، و همهٔ کارت‌ها (چک‌لیست کامل) برای همگام‌سازی کار."""
    return await _read_projects(
        token,
        max_pages=_SYNC_MAX_PAGES,
        checklist_limit=None,
        max_cards=_SYNC_MAX_CARDS,
        timeout=180,
    )


async def mizito_snapshot(token: str | None = None) -> dict:
    settings = get_settings()
    token = settings.perf_mizito_token.strip() if token is None else token.strip()
    raw = await _read_projects(
        token,
        max_pages=_MAX_PAGES,
        checklist_limit=_CHECKLIST_ITEMS,
        max_cards=_MAX_CARDS,
        timeout=45,
    )
    if not raw.get("connected"):
        return raw
    return for_perf(raw)


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
