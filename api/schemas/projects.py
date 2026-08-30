from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from api.schemas.common import Stage


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    brand: str | None = None
    jobName: str | None = None
    location: str | None = None
    state: str | None = Field(default=None, max_length=2, description="Ship-to state; drives tax")
    architect: str | None = None
    gc: str | None = None
    initiator: str | None = None
    bidDue: date | None = None
    projectNumber: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    brand: str | None = None
    jobName: str | None = None
    location: str | None = None
    state: str | None = Field(default=None, max_length=2)
    architect: str | None = None
    gc: str | None = None
    initiator: str | None = None
    bidDue: date | None = None
    projectNumber: str | None = None
    stage: Stage | None = None


class Project(ProjectCreate):
    id: str
    code: str
    slug: str
    stage: Stage = "intake"
    progress: int = 0
    createdAt: datetime
    updatedAt: datetime | None = None
