"""تخصیص کد کمپین (S94، …) در دیتابیس — دفتر شماره فقط خروجی شیت است."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.perf.campaign_register import next_number, sequence_of
from app.perf.models import PmCampaign, PmCampaignSequence


async def _highest_seq(db: AsyncSession, organization_id: UUID) -> int:
    codes = list(
        (await db.scalars(select(PmCampaign.code).where(PmCampaign.organization_id == organization_id))).all()
    )
    return next_number(codes) - 1


async def allocate_campaign_code(db: AsyncSession, organization_id: UUID, tag: str) -> str:
    tag = tag.strip().upper() or "S"
    row = await db.get(PmCampaignSequence, organization_id)
    if row is None:
        row = PmCampaignSequence(organization_id=organization_id, next_seq=await _highest_seq(db, organization_id))
        db.add(row)
        await db.flush()
    for _ in range(32):
        row.next_seq += 1
        code = f"{tag}{row.next_seq}"
        if sequence_of(code) is None:
            continue
        exists = await db.scalar(
            select(PmCampaign.id).where(PmCampaign.organization_id == organization_id, PmCampaign.code == code)
        )
        if exists is None:
            await db.flush()
            return code
    raise RuntimeError("کد کمپین آزاد پیدا نشد")
