"""راستی‌آزمایی زنجیرهٔ هش لاگ ممیزی.

لاگ ممیزی در سطح API فقط-افزودنی است، ولی دسترسی مستقیم به دیتابیس می‌تواند
سطرها را تغییر یا حذف کند. از مهاجرت ۰۰۱۱ هر سطر یک `row_hash` دارد که از
محتوای سطر + هش سطر قبلی ساخته می‌شود، پس هر تغییر یا حذف قابل‌شناسایی است.

این ابزار کل زنجیرهٔ هر سازمان را بازمحاسبه می‌کند و می‌گوید کجا شکسته است.
برای ممیزی دوره‌ای یا بعد از دسترسی مستقیم به دیتابیس اجرا می‌شود.

اجرا:
    uv run python -m scripts.verify_audit_chain
    uv run python -m scripts.verify_audit_chain --org autoco
    uv run python -m scripts.verify_audit_chain --json      # برای مانیتورینگ
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from uuid import UUID

from app.db.session import AsyncSessionLocal
from app.models import Organization
from app.services import verify_audit_chain

from sqlalchemy import select


@dataclass
class ChainResult:
    organization_id: str
    organization_slug: str
    rows_checked: int
    ok: bool
    broken_at: str | None
    detail: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "organization_id": self.organization_id,
            "organization_slug": self.organization_slug,
            "rows_checked": self.rows_checked,
            "ok": self.ok,
            "broken_at": self.broken_at,
            "detail": self.detail,
        }


async def verify_org(session, org_id: UUID, slug: str) -> ChainResult:
    result = await verify_audit_chain(session, org_id)
    return ChainResult(
        organization_id=str(org_id),
        organization_slug=slug,
        rows_checked=result["rows_checked"],
        ok=result["ok"],
        broken_at=result["broken_at"],
        detail=result["detail"],
    )


async def main() -> int:
    ap = argparse.ArgumentParser(description="راستی‌آزمایی زنجیرهٔ هش لاگ ممیزی")
    ap.add_argument("--org", help="فقط این سازمان (slug یا uuid)")
    ap.add_argument("--json", action="store_true", help="خروجی JSON")
    args = ap.parse_args()

    async with AsyncSessionLocal() as session:
        q = select(Organization)
        if args.org:
            q = q.where(
                (Organization.slug == args.org) | (Organization.id == _try_uuid(args.org))
            )
        orgs = list((await session.execute(q)).scalars())

        if not orgs:
            print("سازمانی پیدا نشد.", file=sys.stderr)
            return 2

        results = [await verify_org(session, o.id, o.slug) for o in orgs]

    if args.json:
        print(json.dumps([r.as_dict() for r in results], ensure_ascii=False, indent=2))
    else:
        total = sum(r.rows_checked for r in results)
        for r in results:
            mark = "سالم" if r.ok else "شکسته"
            print(f"[{mark}] {r.organization_slug}: {r.rows_checked} سطر")
            if not r.ok:
                print(f"        نقطهٔ شکست: {r.broken_at} — {r.detail}")
        bad = [r for r in results if not r.ok]
        print(f"\n{len(results)} سازمان، {total} سطر بررسی شد — {len(bad)} مشکل")

    return 1 if any(not r.ok for r in results) else 0


def _try_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
