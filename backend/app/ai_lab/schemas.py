"""Pydantic schemas for AI Lab tasks and bot results."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

TASK_KINDS = (
    "period_review",
    "campaign_review",
    "channel_budget",
    "sms_copy_review",
    "projects_health",
    "team_load",
    "finance_reconcile",
    "my_work_review",
)

TaskKindLiteral = Literal[
    "period_review",
    "campaign_review",
    "channel_budget",
    "sms_copy_review",
    "projects_health",
    "team_load",
    "finance_reconcile",
    "my_work_review",
]


class PeriodReviewIn(BaseModel):
    from_date: str
    to_date: str
    brand: str = ""


class CampaignReviewIn(BaseModel):
    campaign_id: UUID


class ChannelBudgetIn(BaseModel):
    next_budget_toman: int = Field(ge=0)
    reference_from: str
    reference_to: str


class SmsCopyReviewIn(BaseModel):
    from_date: str
    to_date: str
    brand: str = ""


class ProjectsHealthIn(BaseModel):
    lane: str = ""
    stale_days: int = Field(default=14, ge=1, le=90)


class TeamLoadIn(BaseModel):
    lane: str = ""


class FinanceReconcileIn(BaseModel):
    pass


class MyWorkReviewIn(BaseModel):
    pass


class SnapshotIn(BaseModel):
    kind: TaskKindLiteral
    input: dict[str, Any]


class TaskCreateIn(BaseModel):
    kind: TaskKindLiteral
    input: dict[str, Any]


class FindingOut(BaseModel):
    title: str
    evidence: str
    severity: Literal["high", "medium", "low"]


class RecommendationOut(BaseModel):
    id: str
    action: str
    reason: str
    expected_impact: str
    confidence: Literal["high", "medium", "low"]


class BotResultBody(BaseModel):
    summary: str
    findings: list[FindingOut] = Field(default_factory=list)
    recommendations: list[RecommendationOut] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)


class BotCallbackIn(BaseModel):
    task_id: UUID
    status: Literal["done", "failed"]
    result: BotResultBody | None = None
    error: str | None = None

    @model_validator(mode="after")
    def result_required_when_done(self):
        if self.status == "done" and self.result is None:
            raise ValueError("result required when status is done")
        return self


class ManualResultIn(BaseModel):
    payload: dict[str, Any]


class EvaluationIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    useful: bool
    eval_note: str = ""


class RecommendationDecisionIn(BaseModel):
    decision: Literal["accepted", "rejected", "done"]


class RecToTaskIn(BaseModel):
    owner_id: UUID | None = None
    deadline: str | None = None
    priority: Literal["low", "medium", "high", "critical"] = "medium"
