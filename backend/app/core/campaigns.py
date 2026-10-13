"""پل کمپین برای ماژول درخواست‌ها.

ماژول درخواست‌ها نباید مستقیم به `app.perf` وابسته باشد (perf خودش به requests
وابسته است؛ وابستگی دوطرفه می‌سازد). این ماژول در `core` زندگی می‌کند تا هر دو
بتوانند از آن استفاده کنند بدون اینکه مرز معماری بشکند.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def project_campaigns(db: AsyncSession, organization_id: UUID, project_id: UUID) -> tuple[list[dict], list[dict]]:
    """کمپین‌های متصل به پروژه و فهرست کامل کمپین‌های سازمان."""
    from app.perf.models import PmCampaign

    rows = list(
        (
            await db.scalars(
                select(PmCampaign)
                .where(PmCampaign.organization_id == organization_id)
                .order_by(PmCampaign.code)
            )
        ).all()
    )
    linked = [{"id": str(row.id), "code": row.code, "title": row.title} for row in rows if row.project_id == project_id]
    choices = [
        {
            "id": str(row.id),
            "code": row.code,
            "title": row.title,
            "project_id": str(row.project_id) if row.project_id else None,
        }
        for row in rows
    ]
    return linked, choices


async def set_project_campaigns(db: AsyncSession, organization_id: UUID, project_id: UUID, campaign_ids: list[UUID]) -> list[dict]:
    """کمپین‌های این پروژه را یکجا تعیین می‌کند. یک پروژه چند کمپین می‌گیرد."""
    from app.perf.models import PmCampaign

    wanted = set(campaign_ids)
    if wanted:
        found = list(
            (
                await db.scalars(
                    select(PmCampaign).where(PmCampaign.organization_id == organization_id, PmCampaign.id.in_(wanted))
                )
            ).all()
        )
        if len(found) != len(wanted):
            raise LookupError("یکی از کمپین‌ها پیدا نشد")
    current = list(
        (
            await db.scalars(
                select(PmCampaign).where(PmCampaign.organization_id == organization_id, PmCampaign.project_id == project_id)
            )
        ).all()
    )
    for campaign in current:
        if campaign.id not in wanted:
            campaign.project_id = None
    if wanted:
        chosen = list((await db.scalars(select(PmCampaign).where(PmCampaign.id.in_(wanted)))).all())
        for campaign in chosen:
            campaign.project_id = project_id
    await db.flush()
    linked, _choices = await project_campaigns(db, organization_id, project_id)
    return linked


def campaign_tag_choices() -> list[dict]:
    from app.perf.campaign_register import TAGS

    return [{"tag": row["tag"], "brand": row["brand"]} for row in TAGS]


async def create_project_campaign(
    db: AsyncSession,
    organization_id: UUID,
    project_id: UUID,
    user_id: UUID,
    title: str,
    tag: str,
) -> dict:
    """کمپین تازه با شمارهٔ بعدی دفتر، وصل به همین پروژه."""
    from app.perf.campaign_register import TAGS, next_code, tag_brand
    from app.perf.models import PmCampaign

    known = {row["tag"] for row in TAGS}
    letter = (tag or "S").strip().upper()
    if letter not in known:
        raise ValueError("حرف برند در دفتر شماره نیست")
    name = title.strip()
    if not name:
        raise ValueError("عنوان کمپین لازم است")
    codes = list(
        (await db.scalars(select(PmCampaign.code).where(PmCampaign.organization_id == organization_id))).all()
    )
    row = PmCampaign(
        organization_id=organization_id,
        code=next_code(letter, codes),
        title=name[:200],
        brand=tag_brand(letter),
        status="active",
        channels="sms",
        project_id=project_id,
        created_by=user_id,
    )
    db.add(row)
    await db.flush()
    return {"id": str(row.id), "code": row.code, "title": row.title, "brand": row.brand}
