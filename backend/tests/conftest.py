import os
from collections.abc import AsyncGenerator

# Force deterministic planners in tests (ignore developer .env LLM settings)
os.environ["LLM_PROVIDER"] = "rules"
os.environ["DIVAR_MODE"] = "fake"
os.environ["REQUIRE_HUMAN_APPROVAL_FOR_SENSITIVE_AI"] = "false"
os.environ["APP_ENV"] = "development"
os.environ["TELEGRAM_MODE"] = "off"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["BALE_MODE"] = "off"
# Never touch real outside systems from tests (Google Sheets, Mizito).
# Without this, the repo-root .env is read and tests write to the live sheets.
for _name in (
    "PERF_SHEETS_SPREADSHEET_ID",
    "PERF_SHEETS_CREDENTIALS_FILE",
    "PERF_SHEETS_COST_TRACKING_ID",
    "PERF_SHEETS_REGISTER_CAMPAIGN_ID",
    "PERF_SHEETS_REPORTER_ID",
    "PERF_SHEETS_WEBHOOK",
    "PERF_MIZITO_TOKEN",
    "PERF_MIZITO_WORKSPACE_ID",
    "PERF_MIZITO_TASK_BOARDS",
    "PERF_MIZITO_REQUESTER_IDS",
    "PERF_MIZITO_IGNORE_IDS",
):
    os.environ[_name] = ""


def _test_database_url() -> str:
    raw = (
        os.environ.get("POSTGRES_TEST_URL")
        or os.environ.get("TEST_DATABASE_URL")
        or "postgresql+asyncpg://cm:cm@localhost:5432/cm_test"
    )
    if raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw.startswith("sqlite"):
        raise RuntimeError("Tests require PostgreSQL. Start docker compose postgres.")
    return raw


os.environ["DATABASE_URL"] = _test_database_url()

from scripts.ensure_pg_db import ensure_database  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine as _create_engine  # noqa: E402

ensure_database(os.environ["DATABASE_URL"])


def _bootstrap_schema() -> None:
    import asyncio

    from app import models as _models  # noqa: F401
    from app.db.base import Base as _Base

    async def _run() -> None:
        engine = _create_engine(os.environ["DATABASE_URL"], echo=False)
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(_Base.metadata.drop_all)
            await conn.run_sync(_Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_run())


_bootstrap_schema()

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import models  # noqa: F401
from app.core.config import get_settings
from app.core.permissions import PermissionCode
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.enums import RelationshipType
from app.services import OrgService


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """بعد از هر تست، کش تنظیمات پاک می‌شود.

    بدون این، تستی که `REQUIRE_HUMAN_APPROVAL_FOR_SENSITIVE_AI=true` ست می‌کند
    تنظیمات را کش می‌کند؛ monkeypatch env را برمی‌گردارد ولی کش همچنان `true`
    می‌ماند و تست‌های بعدی (که حاکمیت AI را خاموش فرض می‌کنند) شکست می‌خورند.
    """
    yield
    get_settings.cache_clear()


async def _truncate_public(engine) -> None:
    names = [table.fullname for table in reversed(Base.metadata.sorted_tables)]
    if not names:
        return
    quoted = ", ".join(f'"{n}"' if "." not in n else n for n in names)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def clean_db(db_engine):
    await _truncate_public(db_engine)
    yield


