"""میزیتو، پیشگام و آی‌اس‌ام‌اس را به کمپین‌های موجود وصل می‌کند."""

import asyncio

from sqlalchemy import select

from app import models  # noqa: F401
from app.db.session import AsyncSessionLocal
from app.models import Organization
from app.perf.services.extract_import import import_extracts


async def main() -> None:
    async with AsyncSessionLocal() as db:
        org = await db.scalar(select(Organization).where(Organization.slug == "autoco"))
        if org is None:
            raise SystemExit("org autoco not found")
        result = await import_extracts(db, org.id)
        await db.commit()
        print(result)


if __name__ == "__main__":
    asyncio.run(main())
