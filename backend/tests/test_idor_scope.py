"""پوشش رگرسیون IDOR: هر endpoint که شناسهٔ موجودیت می‌گیرد باید سطر را
در محدودهٔ سازمان درخواست‌کننده حل کند و برای سازمان دیگر ۴۰۴ بدهد.

الگو: کاربر A (سازمان ۲) به موجودیت سازمان ۱ دسترسی می‌خواهد → ۴۰۴؛
کاربر مجاز همان سازمان → ۲۰۰.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import PermissionCode
from app.models.enums import CaseType, Channel, Priority, VehicleStatus
from app.services import CommunicationService, OrgService, WorkService
from app.services.inventory import InventoryService

PASSWORD = "password"


@pytest_asyncio.fixture
async def org2(db: AsyncSession, seeded):
    """سازمان دوم با کاربر ادمین مستقل — برای تست مرز بین‌سازمانی."""
    svc = OrgService(db)
    org = await svc.create_organization("BetaCo", "betaco")
    role = await svc.create_role(
        org.id,
        "Admin",
        "admin",
        [p.value for p in PermissionCode],
        "organization",
    )
    boss = await svc.create_user(
        organization_id=org.id,
        email="boss@betaco.example",
        full_name="Beta Boss",
        password=PASSWORD,
        role_id=role.id,
    )
    await db.commit()
    return {"org": org, "boss": boss}


@pytest_asyncio.fixture
async def org2_headers(client, org2):
    r = await client.post(
        "/auth/login",
        json={"organization_slug": "betaco", "email": "boss@betaco.example", "password": PASSWORD},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest_asyncio.fixture
async def org1_headers(client, seeded):
    r = await client.post(
        "/auth/login",
        json={"organization_slug": "autoco", "email": "ali@autoco.example", "password": PASSWORD},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest_asyncio.fixture
async def org1_entities(db: AsyncSession, seeded):
    """موجودیت‌های سازمان ۱: work item، task، conversation، case، vehicle."""
    org_id = seeded["org"].id
    ali = seeded["ali"]
    reza = seeded["reza"]
    work = WorkService(db)
    wi = await work.create_work_item(
        organization_id=org_id,
        title="Org1 WI",
        owner_id=ali.id,
    )
    task = await work.create_task(
        organization_id=org_id,
        title="Org1 Task",
        owner_id=ali.id,
        assignee_ids=[reza.id],
    )
    conv = await CommunicationService(db).create_conversation(
        organization_id=org_id,
        channel=Channel.WEB,
        participant_ids=[ali.id],
        topic="Org1 conv",
    )
    case = await work.create_case(
        organization_id=org_id,
        subject="Org1 Case",
        case_type=CaseType.FOLLOW_UP,
        created_by=ali.id,
        owner_id=reza.id,
        priority=Priority.MEDIUM,
    )
    vehicle = await InventoryService(db).create_vehicle(
        organization_id=org_id,
        vin="VIN-IDOR-0001",
        brand="Toyota",
        model="Camry",
        year=2024,
        actor_id=ali.id,
        status=VehicleStatus.IN_STOCK,
    )
    await db.commit()
    return {
        "wi": wi,
        "task": task,
        "conv": conv,
        "case": case,
        "vehicle": vehicle,
        "ali": ali,
        "reza": reza,
    }


def _id(obj) -> str:
    return str(obj.id)


class TestConversationMessages:
    @pytest.mark.asyncio
    async def test_cross_org_messages_is_404(self, client, org1_entities, org2_headers):
        r = await client.get(f"/conversations/{_id(org1_entities['conv'])}/messages", headers=org2_headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_same_org_messages_is_200(self, client, org1_entities, org1_headers):
        r = await client.get(f"/conversations/{_id(org1_entities['conv'])}/messages", headers=org1_headers)
        assert r.status_code == 200


class TestWorkItemProgress:
    @pytest.mark.asyncio
    async def test_cross_org_progress_is_404(self, client, org1_entities, org2_headers):
        r = await client.get(f"/work-items/{_id(org1_entities['wi'])}/progress", headers=org2_headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_same_org_progress_is_200(self, client, org1_entities, org1_headers):
        r = await client.get(f"/work-items/{_id(org1_entities['wi'])}/progress", headers=org1_headers)
        assert r.status_code == 200


class TestWorkItemParticipants:
    @pytest.mark.asyncio
    async def test_cross_org_add_participant_is_404(self, client, org1_entities, org2_headers):
        r = await client.post(
            f"/work-items/{_id(org1_entities['wi'])}/participants",
            headers=org2_headers,
            json={"user_id": str(org1_entities["reza"].id)},
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_same_org_add_participant_is_200(self, client, org1_entities, org1_headers):
        r = await client.post(
            f"/work-items/{_id(org1_entities['wi'])}/participants",
            headers=org1_headers,
            json={"user_id": str(org1_entities["reza"].id)},
        )
        assert r.status_code == 200, r.text


class TestTaskParticipants:
    @pytest.mark.asyncio
    async def test_cross_org_add_participant_is_404(self, client, org1_entities, org2_headers):
        r = await client.post(
            f"/tasks/{_id(org1_entities['task'])}/participants",
            headers=org2_headers,
            json={"user_id": str(org1_entities["reza"].id)},
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_same_org_add_participant_is_200(self, client, org1_entities, org1_headers):
        r = await client.post(
            f"/tasks/{_id(org1_entities['task'])}/participants",
            headers=org1_headers,
            json={"user_id": str(org1_entities["ali"].id)},
        )
        assert r.status_code == 200, r.text


class TestTaskDelegateAndAssign:
    @pytest.mark.asyncio
    async def test_cross_org_delegate_is_404(self, client, org1_entities, org2_headers):
        r = await client.post(
            f"/tasks/{_id(org1_entities['task'])}/delegate",
            headers=org2_headers,
            json={"to_user_id": str(org1_entities["reza"].id)},
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_org_assign_is_404(self, client, org1_entities, org2_headers):
        r = await client.post(
            f"/tasks/{_id(org1_entities['task'])}/assign",
            headers=org2_headers,
            json={"to_user_id": str(org1_entities["reza"].id)},
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_same_org_delegate_is_200(self, client, org1_entities, org1_headers, seeded):
        r = await client.post(
            f"/tasks/{_id(org1_entities['task'])}/delegate",
            headers=org1_headers,
            json={"to_user_id": str(seeded["sara"].id)},
        )
        assert r.status_code == 200, r.text


class TestTaskComplete:
    @pytest.mark.asyncio
    async def test_cross_org_complete_is_404(self, client, org1_entities, org2_headers):
        r = await client.post(f"/tasks/{_id(org1_entities['task'])}/complete", headers=org2_headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_same_org_complete_is_200(self, client, org1_entities, org1_headers):
        r = await client.post(f"/tasks/{_id(org1_entities['task'])}/complete", headers=org1_headers)
        assert r.status_code == 200, r.text


class TestTaskDependency:
    @pytest.mark.asyncio
    async def test_cross_org_dependency_is_404(self, client, org1_entities, org2, org2_headers, db: AsyncSession):
        other = WorkService(db)
        alien_task = await other.create_task(
            organization_id=org2["org"].id,
            title="Beta Task",
            owner_id=org2["boss"].id,
        )
        await db.commit()
        r = await client.post(
            "/tasks/dependencies",
            headers=org2_headers,
            json={
                "dependent_task_id": str(alien_task.id),
                "prerequisite_task_id": str(org1_entities["task"].id),
            },
        )
        assert r.status_code == 404


class TestSlaEvaluate:
    @pytest.mark.asyncio
    async def test_cross_org_task_sla_is_404(self, client, org1_entities, org2_headers):
        r = await client.post(f"/sla/tasks/{_id(org1_entities['task'])}/evaluate", headers=org2_headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_org_case_sla_is_404(self, client, org1_entities, org2_headers):
        r = await client.post(f"/sla/cases/{_id(org1_entities['case'])}/evaluate", headers=org2_headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_same_org_task_sla_is_200(self, client, org1_entities, org1_headers):
        r = await client.post(f"/sla/tasks/{_id(org1_entities['task'])}/evaluate", headers=org1_headers)
        assert r.status_code == 200, r.text


class TestOrgEndpoints:
    @pytest.mark.asyncio
    async def test_cross_org_relationships_are_hidden(self, client, org1_entities, org2_headers):
        r = await client.get(
            f"/org/users/{_id(org1_entities['reza'])}/relationships", headers=org2_headers
        )
        assert r.status_code == 200
        assert r.json() == []

    @pytest.mark.asyncio
    async def test_cross_org_managers_are_hidden(self, client, org1_entities, org2_headers):
        r = await client.get(f"/org/users/{_id(org1_entities['reza'])}/managers", headers=org2_headers)
        assert r.status_code == 200
        assert r.json() == []

    @pytest.mark.asyncio
    async def test_same_org_managers_are_visible(self, client, org1_entities, org1_headers):
        r = await client.get(f"/org/users/{_id(org1_entities['reza'])}/managers", headers=org1_headers)
        assert r.status_code == 200
        assert len(r.json()) >= 1

    @pytest.mark.asyncio
    async def test_cross_org_team_members_is_404(self, client, seeded, org2_headers):
        r = await client.get(f"/org/teams/{_id(seeded['sales_team'])}/members", headers=org2_headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_same_org_team_members_is_200(self, client, seeded, org1_headers):
        r = await client.get(f"/org/teams/{_id(seeded['sales_team'])}/members", headers=org1_headers)
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_cross_org_reports_are_hidden(self, client, org1_entities, org2_headers):
        r = await client.get(f"/people/{_id(org1_entities['ali'])}/reports", headers=org2_headers)
        assert r.status_code == 200
        assert r.json() == []


class TestInventoryWrite:
    @pytest.mark.asyncio
    async def test_cross_org_change_status_is_404(self, client, org1_entities, org2_headers):
        r = await client.post(
            f"/inventory/vehicles/{_id(org1_entities['vehicle'])}/status",
            headers=org2_headers,
            json={"to_status": "RESERVED"},
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_org_link_branch_is_404(self, client, org1_entities, org2_headers, seeded):
        r = await client.post(
            f"/inventory/vehicles/{_id(org1_entities['vehicle'])}/branches",
            headers=org2_headers,
            json={"branch_id": str(seeded["branch"].id)},
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_same_org_change_status_is_200(self, client, org1_entities, org1_headers):
        r = await client.post(
            f"/inventory/vehicles/{_id(org1_entities['vehicle'])}/status",
            headers=org1_headers,
            json={"to_status": "RESERVED"},
        )
        assert r.status_code == 200, r.text


class TestAssignmentSkills:
    @pytest.mark.asyncio
    async def test_cross_org_add_skill_is_404(self, client, org1_entities, org2_headers):
        r = await client.post(
            f"/assignment/users/{_id(org1_entities['reza'])}/skills",
            headers=org2_headers,
            json={"skill_code": "sales", "level": 2},
        )
        assert r.status_code == 404