@pytest_asyncio.fixture
async def db(clean_db, db_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.commit()


@pytest_asyncio.fixture
async def client(clean_db, db_engine) -> AsyncGenerator[AsyncClient, None]:
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded(db: AsyncSession):
    """Org with manager (Ali), seller (Reza), marketing (Sara), branch, teams."""
    svc = OrgService(db)
    org = await svc.create_organization("AutoCo", "autoco")
    branch = await svc.create_branch(org.id, "Tehran", "THR", city="Tehran")
    sales_dept = await svc.create_department(org.id, "Sales", "SALES")
    mkt_dept = await svc.create_department(org.id, "Marketing", "MKT")
    sales_team = await svc.create_team(org.id, "Sales Team", "SALES_T", sales_dept.id)
    mkt_team = await svc.create_team(org.id, "Marketing Team", "MKT_T", mkt_dept.id)

    from app.core.permissions import admin_role_permission_codes

    admin_role = await svc.create_role(
        org.id, "Admin", "admin", admin_role_permission_codes(), "organization"
    )
    manager_role = await svc.create_role(
        org.id,
        "Manager",
        "manager",
        [
            PermissionCode.USER_READ,
            PermissionCode.USER_WRITE,
            PermissionCode.RELATIONSHIP_WRITE,
            PermissionCode.CONVERSATION_READ,
            PermissionCode.CONVERSATION_WRITE,
            PermissionCode.WORK_ITEM_READ,
            PermissionCode.WORK_ITEM_WRITE,
            PermissionCode.CASE_READ,
            PermissionCode.CASE_WRITE,
            PermissionCode.TASK_READ,
            PermissionCode.TASK_WRITE,
            PermissionCode.TASK_ASSIGN,
            PermissionCode.TASK_DELEGATE,
            PermissionCode.NOTIFICATION_READ,
            PermissionCode.EVENT_READ,
            PermissionCode.SLA_MANAGE,
            PermissionCode.INVENTORY_READ,
            PermissionCode.INVENTORY_WRITE,
            PermissionCode.SEARCH,
            PermissionCode.RAG_READ,
            PermissionCode.RAG_INDEX,
            PermissionCode.AGENT_RUN,
            PermissionCode.KB_READ,
            PermissionCode.KB_WRITE,
            PermissionCode.CUSTOMER_READ,
            PermissionCode.CUSTOMER_WRITE,
            PermissionCode.CAMPAIGN_READ,
            PermissionCode.CAMPAIGN_WRITE,
        ],
        "branch",
    )
    seller_role = await svc.create_role(
        org.id,
        "Seller",
        "seller",
        [
            PermissionCode.CONVERSATION_READ,
            PermissionCode.CONVERSATION_WRITE,
            PermissionCode.WORK_ITEM_READ,
            PermissionCode.CASE_READ,
            PermissionCode.TASK_READ,
            PermissionCode.TASK_WRITE,
            PermissionCode.NOTIFICATION_READ,
            PermissionCode.INVENTORY_READ,
            PermissionCode.SEARCH,
            PermissionCode.RAG_READ,
            PermissionCode.KB_READ,
            PermissionCode.CUSTOMER_READ,
            PermissionCode.CAMPAIGN_READ,
        ],
        "team",
    )
    mkt_role = await svc.create_role(
        org.id,
        "Marketing",
        "marketing",
        [
            PermissionCode.CONVERSATION_READ,
            PermissionCode.CONVERSATION_WRITE,
            PermissionCode.WORK_ITEM_READ,
            PermissionCode.CASE_READ,
            PermissionCode.TASK_READ,
            PermissionCode.TASK_WRITE,
            PermissionCode.NOTIFICATION_READ,
            PermissionCode.INVENTORY_READ,
            PermissionCode.SEARCH,
            PermissionCode.RAG_READ,
            PermissionCode.KB_READ,
            PermissionCode.CAMPAIGN_READ,
            PermissionCode.CAMPAIGN_WRITE,
        ],
        "team",
    )
    limited_role = await svc.create_role(
        org.id,
        "Viewer",
        "viewer",
        [PermissionCode.WORK_ITEM_READ],
        "self",
    )

    ali = await svc.create_user(
        organization_id=org.id,
        email="ali@autoco.example",
        full_name="Ali Manager",
        password="password",
        role_id=manager_role.id,
        branch_id=branch.id,
        department_id=sales_dept.id,
    )
    reza = await svc.create_user(
        organization_id=org.id,
        email="reza@autoco.example",
        full_name="Reza Seller",
        password="password",
        role_id=seller_role.id,
        branch_id=branch.id,
        department_id=sales_dept.id,
        team_id=sales_team.id,
        manager_id=ali.id,
    )
    sara = await svc.create_user(
        organization_id=org.id,
        email="sara@autoco.example",
        full_name="Sara Marketing",
        password="password",
        role_id=mkt_role.id,
        branch_id=branch.id,
        department_id=mkt_dept.id,
        team_id=mkt_team.id,
        manager_id=ali.id,
    )
    viewer = await svc.create_user(
        organization_id=org.id,
        email="viewer@autoco.example",
        full_name="Limited Viewer",
        password="password",
        role_id=limited_role.id,
        branch_id=branch.id,
    )
    await svc.add_relationship(org.id, ali.id, reza.id, RelationshipType.MANAGES, ali.id)
    await svc.add_relationship(org.id, reza.id, ali.id, RelationshipType.REPORTS_TO, reza.id)
    await svc.add_relationship(
        org.id, reza.id, sara.id, RelationshipType.COLLABORATES_WITH, ali.id
    )
    await db.commit()
    return {
        "org": org,
        "branch": branch,
        "sales_team": sales_team,
        "mkt_team": mkt_team,
        "ali": ali,
        "reza": reza,
        "sara": sara,
        "viewer": viewer,
        "admin_role": admin_role,
        "manager_role": manager_role,
    }


async def login(client: AsyncClient, email: str) -> str:
    r = await client.post(
        "/auth/login",
        json={"organization_slug": "autoco", "email": email, "password": "password"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
