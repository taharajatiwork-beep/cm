"""Targeted coverage for hybrid_rag fallbacks, enterprise_ops helpers, pagination, notifications, assignment, worker."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.pagination import decode_cursor, encode_cursor, page
from app.core.permissions import PermissionCode
from app.models.enums import NotificationChannel, VehicleStatus
from app.models.inventory import Vehicle
from app.services.enterprise_ops import EnterpriseService, notify_current_approver
from app.services.hybrid_rag import (
    AnalyzedQuery,
    FusedHit,
    HybridRagService,
    QueryAnalyzer,
)
from app.services.notifications import notify

# --------------------------------------------------------------------- pagination


def test_pagination_encode_decode_and_page():
    assert decode_cursor(None) is None
    assert decode_cursor("") is None
    assert decode_cursor("!!!not-b64!!!") is None
    token = encode_cursor("10")
    assert decode_cursor(token) == "10"
    items = list(range(25))
    first = page(items, cursor=None, limit=10)
    assert first["total"] == 25
    assert first["items"] == list(range(10))
    assert first["next_cursor"]
    second = page(items, cursor=first["next_cursor"], limit=10)
    assert second["items"] == list(range(10, 20))
    last = page(items, cursor=second["next_cursor"], limit=10)
    assert last["items"] == list(range(20, 25))
    assert last["next_cursor"] is None
    # non-digit cursor starts at 0; limit clamped
    assert page(items, cursor=encode_cursor("abc"), limit=1000)["items"] == list(range(25))


# --------------------------------------------------------------------- hybrid_rag


def test_query_analyzer_case_policy_and_semantic():
    a = QueryAnalyzer().analyze("Open case C-123 for پیگیری")
    assert a.case_number == "C-123"
    assert "case" in a.entity_types
    pol = QueryAnalyzer().analyze("What is the sales policy SOP قانون؟")
    assert pol.wants_policy
    assert "document" in pol.entity_types
    sem = QueryAnalyzer().analyze("hi")
    assert sem.intent == "semantic"


def test_hybrid_extractive_and_context_branches():
    svc = HybridRagService.__new__(HybridRagService)
    case_hit = FusedHit(
        entity_type="case",
        entity_id=uuid4(),
        title="C-100",
        content="x" * 600,
        sources=["sql", "exact"],
        score=1.0,
        metadata={},
    )
    analyzed = AnalyzedQuery(
        raw="C-100",
        intent="lookup",
        case_number="C-100",
        free_text="C-100",
    )
    ans = svc._extractive_answer(analyzed, [case_hit], "")
    assert "C-100" in ans
    assert "پیدا شد" in ans

    generic = AnalyzedQuery(raw="what about ops", intent="semantic", free_text="what about ops")
    long_ans = svc._extractive_answer(generic, [case_hit], "")
    assert "…" in long_ans or "منبع" in long_ans

    empty = svc._extractive_answer(analyzed, [], "")
    assert "پیدا نشد" in empty

    reserved = FusedHit(
        entity_type="vehicle",
        entity_id=uuid4(),
        title="Camry",
        content="ok",
        sources=["sql", "text"],
        score=1.0,
        metadata={"status": "RESERVED", "stock_number": "9", "year": 2020, "vin": "V"},
    )
    status_q = AnalyzedQuery(
        raw="موجود؟",
        intent="lookup",
        wants_status=True,
        brand="Toyota",
        model="Camry",
        free_text="Toyota Camry",
    )
    assert "رزرو" in svc._extractive_answer(status_q, [reserved], "")

    # context truncation
    big = FusedHit(
        entity_type="document",
        entity_id=uuid4(),
        title="doc",
        content="body" * 50,
        sources=["vector"],
        score=1.0,
    )
    ctx = svc._build_context([big, big], limit=40)
    assert len(ctx) <= 40 or ctx == ""


@pytest.mark.asyncio
async def test_hybrid_llm_answer_paths(db: AsyncSession, seeded, monkeypatch):
    svc = HybridRagService(db)
    hit = FusedHit(
        entity_type="vehicle",
        entity_id=uuid4(),
        title="Elantra",
        content="IN_STOCK",
        sources=["sql"],
        score=2.0,
        metadata={"status": "IN_STOCK"},
    )
    analyzed = AnalyzedQuery(raw="النترا؟", intent="lookup", model="Elantra", free_text="Elantra")

    class OkClient:
        async def chat_text(self, **_kwargs):
            return "جواب LLM"

    monkeypatch.setattr("app.ai.llm.get_llm_client", lambda: OkClient())
    text, mode = await svc._answer(analyzed, [hit], "ctx")
    assert mode == "llm"
    assert "جواب LLM" in text
    assert "منابع" in text

    class EmptyClient:
        async def chat_text(self, **_kwargs):
            return "  "

    monkeypatch.setattr("app.ai.llm.get_llm_client", lambda: EmptyClient())
    text2, mode2 = await svc._answer(analyzed, [hit], "ctx")
    assert mode2 == "extractive"

    class BoomClient:
        async def chat_text(self, **_kwargs):
            raise RuntimeError("llm down")

    monkeypatch.setattr("app.ai.llm.get_llm_client", lambda: BoomClient())
    text3, mode3 = await svc._answer(analyzed, [hit], "ctx")
    assert mode3 == "extractive"
    assert "llm down" in text3.lower() or "LLM" in text3

    monkeypatch.setattr("app.ai.llm.get_llm_client", lambda: None)
    text4, mode4 = await svc._answer(analyzed, [hit], "ctx")
    assert mode4 == "extractive"
    assert text4


@pytest.mark.asyncio
async def test_hybrid_vehicle_inventory_fallback(db: AsyncSession, seeded, monkeypatch):
    vehicle = Vehicle(
        organization_id=seeded["org"].id,
        vin="KMHD84LF5JU777001",
        brand="Hyundai",
        model="Tucson",
        year=2022,
        stock_number="7701",
        status=VehicleStatus.IN_STOCK,
        branch_id=seeded["branch"].id,
    )
    db.add(vehicle)
    await db.flush()

    async def empty_search(self, **_kwargs):
        return []

    async def empty_vector(self, **_kwargs):
        return []

    monkeypatch.setattr("app.services.search.SearchService.search", empty_search)
    monkeypatch.setattr("app.services.rag.RagService.semantic_search", empty_vector)

    perms = {
        PermissionCode.RAG_READ,
        PermissionCode.SEARCH,
        PermissionCode.INVENTORY_READ,
    }
    result = await HybridRagService(db).run(
        organization_id=seeded["org"].id,
        query="Hyundai Tucson موجود است؟",
        actor_permissions=perms,
        top_k=5,
    )
    assert result.hits
    assert any(h.entity_type == "vehicle" for h in result.hits)
    assert result.answer


@pytest.mark.asyncio
async def test_hybrid_rerank_boosts(db: AsyncSession, seeded):
    svc = HybridRagService(db)
    vid = uuid4()
    hits = [
        FusedHit(
            entity_type="vehicle",
            entity_id=vid,
            title="Toyota Camry",
            content="vin ABC stock 55",
            sources=["sql", "exact", "vector"],
            score=1.0,
            metadata={"vin": "ABC1234567890", "stock_number": "55"},
        ),
        FusedHit(
            entity_type="document",
            entity_id=uuid4(),
            title="policy",
            content="rules",
            sources=["vector"],
            score=1.0,
            metadata={},
        ),
    ]
    analyzed = AnalyzedQuery(
        raw="Toyota Camry status ABC1234567890 #55",
        intent="lookup",
        brand="Toyota",
        model="Camry",
        vin="ABC1234567890",
        stock_number="55",
        wants_status=True,
        free_text="Toyota Camry",
    )
    ranked = svc._rerank(hits, analyzed)
    assert ranked[0].entity_id == vid
    assert ranked[0].score > 1.0


# --------------------------------------------------------------------- enterprise_ops


@pytest.mark.asyncio
async def test_enterprise_list_audit_filters(db: AsyncSession, seeded):
    from app.services import write_audit

    ali = seeded["ali"]
    await write_audit(
        db,
        organization_id=ali.organization_id,
        actor_id=ali.id,
        action="test.action",
        entity_type="demo",
        entity_id=uuid4(),
    )
    svc = EnterpriseService(db)
    perms = {PermissionCode.EVENT_READ}
    rows = await svc.list_audit(
        ali.organization_id,
        actor_permissions=perms,
        actor_id=ali.id,
        entity_type="demo",
        action="test.action",
        day=datetime.now(UTC).date().isoformat(),
    )
    assert any(r.action == "test.action" for r in rows)
    with pytest.raises(ValueError, match="bad day"):
        await svc.list_audit(
            ali.organization_id,
            actor_permissions=perms,
            day="not-a-day",
        )


@pytest.mark.asyncio
async def test_enterprise_decide_errors_and_reject(db: AsyncSession, seeded):
    svc = EnterpriseService(db)
    org_id = seeded["org"].id
    req = await svc.request_approval(
        organization_id=org_id,
        requester_id=seeded["reza"].id,
        kind="discount",
        title="t",
        payload={},
        approver_ids=[seeded["ali"].id, seeded["sara"].id],
    )
    with pytest.raises(ValueError, match="not found"):
        await svc.decide(
            organization_id=org_id,
            request_id=uuid4(),
            actor_id=seeded["ali"].id,
            decision="approved",
        )
    with pytest.raises(ValueError, match="approver"):
        await svc.decide(
            organization_id=org_id,
            request_id=req.id,
            actor_id=seeded["sara"].id,
            decision="approved",
        )
    rejected = await svc.decide(
        organization_id=org_id,
        request_id=req.id,
        actor_id=seeded["ali"].id,
        decision="rejected",
        comment="no",
    )
    assert rejected.status == "rejected"
    with pytest.raises(ValueError, match="already"):
        await svc.decide(
            organization_id=org_id,
            request_id=req.id,
            actor_id=seeded["ali"].id,
            decision="approved",
        )


@pytest.mark.asyncio
async def test_enterprise_membership_schedule_quota_status(db: AsyncSession, seeded, monkeypatch):
    svc = EnterpriseService(db)
    org_id = seeded["org"].id
    with pytest.raises(ValueError, match="User not found"):
        await svc.add_team_membership(org_id, uuid4(), seeded["sales_team"].id)
    row = await svc.add_team_membership(org_id, seeded["reza"].id, seeded["sales_team"].id)
    assert row.user_id == seeded["reza"].id

    sched = await svc.schedule_report(org_id, "weekly", "email", 9)
    assert sched.name == "weekly"

    monkeypatch.setenv("AI_DAILY_TOKEN_QUOTA", "100000")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        await svc.record_ai_usage(org_id, seeded["ali"].id, "gpt-test", 3, 4)
    finally:
        monkeypatch.delenv("AI_DAILY_TOKEN_QUOTA", raising=False)
        get_settings.cache_clear()

    missing = await svc.get_approval_status(uuid4(), seeded["ali"].id)
    assert missing["status"] == "not_found"

    req = await svc.request_approval(
        organization_id=org_id,
        requester_id=seeded["reza"].id,
        kind="x",
        title="y",
        payload={},
        approver_ids=[seeded["ali"].id],
    )
    status = await svc.get_approval_status(req.id, seeded["ali"].id)
    assert status["status"] == "pending"
    assert status["is_current_approver"] is True
    assert status["current_approver_id"] == str(seeded["ali"].id)


@pytest.mark.asyncio
async def test_notify_current_approver_no_step(db: AsyncSession, seeded):
    from app.models.enterprise import ApprovalRequest

    # requester linked but no ApprovalStep rows → early return at step lookup
    from app.models.telegram import TelegramAccount

    db.add(
        TelegramAccount(
            organization_id=seeded["org"].id,
            user_id=seeded["reza"].id,
            provider="telegram",
            telegram_user_id=999001,
            telegram_chat_id=999001,
        )
    )
    approval = ApprovalRequest(
        organization_id=seeded["org"].id,
        kind="x",
        title="orphan",
        payload_json="{}",
        requester_id=seeded["reza"].id,
        current_step=3,
    )
    db.add(approval)
    await db.flush()
    await notify_current_approver(db, approval)  # should no-op


# --------------------------------------------------------------------- notifications


@pytest.mark.asyncio
async def test_notify_event_branches(db: AsyncSession, seeded):
    org_id = seeded["org"].id
    uid = seeded["ali"].id
    tid = uuid4()
    await notify(
        db,
        organization_id=org_id,
        user_id=uid,
        title="Task done",
        body="finished",
        entity_type="task",
        entity_id=tid,
    )
    await notify(
        db,
        organization_id=org_id,
        user_id=uid,
        title="SLA breach late",
        body="overdue",
        entity_type="task",
        entity_id=tid,
    )
    await notify(
        db,
        organization_id=org_id,
        user_id=uid,
        title="Branch note",
        body="hello",
        entity_type="case",
        entity_id=uuid4(),
    )
    await notify(
        db,
        organization_id=org_id,
        user_id=uid,
        title="New message",
        body="ping",
        entity_type="message",
        entity_id=uuid4(),
        channel=NotificationChannel.WEB,
    )
    await notify(
        db,
        organization_id=org_id,
        user_id=uid,
        title="Generic",
        body="x",
    )


# --------------------------------------------------------------------- assignment


@pytest.mark.asyncio
async def test_assignment_recommend_and_skills(db: AsyncSession, seeded):
    from app.services.assignment import AssignmentEngine

    engine = AssignmentEngine(db)
    skill = await engine.add_skill(seeded["reza"].id, "sales", level=2)
    assert skill.skill_code == "sales"
    again = await engine.add_skill(seeded["reza"].id, "sales", level=3)
    assert again.level == 3

    rec = await engine.recommend(
        organization_id=seeded["org"].id,
        actor_permissions={PermissionCode.TASK_ASSIGN, PermissionCode.ORG_ADMIN},
        branch_id=seeded["branch"].id,
        role_code="seller",
        required_skills=["sales"],
        related_user_id=seeded["ali"].id,
        limit=5,
    )
    assert rec.filters_applied["role_code"] == "seller"
    assert isinstance(rec.candidates, list)


# --------------------------------------------------------------------- files


def test_files_local_save_read_and_reject(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.core.files import UploadRejected, read_upload, save_upload

    monkeypatch.setenv("FILE_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("FILE_BACKEND", "local")
    get_settings.cache_clear()
    try:
        path = save_upload("fleet.csv", "text/csv", b"a,b\n1,2\n")
        assert path.exists()
        data = read_upload(str(path))
        assert data.startswith(b"a,b")
        with pytest.raises(UploadRejected):
            save_upload("evil.exe", "application/octet-stream", b"MZ")
        monkeypatch.setenv("UPLOAD_MAX_BYTES", "4")
        get_settings.cache_clear()
        with pytest.raises(UploadRejected):
            save_upload("big.csv", "text/csv", b"12345")
    finally:
        monkeypatch.delenv("FILE_STORAGE_DIR", raising=False)
        monkeypatch.delenv("FILE_BACKEND", raising=False)
        monkeypatch.delenv("UPLOAD_MAX_BYTES", raising=False)
        get_settings.cache_clear()


# --------------------------------------------------------------------- adapter notify + worker external


@pytest.mark.asyncio
async def test_adapter_notify_user(db: AsyncSession, seeded):
    from app.integrations.telegram.adapter import TelegramAdapter
    from app.integrations.telegram.client import FakeTelegramClient
    from app.models.telegram import TelegramAccount

    client = FakeTelegramClient()
    adapter = TelegramAdapter(db, client=client)
    assert await adapter.notify_user(seeded["ali"].id, "hi") is False

    db.add(
        TelegramAccount(
            organization_id=seeded["org"].id,
            user_id=seeded["ali"].id,
            provider="telegram",
            telegram_user_id=42,
            telegram_chat_id=42,
        )
    )
    await db.flush()
    assert await adapter.notify_user(seeded["ali"].id, "ping") is True
    assert client.sent


@pytest.mark.asyncio
async def test_run_external_worker_paths(monkeypatch):
    import asyncio

    from app import worker as worker_mod

    monkeypatch.setattr(worker_mod, "try_acquire_db_lock", AsyncMock(return_value=None))
    with pytest.raises(SystemExit, match="another worker"):
        await worker_mod.run_external_worker()

    async def acquire(name, ttl_seconds=3600):
        return "owner-1"

    class FakeWorker:
        def __init__(self, *_a, **_k):
            pass

        async def start(self):
            return None

        async def stop(self):
            return None

    class _Sess:
        async def commit(self):
            return None

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return _Sess()

        async def __aexit__(self, *args):
            return None

    sleeps = {"n": 0}

    async def fake_sleep(_s):
        sleeps["n"] += 1
        if sleeps["n"] >= 1:
            raise asyncio.CancelledError()

    monkeypatch.setattr(worker_mod, "try_acquire_db_lock", acquire)
    monkeypatch.setattr(worker_mod, "Worker", FakeWorker)
    monkeypatch.setattr(worker_mod, "AsyncSessionLocal", _Factory())
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr("app.core.logging.setup_logging", lambda: None)
    monkeypatch.setattr("app.core.locks.release_lock", AsyncMock())
    monkeypatch.setattr("app.core.locks.try_lock", AsyncMock(return_value=None))

    with pytest.raises(asyncio.CancelledError):
        await worker_mod.run_external_worker()


@pytest.mark.asyncio
async def test_enterprise_kpis(db: AsyncSession, seeded):
    data = await EnterpriseService(db).kpis(seeded["org"].id)
    assert set(data) >= {"open_tasks", "vehicles", "cases", "work_items"}


@pytest.mark.asyncio
async def test_hybrid_fuses_vector_into_sql_hit(db: AsyncSession, seeded, monkeypatch):
    """Same entity in SQL + vector → merge sources/content (hybrid_rag 384–393)."""
    from app.services.rag import RetrievalHit
    from app.services.search import SearchEntityType, SearchHit

    vid = uuid4()

    async def sql_hits(self, **_kwargs):
        return [
            SearchHit(
                entity_type=SearchEntityType.VEHICLE,
                entity_id=vid,
                title="Camry short",
                subtitle="short",
                score=5.0,
                match_kind="exact",
                metadata={"vin": "X", "status": "IN_STOCK"},
            )
        ]

    async def vec_hits(self, **_kwargs):
        return [
            RetrievalHit(
                embedding_id=uuid4(),
                entity_type="vehicle",
                entity_id=vid,
                chunk_id="c1",
                content="much longer vector content about the Camry inventory status",
                score=0.9,
                metadata={"title": "Camry vector"},
            ),
            RetrievalHit(
                embedding_id=uuid4(),
                entity_type="document",
                entity_id=uuid4(),
                chunk_id="c2",
                content="solo vector doc",
                score=0.5,
                metadata={},
            ),
        ]

    monkeypatch.setattr("app.services.search.SearchService.search", sql_hits)
    monkeypatch.setattr("app.services.rag.RagService.semantic_search", vec_hits)

    result = await HybridRagService(db).run(
        organization_id=seeded["org"].id,
        query="Camry status please tell me",
        actor_permissions={
            PermissionCode.RAG_READ,
            PermissionCode.SEARCH,
            PermissionCode.INVENTORY_READ,
        },
        top_k=5,
    )
    vehicle_hits = [h for h in result.hits if h.entity_id == vid]
    assert vehicle_hits
    assert "vector" in vehicle_hits[0].sources
    assert "exact" in vehicle_hits[0].sources or "sql" in vehicle_hits[0].sources
    assert "longer" in vehicle_hits[0].content


@pytest.mark.asyncio
async def test_notify_enqueue_failure_swallowed(db: AsyncSession, seeded, monkeypatch):
    """Telegram enqueue failure must not break notify() (lines 106–108)."""

    async def boom(*_a, **_k):
        raise RuntimeError("enqueue failed")

    monkeypatch.setattr(
        "app.integrations.telegram.outbox.enqueue_telegram",
        boom,
    )
    n = await notify(
        db,
        organization_id=seeded["org"].id,
        user_id=seeded["ali"].id,
        title="Task assigned",
        body="still ok",
        entity_type="task",
        entity_id=uuid4(),
    )
    assert n.id is not None


def test_files_relative_read(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.core.files import read_upload, save_upload

    monkeypatch.setenv("FILE_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("FILE_BACKEND", "local")
    get_settings.cache_clear()
    try:
        path = save_upload("note.txt", "text/plain", b"hello")
        data = read_upload(path.name)
        assert data == b"hello"
    finally:
        monkeypatch.delenv("FILE_STORAGE_DIR", raising=False)
        monkeypatch.delenv("FILE_BACKEND", raising=False)
        get_settings.cache_clear()


def test_files_s3_paths_mocked(monkeypatch):
    from app.core import files as files_mod
    from app.core.config import get_settings

    monkeypatch.setenv("FILE_BACKEND", "s3")
    monkeypatch.setenv("S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("S3_BUCKET", "cm-test")
    monkeypatch.setenv("S3_ACCESS_KEY", "x")
    monkeypatch.setenv("S3_SECRET_KEY", "y")
    get_settings.cache_clear()

    class FakeBody:
        def read(self):
            return b"s3-bytes"

    class FakeClient:
        def __init__(self):
            self.created = False

        def head_bucket(self, Bucket):
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "404", "Message": "no"}}, "HeadBucket")

        def create_bucket(self, Bucket):
            self.created = True

        def put_object(self, **_kwargs):
            return None

        def get_object(self, **_kwargs):
            return {"Body": FakeBody()}

    client = FakeClient()
    monkeypatch.setattr(files_mod, "_client", lambda: client)
    try:
        path = files_mod.save_upload("a.csv", "text/csv", b"1,2\n")
        assert client.created
        assert files_mod.read_upload(str(path)) == b"s3-bytes"
    finally:
        for key in ("FILE_BACKEND", "S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
            monkeypatch.delenv(key, raising=False)
        get_settings.cache_clear()
