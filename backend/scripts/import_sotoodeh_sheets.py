"""دفتر شماره، پرداخت‌ها، پیامک و گزارش کانال را روی کد کمپین به هم وصل می‌کند."""

import asyncio

from sqlalchemy import select

from app import models  # noqa: F401
from app.db.session import AsyncSessionLocal
from app.models import Organization
from app.perf.services.archive_import import import_sotoodeh


async def main() -> None:
    async with AsyncSessionLocal() as db:
        org = await db.scalar(select(Organization).where(Organization.slug == "autoco"))
        if org is None:
            raise SystemExit("org autoco not found")
        result = await import_sotoodeh(db, org.id)
        await db.commit()
        print(result)


if __name__ == "__main__":
    asyncio.run(main())
