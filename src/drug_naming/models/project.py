from __future__ import annotations
from .._compat import StrEnum
from datetime import date, datetime, timezone
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from .molecule import MoleculeInput


class MilestoneStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class Milestone(BaseModel):
    id: str
    name: str
    phase: str
    order: int
    status: MilestoneStatus = MilestoneStatus.PENDING
    fastest_days: int
    slowest_days: int
    fastest_start: date | None = None
    fastest_end: date | None = None
    slowest_start: date | None = None
    slowest_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    depends_on: list[str] = Field(default_factory=list)
    parallel_with: str | None = None
    notes: str = ""


class Phase(BaseModel):
    id: str
    name: str
    order: int
    milestones: list[Milestone] = Field(default_factory=list)
    is_parallel: bool = False
    parallel_trigger: str | None = None


class ProjectStatus(StrEnum):
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    DELAYED = "delayed"
    COMPLETED = "completed"


class Project(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    cas_number: str | None = None
    molecule: MoleculeInput
    phases: list[Phase] = Field(default_factory=list)
    current_phase: str = ""
    current_milestone: str = ""
    overall_status: ProjectStatus = ProjectStatus.ON_TRACK
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    csv_source: str | None = None
