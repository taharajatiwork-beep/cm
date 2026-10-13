import pytest

from app.perf.services.sync_lock import SyncBusy, begin_sync, finish_sync, sync_status


@pytest.mark.asyncio
async def test_sync_lock_blocks_second_actor(seeded, db):
    org = seeded["org"].id
    user_a = seeded["ali"].id
    user_b = seeded["sara"].id
    await begin_sync(db, org, user_a, "Ali")
    with pytest.raises(SyncBusy):
        await begin_sync(db, org, user_b, "Sara")
    await finish_sync(db, org, ok=True)
    status = await sync_status(db, org)
    assert status["running"] is False
    assert status["result"] == "ok"
