from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.communication_agent import CommunicationAgent
from app.ai.divar_agent import DivarAgent
from app.ai.inventory_agent import InventoryAgent
from app.ai.purchase_agent import PurchaseAgent
from app.ai.sales_agent import SalesAgent
from app.api.deps import AuthContext, get_current_user, handle_authz
from app.core.permissions import AuthorizationError
from app.db.session import get_db

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRequest(BaseModel):
    message: str = Field(min_length=1)


class AgentResponse(BaseModel):
    request_id: str
    ok: bool
    intent: str
    clarification: str | None = None
    message: str
    work_item_id: str | None = None
    task_ids: list[str] = []
    case_id: str | None = None
    tool_trace: list[dict[str, Any]] = []


class InventoryAgentRequest(BaseModel):
    message: str | None = None
    min_days: int | None = Field(default=None, ge=0)
    min_branch_requests: int | None = Field(default=None, ge=1)
    auto_create: bool | None = None


class InventoryAgentResponse(BaseModel):
    request_id: str
    ok: bool
    intent: str
    clarification: str | None = None
    message: str
    opportunities_found: int = 0
    cases_created: list[str] = []
    work_item_ids: list[str] = []
    tool_trace: list[dict[str, Any]] = []


class SalesAgentRequest(BaseModel):
    message: str | None = None
    stale_days: int | None = Field(default=None, ge=0)
    auto_create: bool | None = None
    case_id: str | None = None


class SalesAgentResponse(BaseModel):
    request_id: str
    ok: bool
    intent: str
    clarification: str | None = None
    message: str
    follow_ups_found: int = 0
    cases_created: list[str] = []
    work_item_ids: list[str] = []
    task_ids: list[str] = []
    tool_trace: list[dict[str, Any]] = []


@router.post("/communication", response_model=AgentResponse)
async def run_communication_agent(
    body: AgentRequest,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await CommunicationAgent(db).run(user=ctx.user, text=body.message)
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return AgentResponse(
        request_id=result.request_id,
        ok=result.ok,
        intent=result.intent,
        clarification=result.clarification,
        message=result.message,
        work_item_id=result.work_item_id,
        task_ids=result.task_ids,
        case_id=result.case_id,
        tool_trace=result.tool_trace,
    )


@router.post("/inventory", response_model=InventoryAgentResponse)
async def run_inventory_agent(
    body: InventoryAgentRequest,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await InventoryAgent(db).run(
            user=ctx.user,
            message=body.message,
            min_days=body.min_days,
            min_branch_requests=body.min_branch_requests,
            auto_create=body.auto_create,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return InventoryAgentResponse(
        request_id=result.request_id,
        ok=result.ok,
        intent=result.intent,
        clarification=result.clarification,
        message=result.message,
        opportunities_found=result.opportunities_found,
        cases_created=result.cases_created,
        work_item_ids=result.work_item_ids,
        tool_trace=result.tool_trace,
    )


@router.post("/sales", response_model=SalesAgentResponse)
async def run_sales_agent(
    body: SalesAgentRequest,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await SalesAgent(db).run(
            user=ctx.user,
            message=body.message,
            stale_days=body.stale_days,
            auto_create=body.auto_create,
            case_id=body.case_id,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return SalesAgentResponse(
        request_id=result.request_id,
        ok=result.ok,
        intent=result.intent,
        clarification=result.clarification,
        message=result.message,
        follow_ups_found=result.follow_ups_found,
        cases_created=result.cases_created,
        work_item_ids=result.work_item_ids,
        task_ids=result.task_ids,
        tool_trace=result.tool_trace,
    )


class PurchaseAgentRequest(BaseModel):
    message: str | None = None
    stale_days: int | None = Field(default=None, ge=0)
    auto_create: bool | None = None


class PurchaseAgentResponse(BaseModel):
    request_id: str
    ok: bool
    intent: str
    clarification: str | None = None
    message: str
    opportunities_found: int = 0
    cases_created: list[str] = []
    work_item_ids: list[str] = []
    task_ids: list[str] = []
    tool_trace: list[dict[str, Any]] = []


@router.post("/purchase", response_model=PurchaseAgentResponse)
async def run_purchase_agent(
    body: PurchaseAgentRequest,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await PurchaseAgent(db).run(
            user=ctx.user,
            message=body.message,
            stale_days=body.stale_days,
            auto_create=body.auto_create,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return PurchaseAgentResponse(
        request_id=result.request_id,
        ok=result.ok,
        intent=result.intent,
        clarification=result.clarification,
        message=result.message,
        opportunities_found=result.opportunities_found,
        cases_created=result.cases_created,
        work_item_ids=result.work_item_ids,
        task_ids=result.task_ids,
        tool_trace=result.tool_trace,
    )


class DivarAgentRequest(BaseModel):
    message: str | None = None
    vehicle_id: str | None = None
    auto_create: bool | None = None
    limit: int = Field(default=5, ge=1, le=20)


class DivarAgentResponse(BaseModel):
    request_id: str
    ok: bool
    intent: str
    clarification: str | None = None
    message: str
    listings_prepared: int = 0
    listing_ids: list[str] = []
    work_item_ids: list[str] = []
    tool_trace: list[dict[str, Any]] = []


@router.post("/divar", response_model=DivarAgentResponse)
async def run_divar_agent(
    body: DivarAgentRequest,
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await DivarAgent(db).run(
            user=ctx.user,
            message=body.message,
            vehicle_id=body.vehicle_id,
            auto_create=body.auto_create,
            limit=body.limit,
        )
    except AuthorizationError as e:
        raise handle_authz(e) from e
    return DivarAgentResponse(
        request_id=result.request_id,
        ok=result.ok,
        intent=result.intent,
        clarification=result.clarification,
        message=result.message,
        listings_prepared=result.listings_prepared,
        listing_ids=result.listing_ids,
        work_item_ids=result.work_item_ids,
        tool_trace=result.tool_trace,
    )
