from app.requests.project_title import project_title_without_team_suffix
from app.requests.spine import build_spine_timeline


async def test_request_spine_includes_request_node(seeded, db):
    from app.requests.models import WorkRequest

    req = WorkRequest(
        organization_id=seeded["org"].id,
        code="REQ-TEST",
        title="تست",
        description="",
        kind="عمومی",
        priority="normal",
        status="new",
        requested_by=seeded["ali"].id,
        created_by=seeded["ali"].id,
    )
    db.add(req)
    await db.flush()
    items = await build_spine_timeline(db, seeded["org"].id, request_id=req.id)
    kinds = {row["kind"] for row in items}
    assert "work_request" in kinds


def test_title_helper_still():
    assert project_title_without_team_suffix("a — b", "b") == "a"
