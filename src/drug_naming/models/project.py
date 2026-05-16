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
    planned_start: date | None = None
    planned_end: date | None = None
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
    nda_date: date | None = None
    active_path: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    csv_source: str | None = None


class MilestoneDateOverride(BaseModel):
    milestone_id: str
    planned_start: date | None = None
    planned_end: date | None = None


def build_default_phases(has_cas: bool) -> list[Phase]:
    """Build the default 5-phase pipeline structure.

    Args:
        has_cas: True if CAS number is already known (skip Phase 1).

    Returns:
        List of Phase objects with milestones populated.
    """
    phases: list[Phase] = []

    if not has_cas:
        phases.append(Phase(
            id="cas_application",
            name="CAS申请",
            order=1,
            milestones=[
                Milestone(id="cas_doc_prep", name="CAS资料准备", phase="cas_application", order=1, fastest_days=3, slowest_days=7),
                Milestone(id="cas_submit", name="CAS申请递交", phase="cas_application", order=2, fastest_days=1, slowest_days=3, depends_on=["cas_doc_prep"]),
                Milestone(id="cas_obtain", name="CAS号获取", phase="cas_application", order=3, fastest_days=5, slowest_days=15, depends_on=["cas_submit"]),
            ],
        ))

    phase2_order = 2 if not has_cas else 1
    phases.append(Phase(
        id="inn_naming",
        name="INN命名",
        order=phase2_order,
        milestones=[
            Milestone(id="inn_name_determined", name="确定申报名", phase="inn_naming", order=1, fastest_days=4, slowest_days=10),
            Milestone(id="inn_submission", name="INN申请提交", phase="inn_naming", order=2, fastest_days=5, slowest_days=10, depends_on=["inn_name_determined"]),
            Milestone(id="inn_consultation", name="INN会议", phase="inn_naming", order=3, fastest_days=0, slowest_days=0, depends_on=["inn_submission"]),
            Milestone(id="inn_pinn_published", name="pINN公示", phase="inn_naming", order=4, fastest_days=60, slowest_days=80, depends_on=["inn_consultation"]),
            Milestone(id="inn_pinn_objection", name="pINN反对期", phase="inn_naming", order=5, fastest_days=80, slowest_days=80, depends_on=["inn_pinn_published"]),
            Milestone(id="inn_rinn", name="rINN时间", phase="inn_naming", order=6, fastest_days=100, slowest_days=120, depends_on=["inn_pinn_objection"]),
        ],
    ))

    phase3_order = phase2_order + 1
    phases.append(Phase(
        id="chinese_submission",
        name="中文名提交",
        order=phase3_order,
        is_parallel=True,
        parallel_trigger="inn_pinn_published",
        milestones=[
            Milestone(id="chin_name_draft", name="中文名拟定", phase="chinese_submission", order=1, fastest_days=3, slowest_days=7),
            Milestone(id="chin_doc_submit", name="通用名资料提交", phase="chinese_submission", order=2, fastest_days=5, slowest_days=15, depends_on=["chin_name_draft"]),
        ],
    ))

    phase4_order = phase3_order + 1
    phases.append(Phase(
        id="pharmacopoeia_review",
        name="药典委核名",
        order=phase4_order,
        milestones=[
            Milestone(id="pharm_auto_notice", name="药典委自动公示", phase="pharmacopoeia_review", order=1, fastest_days=200, slowest_days=220, notes="路径A: pINN后10-11个月自动触发，公示1个月"),
            Milestone(id="pharm_tech_review", name="药典委技术审评", phase="pharmacopoeia_review", order=2, fastest_days=30, slowest_days=60, notes="路径B: CDE受理后流转，无公示期"),
            Milestone(id="pharm_approval", name="收到核准文件", phase="pharmacopoeia_review", order=3, fastest_days=10, slowest_days=20, depends_on=["pharm_auto_notice", "pharm_tech_review"]),
        ],
    ))

    phase5_order = phase4_order + 1
    phases.append(Phase(
        id="trademark",
        name="商标品牌",
        order=phase5_order,
        is_parallel=True,
        parallel_trigger="inn_pinn_published",
        milestones=[
            Milestone(id="tm_name_draft", name="商品名拟定", phase="trademark", order=1, fastest_days=5, slowest_days=10),
            Milestone(id="tm_submit", name="商品名提交", phase="trademark", order=2, fastest_days=5, slowest_days=10, depends_on=["tm_name_draft"]),
            Milestone(id="tm_notice", name="商品名公示", phase="trademark", order=3, fastest_days=180, slowest_days=180, depends_on=["tm_submit"]),
        ],
    ))

    return phases
