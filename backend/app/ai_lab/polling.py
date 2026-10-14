"""Poll schedule for GitHub result delivery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

POLL_TIMEOUT = timedelta(hours=2)
PHASE_1 = timedelta(minutes=5)
PHASE_2 = timedelta(minutes=30)


def task_age_seconds(created_at: datetime, now: datetime | None = None) -> float:
    now = now or datetime.now(UTC)
    start = created_at.replace(tzinfo=UTC) if created_at.tzinfo is None else created_at
    return max(0.0, (now - start).total_seconds())


def poll_interval_seconds(age_seconds: float) -> int:
    """Seconds until next poll attempt (minimum spacing between polls)."""
    if age_seconds <= PHASE_1.total_seconds():
        return 60
    if age_seconds <= PHASE_2.total_seconds():
        return 300
    if age_seconds <= POLL_TIMEOUT.total_seconds():
        return 900
    return 0


def is_poll_timeout(age_seconds: float) -> bool:
    return age_seconds > POLL_TIMEOUT.total_seconds()


def due_for_poll(
    created_at: datetime,
    last_polled_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(UTC)
    age = task_age_seconds(created_at, now)
    if is_poll_timeout(age):
        return True
    interval = poll_interval_seconds(age)
    if interval <= 0:
        return False
    if last_polled_at is None:
        return True
    last = last_polled_at.replace(tzinfo=UTC) if last_polled_at.tzinfo is None else last_polled_at
    return (now - last).total_seconds() >= interval
