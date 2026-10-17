"""تحلیل GET-only از نوین‌هاب و وردست؛ ذخیرهٔ خلاصه در pm_integration (بدون PII خام)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.perf.models import PmIntegration
from app.perf.services.common import iso, now
from app.perf.services.novinhub import (
    list_novinhub_comments,
    list_novinhub_conversations,
    read_novinhub,
)
from app.perf.services.vardast import list_vardast_assistants, list_vardast_contacts, read_vardast

ROLLUP_TTL_SECONDS = 1200
_CLOSED_STATUS = frozenset(
    {
        "2",
        "3",
        "4",
        "closed",
        "done",
        "replied",
        "answered",
        "resolved",
        "archived",
    }
)


def _status_open(status: Any) -> bool:
    if status is None:
        return True
    text = str(status).strip().lower()
    if not text:
        return True
    if text in _CLOSED_STATUS:
        return False
    if text.isdigit() and int(text) >= 2:
        return False
    return True


def _count_by_status(items: list[dict], key: str = "status") -> dict[str, int]:
    out: dict[str, int] = {}
    for row in items:
        raw = row.get(key)
        label = str(raw) if raw is not None else "unknown"
        out[label] = out.get(label, 0) + 1
    return out


def _open_count(items: list[dict]) -> int:
    return sum(1 for row in items if _status_open(row.get("status")))


def _by_account(items: list[dict], name_key: str = "account_name") -> list[dict]:
    buckets: dict[str, int] = {}
    for row in items:
        name = (row.get(name_key) or "—").strip() or "—"
        buckets[name] = buckets.get(name, 0) + 1
    rows = [{"account": k, "count": v} for k, v in buckets.items()]
    rows.sort(key=lambda r: (-r["count"], r["account"]))
    return rows[:12]


def _redact_sample(text: str, limit: int = 80) -> str:
    cleaned = re.sub(r"@\w+", "@…", text or "")
    cleaned = re.sub(r"\d{10,}", "…", cleaned)
    cleaned = cleaned.strip()
    if len(cleaned) > limit:
        return cleaned[: limit - 1] + "…"
    return cleaned


def _parse_usage_number(usage: dict | None, key: str) -> int | None:
    if not usage:
        return None
    val = usage.get(key)
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str) and val.strip().isdigit():
        return int(val.strip())
    return None


async def _integration_row(db: AsyncSession, organization_id: UUID) -> PmIntegration:
    row = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
    if row is None:
        row = PmIntegration(organization_id=organization_id)
        db.add(row)
        await db.flush()
    return row


def _rollup_fresh(at: datetime | None) -> bool:
    if at is None:
        return False
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    age = (now() - at).total_seconds()
    return age < ROLLUP_TTL_SECONDS


async def build_social_rollup(db: AsyncSession, organization_id: UUID) -> dict:
    nh_accounts = await read_novinhub(db, organization_id)
    vd_home = await read_vardast(db, organization_id)
    comments = await list_novinhub_comments(db, organization_id, limit=50)
    conversations = await list_novinhub_conversations(db, organization_id, limit=50)
    assistants = await list_vardast_assistants(db, organization_id)
    contacts_page = await list_vardast_contacts(db, organization_id, size=1)

    comment_items = comments.get("items") or []
    conv_items = conversations.get("items") or []
    usage = vd_home.get("usage") if isinstance(vd_home.get("usage"), dict) else None

    chat_credit = _parse_usage_number(usage, "chat_credit")
    total_chats = _parse_usage_number(usage, "total_chats")
    contact_credit = _parse_usage_number(usage, "contact_credit")
    low_chat_credit = chat_credit is not None and chat_credit <= 50
    low_contact_credit = contact_credit is not None and contact_credit <= 50

    comment_samples = [
        {
            "account": row.get("account_name") or "—",
            "status": row.get("status"),
            "snippet": _redact_sample(str(row.get("text") or "")),
        }
        for row in comment_items[:8]
    ]
    direct_samples = [
        {
            "account": row.get("account_name") or "—",
            "status": row.get("status"),
            "snippet": _redact_sample(str(row.get("last_message") or "")),
        }
        for row in conv_items[:8]
    ]

    disconnected = sum(1 for a in nh_accounts.get("accounts") or [] if a.get("login_required"))

    rollup = {
        "fetched_at": iso(now()),
        "novinhub": {
            "connected": bool(nh_accounts.get("connected")),
            "reason": nh_accounts.get("reason") or "",
            "account_count": len(nh_accounts.get("accounts") or []),
            "accounts_needing_login": disconnected,
            "comments_sampled": len(comment_items),
            "comments_open_est": _open_count(comment_items),
            "comments_by_status": _count_by_status(comment_items),
            "comments_by_account": _by_account(comment_items),
            "conversations_sampled": len(conv_items),
            "conversations_open_est": _open_count(conv_items),
            "conversations_by_status": _count_by_status(conv_items),
            "conversations_by_account": _by_account(conv_items),
            "comment_snippets": comment_samples,
            "direct_snippets": direct_samples,
            "api_total_comments": comments.get("total"),
            "api_total_conversations": conversations.get("total"),
        },
        "vardast": {
            "connected": bool(vd_home.get("connected")),
            "reason": vd_home.get("reason") or "",
            "channel_count": len(vd_home.get("channels") or []),
            "assistant_count": len(assistants.get("items") or []) if assistants.get("ok") else 0,
            "contacts_total_api": contacts_page.get("total"),
            "usage": {
                "total_chats": total_chats,
                "chat_credit": chat_credit,
                "total_contacts": _parse_usage_number(usage, "total_contacts"),
                "contact_credit": contact_credit,
                "next_due_date": str(usage.get("next_due_date") or "") if usage else "",
            },
            "low_chat_credit": low_chat_credit,
            "low_contact_credit": low_contact_credit,
            "channels": (vd_home.get("channels") or [])[:20],
        },
        "notes": "Aggregated from live GET samples; open counts are estimates on the latest page only.",
    }
    return rollup


async def social_overview(
    db: AsyncSession,
    organization_id: UUID,
    *,
    refresh: bool = False,
) -> dict:
    row = await _integration_row(db, organization_id)
    cached: dict | None = None
    if (row.social_rollup_json or "").strip():
        try:
            parsed = json.loads(row.social_rollup_json)
            if isinstance(parsed, dict):
                cached = parsed
        except json.JSONDecodeError:
            cached = None

    if not refresh and cached and _rollup_fresh(row.social_rollup_at):
        return {
            "cached": True,
            "rollup_at": iso(row.social_rollup_at) if row.social_rollup_at else None,
            **cached,
        }

    rollup = await build_social_rollup(db, organization_id)
    stamped = now()
    row.social_rollup_json = json.dumps(rollup, ensure_ascii=False)
    row.social_rollup_at = stamped
    await db.flush()
    return {"cached": False, "rollup_at": iso(stamped), **rollup}


async def social_home_hints(db: AsyncSession, organization_id: UUID) -> list[dict]:
    """کار بعدی پرفورمنس — فقط از cache؛ بدون refresh اجباری."""
    from app.perf.models import PmSocialDaily

    row = await db.scalar(select(PmIntegration).where(PmIntegration.organization_id == organization_id))
    if not row or not (row.social_rollup_json or "").strip():
        latest = await db.scalar(
            select(PmSocialDaily)
            .where(PmSocialDaily.organization_id == organization_id)
            .order_by(PmSocialDaily.day.desc())
            .limit(1)
        )
        if latest and (latest.comments_open_est >= 5 or latest.conversations_open_est >= 5):
            return [
                {
                    "tone": "warn",
                    "label": "اینباکس",
                    "title": f"آخرین sync ({latest.day.isoformat()}): ~{latest.comments_open_est} کامنت و ~{latest.conversations_open_est} دایرکت باز",
                    "href": "/perf/insights",
                }
            ]
        return []
    try:
        rollup = json.loads(row.social_rollup_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(rollup, dict):
        return []
    hints: list[dict] = []
    nh = rollup.get("novinhub") if isinstance(rollup.get("novinhub"), dict) else {}
    vd = rollup.get("vardast") if isinstance(rollup.get("vardast"), dict) else {}

    if nh.get("accounts_needing_login"):
        n = nh["accounts_needing_login"]
        hints.append(
            {
                "tone": "warn",
                "label": "نوین‌هاب",
                "title": f"{n} اکانت نوین‌هاب قطع است — در پنل نوین‌هاب دوباره وصل کنید",
                "href": "/perf/novinhub",
            }
        )
    open_comments = int(nh.get("comments_open_est") or 0)
    open_directs = int(nh.get("conversations_open_est") or 0)
    if nh.get("connected") and (open_comments >= 5 or open_directs >= 5):
        hints.append(
            {
                "tone": "warn",
                "label": "اینباکس",
                "title": f"تخمین صف: {open_comments} کامنت و {open_directs} دایرکت باز (نمونهٔ اخیر)",
                "href": "/perf/insights",
            }
        )
    if vd.get("low_chat_credit"):
        credit = (vd.get("usage") or {}).get("chat_credit")
        hints.append(
            {
                "tone": "warn",
                "label": "وردست",
                "title": f"اعتبار گفتگوی وردست کم است ({credit})",
                "href": "/perf/vardast",
            }
        )
    stale_at = row.social_rollup_at
    if stale_at and stale_at.tzinfo is None:
        stale_at = stale_at.replace(tzinfo=timezone.utc)
    if stale_at and (now() - stale_at) > timedelta(hours=6):
        hints.append(
            {
                "tone": "",
                "label": "تحلیل",
                "title": "خلاصهٔ سوشال بیش از ۶ ساعت به‌روز نشده — تازه‌سازی کنید",
                "href": "/perf/insights",
            }
        )
    return hints


def rollup_for_ai_lab(rollup: dict, *, from_date: str, to_date: str, brand: str = "") -> dict:
    """برای snapshot AI Lab — بدون متن کامل پیام."""
    nh = rollup.get("novinhub") if isinstance(rollup.get("novinhub"), dict) else {}
    vd = rollup.get("vardast") if isinstance(rollup.get("vardast"), dict) else {}
    return {
        "kind": "social_inbox_review",
        "period": {"from": from_date, "to": to_date, "brand_filter": (brand or "").strip()},
        "novinhub": {
            "connected": nh.get("connected"),
            "accounts_needing_login": nh.get("accounts_needing_login"),
            "comments_open_est": nh.get("comments_open_est"),
            "conversations_open_est": nh.get("conversations_open_est"),
            "comments_by_status": nh.get("comments_by_status"),
            "conversations_by_status": nh.get("conversations_by_status"),
            "comments_by_account": nh.get("comments_by_account"),
            "conversations_by_account": nh.get("conversations_by_account"),
            "comment_snippets": nh.get("comment_snippets"),
            "direct_snippets": nh.get("direct_snippets"),
        },
        "vardast": {
            "connected": vd.get("connected"),
            "channel_count": vd.get("channel_count"),
            "assistant_count": vd.get("assistant_count"),
            "usage": vd.get("usage"),
            "low_chat_credit": vd.get("low_chat_credit"),
            "low_contact_credit": vd.get("low_contact_credit"),
        },
        "notes": "Inbox automation review; no phone numbers. Snippets are redacted samples only.",
    }
