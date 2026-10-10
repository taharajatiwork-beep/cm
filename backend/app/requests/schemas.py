from datetime import date
from uuid import UUID

from pydantic import BaseModel


class RequestIn(BaseModel):
    title: str
    description: str = ""
    kind: str = "عمومی"
    priority: str = "normal"  # low | normal | high
    due_date: date | None = None
    team_id: UUID | None = None


class RequestPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    kind: str | None = None
    priority: str | None = None
    due_date: date | None = None
    team_id: UUID | None = None
    status: str | None = None


class ProjectIn(BaseModel):
    title: str
    description: str = ""
    kind: str = "عمومی"
    team_id: UUID | None = None
    status: str = "new"  # new | in_progress | done


class ProjectPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    kind: str | None = None
    team_id: UUID | None = None
    status: str | None = None