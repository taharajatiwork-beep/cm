"""رگرسیون: «کارهای من» نباید با ددلاین بشکند و باید درست دسته‌بندی کند.

SQLite ددلاین را naive برمی‌گرداند در حالی که `now` آگاه است؛ مقایسهٔ مستقیم
TypeError می‌داد و کل endpoint 500 می‌شد.
"""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.permissions import PermissionCode
from app.models import Task, TaskAssignee, User
from app.models.enums import TaskStatus
from tests.conftest import auth, login


async def _owner(db, seeded, email: str, name: str, permissions: list[str]) -> User:
    from app.services import OrgService

    svc = OrgService(db)
    role = await svc.create_role(seeded["org"].id, name, f"{email.split('@')[0]}_role", permissions, "organization")
    user = await svc.create_user(
        organization_id=seeded["org"].id,
        email=email,
        full_name=name,
        password="password",
        role_id=role.id,
        branch_id=seeded["branch"].id,
    )
    await db.commit()
    return user


async def _task(db, *, org_id, owner_id, title: str, deadline: datetime | None, status=TaskStatus.OPEN) -> Task:
    task = Task(
        id=uuid4(),
        organization_id=org_id,
        title=title,
        status=status,
        owner_id=owner_id,
        deadline=deadline,
    )
    db.add(task)
    await db.flush()
    return task


async def test_my_work_with_deadlines_does_not_500(client, seeded, db):
    owner = await _owner(db, seeded, "owner-dl@autoco.example", "مالک ددلاین", [PermissionCode.TASK_READ])
    now = datetime.now(UTC)
    # ددلاین‌های آگاه در دیتابیس؛ بعد از خواندت از SQLite می‌شوند naive
    await _task(db, org_id=seeded["org"].id, owner_id=owner.id, title="دیر شده", deadline=now - timedelta(days=1))
    await _task(db, org_id=seeded["org"].id, owner_id=owner.id, title="امروز", deadline=now + timedelta(hours=3))
    await _task(db, org_id=seeded["org"].id, owner_id=owner.id, title="آینده", deadline=now + timedelta(days=5))
    await _task(db, org_id=seeded["org"].id, owner_id=owner.id, title="بدون ددلاین", deadline=None)
    await db.commit()

    headers = auth(await login(client, "owner-dl@autoco.example"))
    res = await client.get("/requests/my-work", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    titles = {name: [t["title"] for t in items] for name, items in body.items() if isinstance(items, list)}
    assert "دیر شده" in titles.get("overdue", [])
    assert "امروز" in titles.get("today", [])
    assert "آینده" in titles.get("later", [])
    assert "بدون ددلاین" in titles.get("later", [])


async def test_my_work_assignee_with_deadline_does_not_500(client, seeded, db):
    owner = await _owner(db, seeded, "owner-as@autoco.example", "مالک محول", [PermissionCode.TASK_READ])
    assignee = await _owner(db, seeded, "assignee-dl@autoco.example", "محول‌شده", [PermissionCode.TASK_READ])
    now = datetime.now(UTC)
    task = await _task(db, org_id=seeded["org"].id, owner_id=owner.id, title="کار محول‌شده", deadline=now - timedelta(hours=2))
    db.add(TaskAssignee(task_id=task.id, user_id=assignee.id))
    await db.commit()

    headers = auth(await login(client, "assignee-dl@autoco.example"))
    res = await client.get("/requests/my-work", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert "کار محول‌شده" in [t["title"] for t in body.get("overdue", [])]


async def test_my_work_completed_with_deadline_is_excluded(client, seeded, db):
    owner = await _owner(db, seeded, "owner-done@autoco.example", "مالک انجام‌شده", [PermissionCode.TASK_READ])
    now = datetime.now(UTC)
    await _task(
        db,
        org_id=seeded["org"].id,
        owner_id=owner.id,
        title="انجام‌شده",
        deadline=now - timedelta(days=2),
        status=TaskStatus.COMPLETED,
    )
    await db.commit()

    headers = auth(await login(client, "owner-done@autoco.example"))
    res = await client.get("/requests/my-work", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    all_titles = [t["title"] for items in body.values() if isinstance(items, list) for t in items]
    assert "انجام‌شده" not in all_titles
