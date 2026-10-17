"""خواندن کارت‌های میزیتو و ساخت/به‌روزرسانی پروژه‌های CM.

  uv run python -m scripts.sync_mizito_work --org autoco --purge-manual

توکن از pm_integration (ذخیرهٔ پنل) می‌آید؛ PERF_MIZITO_TOKEN فقط وقتی در DB چیزی نیست.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def _run(org: str, purge: bool) -> dict:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.core.config import get_settings
    from app.models import Organization
    from app.perf.services.connections import mizito_token_for
    from app.requests.mizito_sync import sync_mizito_cards_to_projects

    engine = create_async_engine(get_settings().database_url)
    try:
        async with AsyncSession(engine) as db:
            organization = await db.scalar(select(Organization).where(Organization.slug == org))
            if organization is None:
                raise SystemExit(f"org not found: {org}")
            token = (await mizito_token_for(db, organization.id)).strip()
            if not token:
                raise SystemExit(
                    "No Mizito token: save x-token in panel (Connections) for this org, "
                    "or set PERF_MIZITO_TOKEN for local dev only."
                )
            result = await sync_mizito_cards_to_projects(
                db, organization.id, token=token, purge_manual=purge
            )
            await db.commit()
            return result
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", default="autoco")
    parser.add_argument(
        "--purge-manual",
        action="store_true",
        help="حذف درخواست/پروژهٔ بدون mizito_card_id قبل از sync",
    )
    args = parser.parse_args()
    result = asyncio.run(_run(args.org, args.purge_manual))
    print(result)


if __name__ == "__main__":
    main()
