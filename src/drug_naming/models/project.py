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
    path: str | None = None  # "A" or "B" for pharmacopoeia dual-path; None = both paths
    notes: str = ""
    result: str = ""


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
    sort_order: int = 0


class MilestoneDateOverride(BaseModel):
    milestone_id: str
    planned_start: date | None = None
    planned_end: date | None = None


def build_default_phases(has_cas: bool) -> list[Phase]:
    """Build the default 5-phase pipeline structure.

    Durations calibrated from 8 real project timelines (May 2026).

    Args:
        has_cas: True if CAS number is already known (skip Phase 1).

    Returns:
        List of Phase objects with milestones populated.
    """
    phases: list[Phase] = []

    # Phase 1: CAS申请 (6-16 days total in real data)
    if not has_cas:
        phases.append(Phase(
            id="cas_application",
            name="CAS申请",
            order=1,
            milestones=[
                Milestone(id="cas_doc_prep", name="CAS资料准备", phase="cas_application", order=1, fastest_days=1, slowest_days=3),
                Milestone(id="cas_submit", name="CAS申请递交", phase="cas_application", order=2, fastest_days=1, slowest_days=2, depends_on=["cas_doc_prep"]),
                Milestone(id="cas_obtain", name="CAS号获取", phase="cas_application", order=3, fastest_days=5, slowest_days=10, depends_on=["cas_submit"]),
            ],
        ))

    # Phase 2: INN命名 — 4 milestones matching real workflow
    phase2_order = 2 if not has_cas else 1
    phases.append(Phase(
        id="inn_naming",
        name="INN命名",
        order=phase2_order,
        milestones=[
            Milestone(id="inn_submission", name="INN资料准备与提交", phase="inn_naming", order=1, fastest_days=68, slowest_days=95),
            Milestone(id="inn_consultation", name="INN会议", phase="inn_naming", order=2, fastest_days=0, slowest_days=0, depends_on=["inn_submission"]),
            Milestone(id="inn_pinn_published", name="pINN公示", phase="inn_naming", order=3, fastest_days=120, slowest_days=126, depends_on=["inn_consultation"]),
            Milestone(id="inn_rinn", name="rINN时间", phase="inn_naming", order=4, fastest_days=60, slowest_days=90, depends_on=["inn_pinn_published"]),
        ],
    ))

    # Phase 3: 药典委核名 — dual-path (Path A: auto, Path B: active submission)
    phase3_order = phase2_order + 1
    phases.append(Phase(
        id="pharmacopoeia_review",
        name="药典委核名",
        order=phase3_order,
        milestones=[
            # Path A: 自动核准
            Milestone(id="pharm_auto_notice", name="药典委自动公示", phase="pharmacopoeia_review", order=1, fastest_days=30, slowest_days=40, path="A"),
            # Path B: 主动申报
            Milestone(id="pharm_chin_draft", name="中文通用名拟定", phase="pharmacopoeia_review", order=2, fastest_days=5, slowest_days=10, path="B"),
            Milestone(id="pharm_chin_submit", name="资料提交", phase="pharmacopoeia_review", order=3, fastest_days=5, slowest_days=15, depends_on=["pharm_chin_draft"], path="B"),
            Milestone(id="pharm_tech_review", name="技术审评", phase="pharmacopoeia_review", order=4, fastest_days=30, slowest_days=60, depends_on=["pharm_chin_submit"], path="B"),
            # Common final step (both paths converge here)
            Milestone(id="pharm_approval", name="收到核准文件", phase="pharmacopoeia_review", order=5, fastest_days=5, slowest_days=10, path=None),
        ],
    ))

    # Phase 4: 商标品牌 — 3 milestones (parallel, triggered by pINN)
    phase4_order = phase3_order + 1
    phases.append(Phase(
        id="trademark",
        name="商标品牌",
        order=phase4_order,
        is_parallel=True,
        parallel_trigger="inn_pinn_published",
        milestones=[
            Milestone(id="tm_name_draft", name="候选名库构建", phase="trademark", order=1, fastest_days=25, slowest_days=32),
            Milestone(id="tm_cde_check", name="商标检索及CDE比对", phase="trademark", order=2, fastest_days=25, slowest_days=32, depends_on=["tm_name_draft"]),
            Milestone(id="tm_notice", name="商标申请至公告", phase="trademark", order=3, fastest_days=300, slowest_days=310, depends_on=["tm_cde_check"]),
        ],
    ))

    # Phase 5: NDA申报
    phase5_order = phase4_order + 1
    phases.append(Phase(
        id="nda_filing",
        name="NDA申报",
        order=phase5_order,
        milestones=[
            Milestone(id="nda_submit", name="NDA递交", phase="nda_filing", order=1, fastest_days=0, slowest_days=0,
                      depends_on=["pharm_approval", "tm_notice"],
                      notes="药典委核准 + 商标公告均完成后触发"),
        ],
    ))

    return phases
