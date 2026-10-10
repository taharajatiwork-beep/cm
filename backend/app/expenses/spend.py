"""جمع هزینهٔ ثبت‌شدهٔ پروژه‌ها."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.perf.models import PmPaymentRequest


async def recorded_for_projects(db: AsyncSession, organization_id: UUID, project_ids: set[UUID]) -> int:
    if not project_ids:
        return 0
    rows = list(
        (
            await db.scalars(
                select(PmPaymentRequest).where(
                    PmPaymentRequest.organization_id == organization_id,
                    PmPaymentRequest.status == "recorded",
                )
            )
        ).all()
    )
    return sum(row.amount_toman for row in rows if row.project_id in project_ids)


async def budget_for_project(db: AsyncSession, organization_id: UUID, project_id: UUID, planned: int) -> dict:
    rows = list(
        (
            await db.scalars(
                select(PmPaymentRequest).where(
                    PmPaymentRequest.organization_id == organization_id,
                    PmPaymentRequest.project_id == project_id,
                )
            )
        ).all()
    )
    committed = sum(row.amount_toman for row in rows if row.status in ("manager_ok", "finance_ok", "paid"))
    actual = sum(row.amount_toman for row in rows if row.status == "recorded")
    return {"planned": planned, "committed": committed, "actual": actual, "over": actual > planned > 0}
