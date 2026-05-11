from __future__ import annotations
from .._compat import StrEnum
from datetime import datetime, timezone
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from .molecule import MoleculeInput
from .naming import NameCandidate
from .poca import POCAScoreDetail
from .chinese import ChineseNameCandidate
from .brand import BrandNameCandidate


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    STEM_MATCHING = "stem_matching"
    NAME_GENERATION = "name_generation"
    POCA_SCREENING = "poca_screening"
    CHINESE_NAMING = "chinese_naming"
    BRAND_SCREENING = "brand_screening"
    DECISION_PENDING = "decision_pending"
    COMPLETED = "completed"
    REJECTED = "rejected"


class Decision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"
    ESCALATED = "escalated"


class WorkflowStep(BaseModel):
    step_name: str
    status: ProjectStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result_summary: dict = Field(default_factory=dict)
    decision: Decision | None = None
    decision_notes: str | None = None


class NamingProject(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    molecule: MoleculeInput
    status: ProjectStatus = ProjectStatus.DRAFT
    workflow: list[WorkflowStep] = Field(default_factory=list)
    stem_matches: list = Field(default_factory=list)
    inn_candidates: list[NameCandidate] = Field(default_factory=list)
    poca_results: list[POCAScoreDetail] = Field(default_factory=list)
    chinese_candidates: list[ChineseNameCandidate] = Field(default_factory=list)
    brand_candidates: list[BrandNameCandidate] = Field(default_factory=list)
    final_selection: dict | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
