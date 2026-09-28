"""مرحله ۷: SLA واقعی با تقویم کاری، پشت پرچم‌های sla_use_business_calendar / sla_chain_escalation."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.calendar import IRAN_HOLIDAYS, add_business_minutes, to_business_time
from app.core.config import Settings
from app.models import Notification, Task
from app.models.enums import Priority, SlaState
from app.services import SlaService
from tests.conftest import seeded  # noqa: F401


def test_default_flags_stay_off():
    """پیش‌فرض دو پرچم باید false بماند (Plan / Stage 7)."""
    s = Settings()
    assert s.sla_use_business_calendar is False
    assert s.sla_chain_escalation is False


def test_add_business_minutes_crosses_weekend_and_holiday():
    """۲۰۲۶-۰۳-۲۰ جمعه و تعطیل رسمی است؛ ۳۰ دقیقه کاری باید به روز کاری بعد برسد."""
    assert datetime(2026, 3, 20).weekday() == 4  # جمعه
    start = datetime(2026, 3, 20, 10, 0, tzinfo=UTC)
    out = add_business_minutes(start, 30)
    # ۲۱-۲۴ تعطیل (نوروز) → اولین روز کاری چهارشنبه ۲۵ ساعت ۸:۳۰
    assert out == datetime(2026, 3, 25, 8, 30, tzinfo=UTC)
    assert 8 <= out.hour < 17


def test_add_business_minutes_stops_at_end_of_day():
    """۱۶:۴۵ +۳۰ دقیقه → ۱۵ دقیقه تا ۱۷ و ۱۵ دقیقه صبح روز بعد."""
    # ۲۳ مارس دوشنبه تعطیل است، ۲۵ چهارشنبه اول روز کاری
    out = add_business_minutes(datetime(2026, 3, 25, 16, 45, tzinfo=UTC), 30)
    assert out == datetime(2026, 3, 26, 8, 15, tzinfo=UTC)


def test_to_business_time_and_holiday_coverage():
    # خارج از ساعات کاری → اولین لحظه کاری
    assert to_business_time(datetime(2026, 3, 25, 19, 0, tzinfo=UTC)) == datetime(
        2026, 3, 26, 8, 0, tzinfo=UTC
    )
    # همان روز کاری قبل از ساعت ۸ → همان روز ساعت ۸
    assert to_business_time(datetime(2026, 3, 25, 6, 30, tzinfo=UTC)) == datetime(
        2026, 3, 25, 8, 0, tzinfo=UTC
    )
    # روز کاری داخل ساعت اداری → دست نمی‌خورد
    assert to_business_time(datetime(2026, 3, 25, 11, 15, tzinfo=UTC)) == datetime(
        2026, 3, 25, 11, 15, tzinfo=UTC
    )
    # تعطیلات سال جاری: نوروز و روز جمهوری و ۲۲ بهمن پوشش داده شده‌اند
    assert datetime(2026, 3, 21).date() in IRAN_HOLIDAYS
    assert datetime(2026, 4, 1).date() in IRAN_HOLIDAYS
    assert datetime(2027, 2, 11).date() in IRAN_HOLIDAYS


async def _make_task(db: AsyncSession, seeded: dict) -> Task:
    policy = await SlaService(db).create_policy(
        organization_id=seeded["org"].id,
        name="Response 30m",
        priority=Priority.HIGH,
        response_minutes=30,
        warning_minutes=10,
        escalate_on_breach=True,
    )
    task = Task(
        organization_id=seeded["org"].id,
        title="Reply to the buyer",
        owner_id=seeded["reza"].id,
        sla_policy_id=policy.id,
        sla_state=SlaState.ACTIVE,
        created_at=datetime(2026, 3, 20, 10, 0, tzinfo=UTC),  # جمعه/تعطیل
    )
    db.add(task)
    await db.flush()
    return task


async def test_evaluate_task_uses_business_calendar_and_chains_to_manager(
    seeded: dict, db: AsyncSession, monkeypatch
):
    """با پرچم روشن: deadline روی تقویم کاری جابه‌جا می‌شود و زنجیره به manager می‌رسد."""
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(sla_use_business_calendar=True, sla_chain_escalation=True),
    )
    task = await _make_task(db, seeded)
    await db.commit()

    # قبل از موعد کاری: هشدار می‌دهد، نه نقض SLA
    task = await SlaService(db).evaluate_task(task.id, now=datetime(2026, 3, 25, 8, 15, tzinfo=UTC))
    assert task.deadline is not None
    assert task.deadline.replace(tzinfo=UTC) == datetime(2026, 3, 25, 8, 30, tzinfo=UTC)
    assert task.sla_state == SlaState.WARNING

    # بعد از موعد کاری: نقض + ارتقا به manager (reza.manager_id = ali)
    task = await SlaService(db).evaluate_task(task.id, now=datetime(2026, 3, 25, 8, 45, tzinfo=UTC))
    assert task.sla_state == SlaState.ESCALATED

    rows = (
        (
            await db.execute(
                select(Notification).where(
                    Notification.user_id == seeded["ali"].id,
                    Notification.title == "SLA escalated to you",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].entity_id == task.id


async def test_evaluate_task_keeps_wall_clock_without_flag(
    seeded: dict, db: AsyncSession
):
    """بدون پرچم، رفتار قبلی دست‌نخورده می‌ماند: deadline ذخیره/جابه‌جا نمی‌شود."""
    task = await _make_task(db, seeded)
    await db.commit()

    # موعد خام: جمعه ۱۰:۳۰ → یکشنبه صبح نقض حساب نمی‌شود چون موعد واقعی خام است
    task = await SlaService(db).evaluate_task(task.id, now=datetime(2026, 3, 22, 8, 45, tzinfo=UTC))
    assert task.deadline is None
    # موعد خام ۲۰۲۶-۰۳-۲۰ ۱۰:۳۰ گذشته → نقض
    assert task.sla_state in (SlaState.BREACHED, SlaState.ESCALATED)

    # پرچم پیش‌فرض در تنظیمات همچنان خاموش است
    assert Settings().sla_use_business_calendar is False


async def test_chain_off_notifies_owner_only(seeded: dict, db: AsyncSession, monkeypatch):
    """با خاموش بودن زنجیره (پیش‌فرض) فقط خود مالک اطلاع می‌گیرد."""
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(sla_use_business_calendar=True, sla_chain_escalation=False),
    )
    task = await _make_task(db, seeded)
    await db.commit()
    task = await SlaService(db).evaluate_task(task.id, now=datetime(2026, 3, 25, 8, 45, tzinfo=UTC))
    assert task.sla_state == SlaState.ESCALATED

    manager_notes = (
        await db.execute(select(Notification).where(Notification.user_id == seeded["ali"].id))
    ).scalars().all()
    assert [n for n in manager_notes if n.title == "SLA escalated to you"] == []
    owner_notes = (
        await db.execute(
            select(Notification).where(
                Notification.user_id == seeded["reza"].id,
                Notification.title == "SLA breached — escalated",
            )
        )
    ).scalars().all()
    assert len(owner_notes) == 1
