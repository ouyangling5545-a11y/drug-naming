# 项目管线管理 — 实现计划 (v0.3.0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有"名称评估"和"智能推荐"两个 Tab 基础上新增第三个 Tab "项目管理"，实现从 CAS 号获取到药典委核名全流程的项目管线管理，含最快/最慢双时间线、双路径分叉、药企 Pipeline 风格甘特图。

**Architecture:** 重写 models/project.py（新数据模型）、重写 api/projects.py（JSON 持久化 + 新端点）、新建 engines/date_calculator.py（日期计算引擎），在 static/index.html 新增 Tab C 含 Canvas/SVG 管线图组件。前端使用 Vue 3 CDN 纯原生实现，无构建工具。

**Tech Stack:** Python 3.9+, FastAPI, Pydantic v2, Vue 3 CDN, JSON file persistence

---

### Task 1: 重写数据模型 (models/project.py)

**Files:**
- Read: `src/drug_naming/models/project.py` (现有)
- Read: `src/drug_naming/models/molecule.py` (依赖)
- Write: `src/drug_naming/models/project.py` (重写)

- [ ] **Step 1: 写新模型文件**

```python
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
```

- [ ] **Step 2: 验证模型可导入**

```bash
cd /Users/owen/projectcc && python3 -c "from src.drug_naming.models.project import Milestone, Phase, Project, MilestoneStatus, ProjectStatus; m=Milestone(id='test', name='测试', phase='p1', order=1, fastest_days=5, slowest_days=10); print(m.model_dump_json()); print('OK')"
```
Expected: JSON 输出含所有字段，status 为 "pending"

- [ ] **Step 3: Commit**

```bash
git add src/drug_naming/models/project.py
git commit -m "feat(models): rewrite project.py with Milestone/Phase/Project models for v0.3.0 pipeline"
```

---

### Task 2: 新建日期计算引擎 (engines/date_calculator.py)

**Files:**
- Create: `src/drug_naming/engines/date_calculator.py`
- Read: `src/drug_naming/engines/__init__.py`

- [ ] **Step 1: 确认 engines/__init__.py 内容**

```bash
cat /Users/owen/projectcc/src/drug_naming/engines/__init__.py
```

- [ ] **Step 2: 写日期计算引擎**

```python
"""Date calculator for project pipeline milestones.

Handles calendar-day projection from working-day durations,
skipping weekends. Working days = calendar days minus Saturdays and Sundays.
"""

from datetime import date, timedelta


def working_days_to_calendar_days(working_days: int) -> int:
    """Convert working days to approximate calendar days.

    Rough estimate: 5 working days per 7 calendar days.
    Used for initial projection before exact date calculation.
    """
    return int(working_days * 7 / 5) + 1


def add_working_days(start: date, working_days: int) -> date:
    """Add working days to a date, skipping weekends.

    If working_days is 0, returns start.
    Each full working day increments the date by 1, skipping Sat/Sun.
    """
    if working_days <= 0:
        return start
    current = start
    remaining = working_days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon=0 ... Fri=4
            remaining -= 1
    return current


def recalculate_milestone_dates(milestones: list, start_date: date | None = None) -> None:
    """Recalculate fastest_start/fastest_end and slowest_start/slowest_end
    for an ordered list of milestones.

    Handles dependency chains: a milestone that depends_on another
    starts after the dependency's end date.

    Args:
        milestones: List of Milestone objects (mutated in place).
        start_date: Override start date for the first milestone.
                    Defaults to today.
    """
    from .project import Milestone  # avoid circular import at module level

    if not milestones:
        return

    # Build lookup by milestone id
    by_id: dict[str, Milestone] = {m.id: m for m in milestones}

    base = start_date or date.today()

    for m in sorted(milestones, key=lambda x: x.order):
        # Determine fastest start
        fastest_start = base
        if m.depends_on:
            candidates = []
            for dep_id in m.depends_on:
                dep = by_id.get(dep_id)
                if dep and dep.fastest_end:
                    candidates.append(dep.fastest_end)
            if candidates:
                fastest_start = max(candidates) + timedelta(days=1)

        # Skip weekends for start date
        while fastest_start.weekday() >= 5:
            fastest_start += timedelta(days=1)

        m.fastest_start = fastest_start
        m.fastest_end = add_working_days(fastest_start, m.fastest_days)

        # Slowest path
        slowest_start = base
        if m.depends_on:
            candidates = []
            for dep_id in m.depends_on:
                dep = by_id.get(dep_id)
                if dep and dep.slowest_end:
                    candidates.append(dep.slowest_end)
            if candidates:
                slowest_start = max(candidates) + timedelta(days=1)

        while slowest_start.weekday() >= 5:
            slowest_start += timedelta(days=1)

        m.slowest_start = slowest_start
        m.slowest_end = add_working_days(slowest_start, m.slowest_days)


def recalculate_project_dates(project) -> None:
    """Recalculate all milestone dates for a project.

    Respects phase ordering and parallel phases.
    First non-parallel phase starts from today.
    Parallel phases can start after their parallel_trigger milestone completes.
    """
    from datetime import date as dt_date

    phases_sorted = sorted(project.phases, key=lambda p: p.order)
    base_date = dt_date.today()

    for phase in phases_sorted:
        if phase.is_parallel and phase.parallel_trigger:
            # Find the trigger milestone in another phase
            trigger_end = None
            for other_phase in phases_sorted:
                for m in other_phase.milestones:
                    if m.id == phase.parallel_trigger and m.fastest_end:
                        trigger_end = m.fastest_end
                        break
                if trigger_end:
                    break
            if trigger_end:
                # Use the trigger end as base for this parallel phase
                recalculate_milestone_dates(phase.milestones, start_date=trigger_end)
                continue

        recalculate_milestone_dates(phase.milestones, start_date=base_date)
        # Next non-parallel phase starts after the last milestone of this phase
        if phase.milestones:
            last = phase.milestones[-1]
            if last.fastest_end:
                base_date = last.fastest_end
```

- [ ] **Step 3: 验证计算逻辑**

```bash
cd /Users/owen/projectcc && python3 -c "
from datetime import date
from src.drug_naming.engines.date_calculator import add_working_days, working_days_to_calendar_days

# Test: 5 working days from Monday
d = date(2026, 5, 11)  # Monday
assert add_working_days(d, 5) == date(2026, 5, 18)  # Monday + 5 working days = next Monday

# Test: 1 working day from Friday
d2 = date(2026, 5, 15)  # Friday
assert add_working_days(d2, 1) == date(2026, 5, 18)  # Monday

# Test: 0 working days
assert add_working_days(date(2026, 5, 11), 0) == date(2026, 5, 11)

print('All tests passed')
"
```
Expected: `All tests passed`

- [ ] **Step 4: Commit**

```bash
git add src/drug_naming/engines/date_calculator.py
git commit -m "feat(engines): add date_calculator — working-day math, milestone date projection"
```

---

### Task 3: 新建默认 Phase 工厂函数 (models/project.py 追加)

**Files:**
- Modify: `src/drug_naming/models/project.py` (追加 after existing models)

- [ ] **Step 1: 追加工厂函数到 models/project.py**

在文件末尾追加：

```python
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
            Milestone(id="inn_stem_matching", name="词干匹配", phase="inn_naming", order=1, fastest_days=1, slowest_days=3),
            Milestone(id="inn_name_generation", name="名称生成", phase="inn_naming", order=2, fastest_days=2, slowest_days=5, depends_on=["inn_stem_matching"]),
            Milestone(id="inn_poca_screening", name="POCA筛选", phase="inn_naming", order=3, fastest_days=1, slowest_days=2, depends_on=["inn_name_generation"]),
            Milestone(id="inn_submission", name="INN申请提交", phase="inn_naming", order=4, fastest_days=5, slowest_days=10, depends_on=["inn_poca_screening"]),
            Milestone(id="inn_consultation", name="INN会议", phase="inn_naming", order=5, fastest_days=60, slowest_days=120, depends_on=["inn_submission"]),
            Milestone(id="inn_pinn_published", name="pINN公示", phase="inn_naming", order=6, fastest_days=60, slowest_days=80, depends_on=["inn_consultation"]),
            Milestone(id="inn_pinn_objection", name="pINN反对期", phase="inn_naming", order=7, fastest_days=80, slowest_days=80, depends_on=["inn_pinn_published"]),
            Milestone(id="inn_rinn", name="rINN时间", phase="inn_naming", order=8, fastest_days=100, slowest_days=120, depends_on=["inn_pinn_objection"]),
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
            # Path A (auto): triggered 10-11 months after pINN
            Milestone(id="pharm_auto_notice", name="药典委自动公示", phase="pharmacopoeia_review", order=1, fastest_days=200, slowest_days=220, notes="路径A: pINN后10-11个月自动触发，公示1个月"),
            # Path B (active): triggered after CDE acceptance
            Milestone(id="pharm_tech_review", name="药典委技术审评", phase="pharmacopoeia_review", order=2, fastest_days=30, slowest_days=60, notes="路径B: CDE受理后流转，无公示期"),
            # Common
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
```

- [ ] **Step 2: 验证工厂函数**

```bash
cd /Users/owen/projectcc && python3 -c "
from src.drug_naming.models.project import build_default_phases
phases_no_cas = build_default_phases(has_cas=False)
phases_with_cas = build_default_phases(has_cas=True)
assert len(phases_no_cas) == 5, f'Expected 5 phases with no CAS, got {len(phases_no_cas)}'
assert len(phases_with_cas) == 4, f'Expected 4 phases with CAS, got {len(phases_with_cas)}'
assert phases_no_cas[0].id == 'cas_application'
assert phases_with_cas[0].id == 'inn_naming'
print(f'No CAS: {[p.name for p in phases_no_cas]}')
print(f'With CAS: {[p.name for p in phases_with_cas]}')
print('OK')
"
```
Expected: 输出含 5 个 / 4 个 Phase 名称

- [ ] **Step 3: Commit**

```bash
git add src/drug_naming/models/project.py
git commit -m "feat(models): add build_default_phases() factory with 5-phase pipeline structure"
```

---

### Task 4: 重写 Projects API — JSON 持久化 + 基础 CRUD

**Files:**
- Read: `src/drug_naming/api/projects.py` (existing)
- Write: `src/drug_naming/api/projects.py` (rewrite)
- Create: `src/drug_naming/data/projects.json`

- [ ] **Step 1: 创建初始 projects.json**

```bash
echo '[]' > /Users/owen/projectcc/src/drug_naming/data/projects.json
```

- [ ] **Step 2: 写新的 projects.py API**

```python
from __future__ import annotations
import json
from pathlib import Path
from datetime import date, datetime, timezone
from uuid import UUID
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, UploadFile, File
from ..models.molecule import MoleculeInput
from ..models.project import (
    Project, Phase, Milestone, MilestoneStatus,
    ProjectStatus, build_default_phases,
)
from ..engines.date_calculator import recalculate_project_dates

router = APIRouter()

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "projects.json"


def _load() -> dict[UUID, Project]:
    """Load all projects from JSON file."""
    if not DATA_FILE.exists():
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    projects: dict[UUID, Project] = {}
    for item in raw:
        p = Project.model_validate(item)
        projects[p.id] = p
    return projects


def _save(projects: dict[UUID, Project]) -> None:
    """Save all projects to JSON file."""
    data = [p.model_dump(mode="json") for p in projects.values()]
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


class CreateProjectBody(BaseModel):
    name: str
    cas_number: str | None = None
    molecule: MoleculeInput


@router.post("/", response_model=Project)
def create_project(body: CreateProjectBody) -> Project:
    """Create a new pipeline project with default phases."""
    projects = _load()
    has_cas = bool(body.cas_number and body.cas_number.strip())
    phases = build_default_phases(has_cas)
    project = Project(
        name=body.name,
        cas_number=body.cas_number.strip() if body.cas_number else None,
        molecule=body.molecule,
        phases=phases,
    )
    recalculate_project_dates(project)
    projects[project.id] = project
    _save(projects)
    return project


@router.get("/", response_model=list[Project])
def list_projects(status: str | None = None) -> list[Project]:
    """List all projects, optionally filtered by overall_status."""
    projects = _load()
    result = list(projects.values())
    if status:
        result = [p for p in result if p.overall_status == status]
    return sorted(result, key=lambda p: p.created_at, reverse=True)


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: UUID) -> Project:
    """Get a project by ID with all phases and milestones."""
    projects = _load()
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=Project)
def update_project(project_id: UUID, body: CreateProjectBody) -> Project:
    """Update project basic info."""
    projects = _load()
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.name = body.name
    project.cas_number = body.cas_number
    project.molecule = body.molecule
    project.updated_at = datetime.now(timezone.utc)
    _save(projects)
    return project


@router.delete("/{project_id}")
def delete_project(project_id: UUID) -> dict:
    """Delete a project."""
    projects = _load()
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    del projects[project_id]
    _save(projects)
    return {"ok": True}
```

- [ ] **Step 3: 验证 API 基础 CRUD 可导入**

```bash
cd /Users/owen/projectcc && python3 -c "from src.drug_naming.api.projects import router; print('Router OK, routes:', [r.path for r in router.routes])"
```
Expected: 输出路由列表

- [ ] **Step 4: Commit**

```bash
git add src/drug_naming/api/projects.py src/drug_naming/data/projects.json
git commit -m "feat(api): rewrite projects.py with JSON persistence and basic CRUD"
```

---

### Task 5: Projects API — milestone 更新 + 重算端点

**Files:**
- Modify: `src/drug_naming/api/projects.py` (追加端点)

- [ ] **Step 1: 在 projects.py 追加 milestone 更新和 recalculate 端点**

在 delete_project 函数之后追加：

```python
class UpdateMilestoneBody(BaseModel):
    status: MilestoneStatus | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    fastest_start: date | None = None
    fastest_end: date | None = None
    slowest_start: date | None = None
    slowest_end: date | None = None
    notes: str | None = None


@router.patch("/{project_id}/milestones/{milestone_id}", response_model=Project)
def update_milestone(project_id: UUID, milestone_id: str, body: UpdateMilestoneBody) -> Project:
    """Update a single milestone's status, dates, or notes."""
    projects = _load()
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    found = False
    for phase in project.phases:
        for m in phase.milestones:
            if m.id == milestone_id:
                found = True
                update_data = body.model_dump(exclude_unset=True)
                for key, val in update_data.items():
                    setattr(m, key, val)
                break
        if found:
            break

    if not found:
        raise HTTPException(status_code=404, detail="Milestone not found")

    # Update project current_milestone and overall_status
    _update_project_status(project)
    project.updated_at = datetime.now(timezone.utc)
    _save(projects)
    return project


@router.post("/{project_id}/recalculate", response_model=Project)
def recalculate_project(project_id: UUID) -> Project:
    """Recalculate all milestone dates after dependency changes."""
    projects = _load()
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    recalculate_project_dates(project)
    project.updated_at = datetime.now(timezone.utc)
    _save(projects)
    return project


def _update_project_status(project: Project) -> None:
    """Derive overall_status and current_milestone from milestone states."""
    all_ms: list[Milestone] = []
    for phase in project.phases:
        all_ms.extend(phase.milestones)

    blocked_count = sum(1 for m in all_ms if m.status == MilestoneStatus.BLOCKED)
    completed_count = sum(1 for m in all_ms if m.status == MilestoneStatus.COMPLETED)

    if blocked_count > 0:
        project.overall_status = ProjectStatus.AT_RISK
    elif completed_count == len(all_ms):
        project.overall_status = ProjectStatus.COMPLETED
    else:
        project.overall_status = ProjectStatus.ON_TRACK

    # Find current milestone: first non-completed in order
    for phase in sorted(project.phases, key=lambda p: p.order):
        for m in sorted(phase.milestones, key=lambda x: x.order):
            if m.status != MilestoneStatus.COMPLETED:
                project.current_phase = phase.id
                project.current_milestone = m.id
                return

    project.current_phase = project.phases[-1].id if project.phases else ""
    project.current_milestone = ""
```

- [ ] **Step 2: 验证导入**

```bash
cd /Users/owen/projectcc && python3 -c "from src.drug_naming.api.projects import router, UpdateMilestoneBody; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/drug_naming/api/projects.py
git commit -m "feat(api): add milestone update, recalculate, and status derivation endpoints"
```

---

### Task 6: Projects API — CSV 批量导入

**Files:**
- Modify: `src/drug_naming/api/projects.py` (追加 import endpoint)

- [ ] **Step 1: 追加 CSV 导入端点**

在文件末尾追加：

```python
import csv
import io

from ..models.molecule import (
    PharmacologicalProperties, TargetClass, Mechanism, ChemicalClass,
)


@router.post("/import", response_model=list[Project])
async def import_projects_csv(file: UploadFile = File(...)) -> list[Project]:
    """Import projects from a CSV file.

    Expected columns:
    project_name,cas_number,target_class,mechanism,indication,chemical_class

    Columns after the 6 required ones are ignored.
    """
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="CSV has no header row")

    projects_store = _load()
    created: list[Project] = []

    target_map = {e.value: e for e in TargetClass}
    mechanism_map = {e.value: e for e in Mechanism}
    chem_map = {e.value: e for e in ChemicalClass}

    for row_idx, row in enumerate(reader):
        project_name = (row.get("project_name") or "").strip()
        if not project_name:
            continue

        cas = (row.get("cas_number") or "").strip() or None

        target_str = (row.get("target_class") or "other").strip().lower()
        mechanism_str = (row.get("mechanism") or "other").strip().lower()
        indication = (row.get("indication") or "").strip()
        chem_str = (row.get("chemical_class") or "other").strip().lower()

        target_class = target_map.get(target_str, TargetClass.OTHER)
        mechanism = mechanism_map.get(mechanism_str, Mechanism.OTHER)
        chemical_class = chem_map.get(chem_str, ChemicalClass.OTHER)

        props = PharmacologicalProperties(
            target_class=target_class,
            mechanism=mechanism,
            chemical_class=chemical_class,
            indication=indication,
        )

        molecule = MoleculeInput(
            molecule_id=project_name,
            common_name=project_name,
            properties=props,
        )

        has_cas = bool(cas)
        phases = build_default_phases(has_cas)

        project = Project(
            name=project_name,
            cas_number=cas,
            molecule=molecule,
            phases=phases,
            csv_source=file.filename,
        )
        recalculate_project_dates(project)
        projects_store[project.id] = project
        created.append(project)

    _save(projects_store)
    return created
```

- [ ] **Step 2: 验证导入**

```bash
cd /Users/owen/projectcc && python3 -c "from src.drug_naming.api.projects import router; print('Import OK')"
```
Expected: `Import OK`

- [ ] **Step 3: Commit**

```bash
git add src/drug_naming/api/projects.py
git commit -m "feat(api): add CSV batch import endpoint for projects"
```

---

### Task 7: 前端 Tab C — 基础结构与新建项目表单

**Files:**
- Read: `src/drug_naming/static/index.html` (lines 1-200 for styles, 490-1071 for tabs/app)
- Modify: `src/drug_naming/static/index.html` (add Tab CSS, Tab C markup, Vue state)

- [ ] **Step 1: 在 CSS 中追加管线图样式**

在 `</style>` 之前追加以下 CSS（将现有 `</style>` 所在行替换为这些样式+`</style>`）。

先确认 `</style>` 位置：

```bash
grep -n '</style>' /Users/owen/projectcc/src/drug_naming/static/index.html
```

在 `</style>` 前插入：

```css
/* ===== Tab C: Pipeline Management ===== */
.pipeline-toolbar {
  display: flex; align-items: center; gap: var(--space-3);
  padding: var(--space-4) 0; flex-wrap: wrap;
}
.pipeline-toolbar .btn {
  padding: 8px 18px; border-radius: var(--radius-sm); font-weight: 600;
  font-size: 13px; cursor: pointer; border: none; transition: var(--transition-fast);
  font-family: var(--font-body);
}
.btn-primary { background: var(--color-primary); color: white; }
.btn-primary:hover { background: var(--color-secondary); }
.btn-outline { background: transparent; border: 1.5px solid var(--color-border-strong); color: var(--color-foreground); }
.btn-outline:hover { background: var(--color-muted); }
.status-filter { display: flex; gap: 2px; margin-left: auto; }
.status-filter .sf-chip {
  padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: 500;
  cursor: pointer; border: 1px solid var(--color-border); background: white;
  transition: var(--transition-fast);
}
.status-filter .sf-chip:hover { background: var(--color-muted); }
.status-filter .sf-chip.active { background: var(--color-primary); color: white; border-color: var(--color-primary); }

/* Pipeline Canvas */
.pipeline-canvas-wrap {
  overflow-x: auto; border: 1px solid var(--color-border); border-radius: var(--radius-lg);
  background: var(--color-surface); position: relative;
}
.pipeline-canvas-wrap canvas { display: block; }

/* Modal overlay */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(15,23,42,0.4); z-index: 100;
  display: flex; align-items: center; justify-content: center;
}
.modal-card {
  background: white; border-radius: var(--radius-xl); padding: var(--space-8);
  max-width: 560px; width: 90%; max-height: 85vh; overflow-y: auto;
  box-shadow: var(--shadow-lg);
}
.modal-card h3 { font-family: var(--font-heading); font-size: 20px; margin-bottom: var(--space-5); }
.modal-card label {
  display: block; font-size: 13px; font-weight: 600; color: var(--color-muted-foreground);
  margin-bottom: 4px; margin-top: var(--space-4);
}
.modal-card input, .modal-card select {
  width: 100%; padding: 10px 14px; border: 1.5px solid var(--color-border);
  border-radius: var(--radius-sm); font-size: 14px; font-family: var(--font-body);
}
.modal-card input:focus, .modal-card select:focus { border-color: var(--color-primary); outline: none; }
.modal-actions { display: flex; gap: var(--space-3); justify-content: flex-end; margin-top: var(--space-6); }

/* Milestone drawer */
.drawer-overlay {
  position: fixed; inset: 0; background: rgba(15,23,42,0.3); z-index: 200;
}
.drawer-panel {
  position: fixed; right: 0; top: 0; bottom: 0; width: 420px; max-width: 90vw;
  background: white; box-shadow: var(--shadow-lg); padding: var(--space-8);
  overflow-y: auto; z-index: 201;
}
.drawer-panel h3 { font-family: var(--font-heading); font-size: 18px; margin-bottom: var(--space-5); }
.drawer-field { margin-bottom: var(--space-4); }
.drawer-field label { font-size: 12px; font-weight: 600; color: var(--color-muted-foreground); display: block; margin-bottom: 2px; }
.drawer-field .val { font-size: 14px; }
.status-badge {
  display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600;
}
.status-pending { background: #F1F5FD; color: #64748B; }
.status-in_progress { background: #EFF6FF; color: #2563EB; }
.status-completed { background: #ECFDF5; color: #059669; }
.status-blocked { background: #FEF2F2; color: #DC2626; }

/* List view table */
.pj-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.pj-table th { text-align: left; padding: 10px 14px; border-bottom: 2px solid var(--color-border); font-weight: 600; color: var(--color-muted-foreground); }
.pj-table td { padding: 10px 14px; border-bottom: 1px solid var(--color-border); }
.pj-table tr:hover td { background: var(--color-muted); }
```

- [ ] **Step 2: 在 tabs 区域添加 Tab C 按钮**

将现有两行 tab 按钮改为三行：

```html
  <!-- Tabs -->
  <div class="tabs">
    <div class="tab" :class="{active: activeTab==='evaluate'}" @click="activeTab='evaluate'">名称评估</div>
    <div class="tab" :class="{active: activeTab==='recommend'}" @click="activeTab='recommend'">智能推荐</div>
    <div class="tab" :class="{active: activeTab==='projects'}" @click="activeTab='projects'">项目管理</div>
  </div>
```

- [ ] **Step 3: 在 Tab B 的 `</div>` 之后添加 Tab C 基础模板**

在 `<!-- ==================== TAB B 结束 ==================== -->` 或等效闭合 `</div>` 之后插入：

```html
  <!-- ==================== TAB C: 项目管理 ==================== -->
  <div v-if="activeTab==='projects'">
    <!-- Toolbar -->
    <div class="pipeline-toolbar">
      <button class="btn btn-primary" @click="pjShowCreate=true">+ 新建项目</button>
      <button class="btn btn-outline" @click="pjTriggerFile.click()">导入 CSV</button>
      <input type="file" accept=".csv" style="display:none" ref="pjTriggerFile" @change="pjImportCsv">
      <button class="btn btn-outline" @click="pjViewMode = pjViewMode==='gantt' ? 'list' : 'gantt'">
        {{ pjViewMode === 'gantt' ? '列表视图' : '管线图视图' }}
      </button>
      <div class="status-filter">
        <span class="sf-chip" :class="{active: pjFilter===''}" @click="pjFilter=''">全部</span>
        <span class="sf-chip" :class="{active: pjFilter==='on_track'}" @click="pjFilter='on_track'">进行中</span>
        <span class="sf-chip" :class="{active: pjFilter==='completed'}" @click="pjFilter='completed'">已完成</span>
        <span class="sf-chip" :class="{active: pjFilter==='at_risk'}" @click="pjFilter='at_risk'">卡点</span>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="pjFiltered.length === 0" style="text-align:center;padding:80px 20px;color:var(--color-muted-foreground);">
      <div style="font-size:48px;margin-bottom:16px;">📋</div>
      <div style="font-size:16px;font-weight:600;">尚无项目，创建第一个项目开始追踪</div>
      <div style="font-size:13px;margin-top:8px;">点击"+ 新建项目"或导入 CSV 文件</div>
    </div>

    <!-- Gantt View Placeholder (Task 8 fills this in) -->
    <div v-if="pjViewMode==='gantt' && pjFiltered.length > 0" style="padding:20px;text-align:center;color:var(--color-muted-foreground);">
      管线图加载中...
    </div>

    <!-- List View -->
    <div v-if="pjViewMode==='list' && pjFiltered.length > 0">
      <table class="pj-table">
        <thead>
          <tr>
            <th>项目名称</th><th>CAS号</th><th>当前阶段</th><th>状态</th><th>创建时间</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in pjFiltered" :key="p.id">
            <td style="font-weight:600;">{{ p.name }}</td>
            <td style="font-family:var(--font-mono);">{{ p.cas_number || '—' }}</td>
            <td>{{ pjPhaseName(p.current_phase) }}</td>
            <td><span class="status-badge" :class="'status-'+pjStatusBadgeClass(p.overall_status)">{{ pjStatusLabel(p.overall_status) }}</span></td>
            <td style="color:var(--color-muted-foreground);">{{ p.created_at?.slice(0,10) }}</td>
            <td>
              <button class="btn btn-outline" style="font-size:11px;padding:4px 10px;" @click="pjDeleteProject(p.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Create Project Modal -->
    <div class="modal-overlay" v-if="pjShowCreate" @click.self="pjShowCreate=false">
      <div class="modal-card">
        <h3>新建项目档案</h3>
        <label>项目名称</label>
        <input v-model="pjForm.name" placeholder="如 AMG-001">
        <label>CAS号 <span style="font-weight:400;">(可选，留空则从 CAS 申请开始)</span></label>
        <input v-model="pjForm.cas_number" placeholder="如 123456-78-9">
        <label>靶点分类</label>
        <select v-model="pjForm.target_class">
          <option v-for="t in pjTargetClasses" :value="t">{{ t }}</option>
        </select>
        <label>作用机制</label>
        <select v-model="pjForm.mechanism">
          <option v-for="m in pjMechanisms" :value="m">{{ m }}</option>
        </select>
        <label>化合物类型</label>
        <select v-model="pjForm.chemical_class">
          <option v-for="c in pjChemicalClasses" :value="c">{{ c }}</option>
        </select>
        <label>适应症</label>
        <input v-model="pjForm.indication" placeholder="如 非小细胞肺癌">
        <div class="modal-actions">
          <button class="btn btn-outline" @click="pjShowCreate=false">取消</button>
          <button class="btn btn-primary" @click="pjCreateProject">创建项目</button>
        </div>
      </div>
    </div>
  </div>
```

- [ ] **Step 4: 追加 Vue setup() 中的 Tab C 状态和方法**

在 `return {` 之前追加：

```javascript
    // ========== Tab C: Project Pipeline Management ==========
    const pjProjects = ref([]);
    const pjFilter = ref('');
    const pjViewMode = ref('gantt');
    const pjShowCreate = ref(false);
    const pjTriggerFile = ref(null);
    const pjDrawer = ref(null);  // { milestone, project }
    const pjForm = reactive({ name: '', cas_number: '', target_class: 'kinase', mechanism: 'inhibitor', chemical_class: 'small_molecule', indication: '' });
    const pjTargetClasses = ['kinase','gpcr','ion_channel','nuclear_receptor','protease','transporter','cytokine','growth_factor','immune_checkpoint','cox','opioid_receptor','sodium_channel','histamine_receptor','leukotriene_receptor','beta_adrenoceptor','muscarinic_receptor','bacterial_target','viral_target','fungal_target','tnf_superfamily','complement','integrin','other'];
    const pjMechanisms = ['inhibitor','activator','agonist','antagonist','modulator','blocker','antibody','fusion_protein','gene_therapy','antisense','vaccine','other'];
    const pjChemicalClasses = ['small_molecule','monoclonal_antibody','antibody_fragment','bispecific_antibody','antibody_drug_conjugate','fusion_protein','peptide','oligonucleotide','mrna','sirna','other'];

    const pjFiltered = computed(() => {
      let list = pjProjects.value;
      if (pjFilter.value) list = list.filter(p => p.overall_status === pjFilter.value);
      return list;
    });

    const pjPhaseName = (id) => ({ cas_application:'CAS申请', inn_naming:'INN命名', chinese_submission:'中文名提交', pharmacopoeia_review:'药典委核名', trademark:'商标品牌' }[id] || id);
    const pjStatusLabel = (s) => ({ on_track:'进行中', at_risk:'有风险', delayed:'已延误', completed:'已完成' }[s] || s);
    const pjStatusBadgeClass = (s) => s;

    async function pjLoadProjects() {
      try {
        const res = await fetch('/api/v1/projects/');
        if (!res.ok) throw new Error(await res.text());
        pjProjects.value = await res.json();
      } catch(e) { console.error('Load projects failed:', e); }
    }

    async function pjCreateProject() {
      const body = {
        name: pjForm.name,
        cas_number: pjForm.cas_number || null,
        molecule: {
          molecule_id: pjForm.name,
          common_name: pjForm.name,
          properties: {
            target_class: pjForm.target_class,
            mechanism: pjForm.mechanism,
            chemical_class: pjForm.chemical_class,
            indication: pjForm.indication,
          }
        }
      };
      try {
        const res = await fetch('/api/v1/projects/', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
        if (!res.ok) throw new Error(await res.text());
        pjShowCreate.value = false;
        Object.assign(pjForm, { name:'', cas_number:'', indication:'' });
        await pjLoadProjects();
      } catch(e) { alert('创建失败: '+e.message); }
    }

    async function pjImportCsv(e) {
      const file = e.target.files[0];
      if (!file) return;
      const form = new FormData();
      form.append('file', file);
      try {
        const res = await fetch('/api/v1/projects/import', { method:'POST', body:form });
        if (!res.ok) throw new Error(await res.text());
        await pjLoadProjects();
        alert('导入成功');
      } catch(e) { alert('导入失败: '+e.message); }
      e.target.value = '';
    }

    async function pjDeleteProject(id) {
      if (!confirm('确定删除此项目？')) return;
      try {
        await fetch('/api/v1/projects/'+id, { method:'DELETE' });
        await pjLoadProjects();
      } catch(e) { alert('删除失败: '+e.message); }
    }

    // Load projects on tab switch
    const pjLoaded = ref(false);
    watch(activeTab, (tab) => { if (tab === 'projects' && !pjLoaded.value) { pjLoadProjects(); pjLoaded.value = true; } });
    watch(() => pjProjects.value.length, () => { if (pjProjects.value.length > 0) pjLoaded.value = true; });
```

- [ ] **Step 5: 在 return 对象中追加导出**

在 `return {` 对象中追加：

```javascript
      pjProjects, pjFilter, pjViewMode, pjShowCreate, pjTriggerFile, pjDrawer,
      pjForm, pjTargetClasses, pjMechanisms, pjChemicalClasses,
      pjFiltered, pjPhaseName, pjStatusLabel, pjStatusBadgeClass,
      pjLoadProjects, pjCreateProject, pjImportCsv, pjDeleteProject,
```

- [ ] **Step 6: 验证前端无 JS 语法错误**

```bash
cd /Users/owen/projectcc && python3 -c "
with open('src/drug_naming/static/index.html') as f:
    html = f.read()
# Basic sanity: check Vue.createApp and .mount exist
assert 'createApp' in html
assert '.mount(' in html
assert '项目管理' in html
assert 'pjCreateProject' in html
assert 'pjLoadProjects' in html
print('HTML sanity check passed')
"
```
Expected: `HTML sanity check passed`

- [ ] **Step 7: Commit**

```bash
git add src/drug_naming/static/index.html
git commit -m "feat(ui): add Tab C with create/import/list project views"
```

---

### Task 8: 前端管线图 Canvas 组件

**Files:**
- Modify: `src/drug_naming/static/index.html` (replace Gantt placeholder + add JS rendering logic)

- [ ] **Step 1: 替换管线图占位符为 canvas + drawer**

在 `<!-- Gantt View Placeholder -->` 处替换为：

```html
    <!-- Gantt View -->
    <div v-if="pjViewMode==='gantt' && pjFiltered.length > 0" class="pipeline-canvas-wrap" ref="pjCanvasWrap">
      <canvas ref="pjCanvas" :width="pjCanvasWidth" :height="pjCanvasHeight" style="cursor:pointer;" @click="pjCanvasClick"></canvas>
    </div>

    <!-- Milestone Drawer -->
    <div class="drawer-overlay" v-if="pjDrawer" @click.self="pjDrawer=null">
      <div class="drawer-panel">
        <h3>{{ pjDrawer.milestone.name }}</h3>
        <div style="margin-bottom:16px;font-size:13px;color:var(--color-muted-foreground);">
          项目: {{ pjDrawer.project.name }} · {{ pjPhaseName(pjDrawer.milestone.phase) }}
        </div>
        <div class="drawer-field">
          <label>状态</label>
          <select v-model="pjDrawer.milestone.status" @change="pjUpdateMilestone(pjDrawer.project.id, pjDrawer.milestone)" style="width:100%;padding:8px 12px;border:1.5px solid var(--color-border);border-radius:var(--radius-sm);">
            <option value="pending">待开始</option>
            <option value="in_progress">进行中</option>
            <option value="completed">已完成</option>
            <option value="blocked">已阻塞</option>
          </select>
        </div>
        <div class="drawer-field">
          <label>最快路径</label>
          <div class="val">{{ pjDrawer.milestone.fastest_start }} → {{ pjDrawer.milestone.fastest_end }} ({{ pjDrawer.milestone.fastest_days }}工作日)</div>
        </div>
        <div class="drawer-field">
          <label>最慢路径</label>
          <div class="val">{{ pjDrawer.milestone.slowest_start }} → {{ pjDrawer.milestone.slowest_end }} ({{ pjDrawer.milestone.slowest_days }}工作日)</div>
        </div>
        <div class="drawer-field" v-if="pjDrawer.milestone.actual_start">
          <label>实际开始</label><div class="val">{{ pjDrawer.milestone.actual_start }}</div>
        </div>
        <div class="drawer-field" v-if="pjDrawer.milestone.actual_end">
          <label>实际完成</label><div class="val">{{ pjDrawer.milestone.actual_end }}</div>
        </div>
        <div class="drawer-field">
          <label>备注</label>
          <input v-model="pjDrawer.milestone.notes" @change="pjUpdateMilestone(pjDrawer.project.id, pjDrawer.milestone)" placeholder="添加备注...">
        </div>
        <div style="margin-top:24px;">
          <button class="btn btn-outline" @click="pjDrawer=null" style="width:100%;">关闭</button>
        </div>
      </div>
    </div>
```

- [ ] **Step 2: 追加 Canvas 渲染函数**

在 `pjDeleteProject` 函数之后，`// Load projects on tab switch` 之前追加：

```javascript
    // ===== Pipeline Gantt Canvas =====
    const pjCanvas = ref(null);
    const pjCanvasWrap = ref(null);
    const pjCanvasWidth = ref(1200);
    const pjCanvasHeight = ref(600);

    const PHASE_COLORS = {
      cas_application: '#E2E8F0', inn_naming: '#DBEAFE',
      chinese_submission: '#D1FAE5', pharmacopoeia_review: '#EDE9FE',
      trademark: '#FED7AA',
    };
    const STATUS_COLORS = {
      pending: '#94A3B8', in_progress: '#3B82F6',
      completed: '#10B981', blocked: '#EF4444',
    };

    function pjRenderGantt() {
      const canvas = pjCanvas.value;
      if (!canvas) return;
      const wrap = pjCanvasWrap.value;
      const dpr = window.devicePixelRatio || 1;
      const projects = pjFiltered.value;
      if (projects.length === 0) return;

      // Determine date range across all projects
      let minDate = new Date();
      let maxDate = new Date();
      maxDate.setMonth(maxDate.getMonth() + 6);
      for (const p of projects) {
        for (const ph of (p.phases || [])) {
          for (const m of (ph.milestones || [])) {
            for (const d of [m.fastest_start, m.fastest_end, m.slowest_start, m.slowest_end]) {
              if (!d) continue;
              const dt = new Date(d);
              if (dt < minDate) minDate = dt;
              if (dt > maxDate) maxDate = dt;
            }
          }
        }
      }
      // Pad range
      minDate = new Date(minDate.getFullYear(), minDate.getMonth(), 1);
      maxDate = new Date(maxDate.getFullYear(), maxDate.getMonth() + 2, 0);
      const totalDays = Math.ceil((maxDate - minDate) / (1000*60*60*24));

      // Layout
      const leftPad = 160;
      const rowH = 44;
      const phaseH = 16;
      const headerH = 40;
      const topPad = headerH + 10;
      const rowsPerProject = 2; // fastest + slowest
      const projectGap = 8;
      const totalH = topPad + projects.length * (rowsPerProject * rowH + phaseH + projectGap) + 20;

      const contentW = Math.max(wrap.clientWidth - leftPad - 20, 400);
      const dayW = contentW / Math.max(totalDays, 1);

      pjCanvasWidth.value = leftPad + contentW + 20;
      pjCanvasHeight.value = totalH;

      // Wait for canvas size to be applied
      setTimeout(() => {
        const canvas2 = pjCanvas.value;
        if (!canvas2) return;
        canvas2.width = pjCanvasWidth.value * dpr;
        canvas2.height = pjCanvasHeight.value * dpr;
        canvas2.style.width = pjCanvasWidth.value + 'px';
        canvas2.style.height = pjCanvasHeight.value + 'px';
        const ctx = canvas2.getContext('2d');
        ctx.scale(dpr, dpr);
        ctx.clearRect(0, 0, canvas2.width, canvas2.height);

        // Store hit targets
        const _hits = [];

        // Month header
        ctx.font = '11px "Noto Sans", sans-serif';
        ctx.fillStyle = '#64748B';
        const months = [];
        let cursor = new Date(minDate);
        while (cursor <= maxDate) {
          months.push(new Date(cursor));
          cursor.setMonth(cursor.getMonth() + 1);
        }
        for (const mStart of months) {
          const mEnd = new Date(mStart.getFullYear(), mStart.getMonth()+1, 0);
          const x = leftPad + Math.ceil((mStart - minDate) / (1000*60*60*24)) * dayW;
          const w = (Math.ceil((mEnd - mStart) / (1000*60*60*24)) + 1) * dayW;
          ctx.fillStyle = (months.indexOf(mStart) % 2 === 0) ? '#F8FAFC' : '#FFFFFF';
          ctx.fillRect(x, 0, w, totalH);
          ctx.fillStyle = '#94A3B8';
          ctx.fillText(mStart.getFullYear() + '/' + (mStart.getMonth()+1), x + 6, headerH - 10);
          // Grid line
          ctx.strokeStyle = '#E2E8F0';
          ctx.lineWidth = 0.5;
          ctx.beginPath();
          ctx.moveTo(x, headerH);
          ctx.lineTo(x, totalH);
          ctx.stroke();
        }

        // Today line
        const today = new Date();
        if (today >= minDate && today <= maxDate) {
          const tx = leftPad + Math.ceil((today - minDate) / (1000*60*60*24)) * dayW;
          ctx.strokeStyle = '#EF4444';
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(tx, headerH);
          ctx.lineTo(tx, totalH);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.fillStyle = '#EF4444';
          ctx.fillText('今天', tx + 4, headerH - 4);
        }

        // Render each project
        for (let pi = 0; pi < projects.length; pi++) {
          const project = projects[pi];
          const baseY = topPad + pi * (rowsPerProject * rowH + phaseH + projectGap);

          // Project name
          ctx.fillStyle = '#0F172A';
          ctx.font = '600 13px "Noto Sans", sans-serif';
          ctx.fillText(project.name, 8, baseY + 20);

          // Phase background bands
          for (const phase of (project.phases || [])) {
            const color = PHASE_COLORS[phase.id] || '#F1F5FD';
            const firstM = phase.milestones[0];
            const lastM = phase.milestones[phase.milestones.length - 1];
            if (!firstM || !lastM) continue;
            const pStart = new Date(firstM.fastest_start || minDate);
            const pEnd = new Date(lastM.fastest_end || maxDate);
            const px = leftPad + Math.ceil((pStart - minDate) / (1000*60*60*24)) * dayW;
            const pw = Math.max(Math.ceil((pEnd - pStart) / (1000*60*60*24)) * dayW, 20);
            const py = baseY - 2;
            const ph = rowsPerProject * rowH + 4;
            ctx.fillStyle = color;
            ctx.fillRect(px, py, pw, ph);
          }

          // Fastest path row (green solid)
          const fy = baseY + 10;
          ctx.strokeStyle = '#10B981';
          ctx.lineWidth = 3;
          ctx.beginPath();
          let firstF = true;
          for (const phase of (project.phases || [])) {
            for (const m of (phase.milestones || [])) {
              if (!m.fastest_start || !m.fastest_end) continue;
              const mx = leftPad + Math.ceil((new Date(m.fastest_start) - minDate) / (1000*60*60*24)) * dayW;
              const my = fy + rowH/2;
              if (firstF) { ctx.moveTo(mx, my); firstF = false; }
              else ctx.lineTo(mx, my);
              const ex = leftPad + Math.ceil((new Date(m.fastest_end) - minDate) / (1000*60*60*24)) * dayW;
              ctx.lineTo(ex, my);
              // Node
              ctx.fillStyle = STATUS_COLORS[m.status] || '#94A3B8';
              ctx.beginPath();
              ctx.arc(ex, my, 6, 0, Math.PI*2);
              ctx.fill();
              ctx.strokeStyle = '#FFFFFF';
              ctx.lineWidth = 2;
              ctx.stroke();
              ctx.strokeStyle = '#10B981';
              ctx.lineWidth = 3;
              // Store hit
              _hits.push({ x: ex, y: my, r: 8, project, milestone: m });
              ctx.beginPath();
              ctx.moveTo(ex, my);
            }
          }
          ctx.stroke();

          // Slowest path row (gray dashed)
          const sy = fy + rowH;
          ctx.strokeStyle = '#94A3B8';
          ctx.lineWidth = 2;
          ctx.setLineDash([6, 4]);
          ctx.beginPath();
          let firstS = true;
          for (const phase of (project.phases || [])) {
            for (const m of (phase.milestones || [])) {
              if (!m.slowest_start || !m.slowest_end) continue;
              const mx = leftPad + Math.ceil((new Date(m.slowest_start) - minDate) / (1000*60*60*24)) * dayW;
              const my = sy + rowH/2;
              if (firstS) { ctx.moveTo(mx, my); firstS = false; }
              else ctx.lineTo(mx, my);
              const ex = leftPad + Math.ceil((new Date(m.slowest_end) - minDate) / (1000*60*60*24)) * dayW;
              ctx.lineTo(ex, my);
              ctx.fillStyle = '#CBD5E1';
              ctx.beginPath();
              ctx.arc(ex, my, 4, 0, Math.PI*2);
              ctx.fill();
              _hits.push({ x: ex, y: my, r: 8, project, milestone: m });
              ctx.beginPath();
              ctx.moveTo(ex, my);
            }
          }
          ctx.stroke();
          ctx.setLineDash([]);

          // Legend
          ctx.fillStyle = '#10B981';
          ctx.font = '10px "Noto Sans", sans-serif';
          ctx.fillText('最快', 8, fy + rowH/2 + 4);
          ctx.fillStyle = '#94A3B8';
          ctx.fillText('最慢', 8, sy + rowH/2 + 4);
        }

        // Store hits for click handler
        canvas2._hits = _hits;
      }, 50);
    }

    function pjCanvasClick(e) {
      const canvas = pjCanvas.value;
      if (!canvas || !canvas._hits) return;
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      for (const hit of canvas._hits) {
        const dx = mx - hit.x;
        const dy = my - hit.y;
        if (Math.sqrt(dx*dx + dy*dy) <= hit.r) {
          pjDrawer.value = { project: hit.project, milestone: hit.milestone };
          return;
        }
      }
    }

    async function pjUpdateMilestone(projectId, milestone) {
      try {
        const res = await fetch(`/api/v1/projects/${projectId}/milestones/${milestone.id}`, {
          method: 'PATCH', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({
            status: milestone.status,
            notes: milestone.notes,
            actual_start: milestone.actual_start,
            actual_end: milestone.actual_end,
          })
        });
        if (!res.ok) throw new Error(await res.text());
        const updated = await res.json();
        // Refresh project in local list
        const idx = pjProjects.value.findIndex(p => p.id === projectId);
        if (idx >= 0) {
          pjProjects.value[idx] = updated;
          pjProjects.value = [...pjProjects.value]; // trigger reactivity
        }
        pjRenderGantt();
      } catch(e) { alert('更新失败: '+e.message); }
    }

    // Re-render when filter/view changes
    watch(pjFilter, () => { setTimeout(pjRenderGantt, 100); });
    watch(pjViewMode, (mode) => { if (mode === 'gantt') setTimeout(pjRenderGantt, 100); });
    watch(pjProjects, () => { setTimeout(pjRenderGantt, 100); }, { deep: true });
```

- [ ] **Step 3: 在 return 对象中追加 Canvas 相关导出**

```javascript
      pjCanvas, pjCanvasWrap, pjCanvasWidth, pjCanvasHeight,
      pjRenderGantt, pjCanvasClick, pjUpdateMilestone,
```

- [ ] **Step 4: 在 Tab 切换监听中追加重绘**

修改 watch on activeTab 以重绘：

```javascript
    watch(activeTab, (tab) => {
      if (tab === 'projects') {
        if (!pjLoaded.value) { pjLoadProjects(); pjLoaded.value = true; }
        setTimeout(pjRenderGantt, 200);
      }
    });
```

- [ ] **Step 5: 验证 HTML 完整性**

```bash
cd /Users/owen/projectcc && python3 -c "
with open('src/drug_naming/static/index.html') as f:
    html = f.read()
checks = ['pjRenderGantt', 'pjCanvasClick', 'pjCanvas', 'PHASE_COLORS', 'pjUpdateMilestone']
for c in checks:
    assert c in html, f'Missing: {c}'
print('All canvas functions present')
"
```
Expected: `All canvas functions present`

- [ ] **Step 6: Commit**

```bash
git add src/drug_naming/static/index.html
git commit -m "feat(ui): add Canvas Gantt pipeline view with dual timeline and milestone drawer"
```

---

### Task 9: 集成测试与调试

**Files:**
- Modify: (none — testing only)

- [ ] **Step 1: 安装包并启动服务**

```bash
cd /Users/owen/projectcc && pip3 install -e . 2>&1 | tail -5
```

- [ ] **Step 2: 启动服务并验证 API**

```bash
# Start server in background
cd /Users/owen/projectcc && python3 -m uvicorn src.drug_naming.main:app --host 0.0.0.0 --port 8000 &
sleep 3

# Test: create project without CAS
curl -s -X POST http://localhost:8000/api/v1/projects/ \
  -H 'Content-Type: application/json' \
  -d '{"name":"AMG-001","molecule":{"molecule_id":"AMG-001","common_name":"AMG-001","properties":{"target_class":"kinase","mechanism":"inhibitor","chemical_class":"small_molecule","indication":"非小细胞肺癌"}}}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Created: {d[\"name\"]} with {len(d[\"phases\"])} phases')"
```
Expected: `Created: AMG-001 with 5 phases`

- [ ] **Step 3: Test milestone update**

```bash
# Get project ID and first milestone
PROJ=$(curl -s http://localhost:8000/api/v1/projects/ | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
MID=$(curl -s http://localhost:8000/api/v1/projects/$PROJ | python3 -c "import sys,json; print(json.load(sys.stdin)['phases'][0]['milestones'][0]['id'])")
echo "Project: $PROJ, Milestone: $MID"

# Update milestone status
curl -s -X PATCH "http://localhost:8000/api/v1/projects/$PROJ/milestones/$MID" \
  -H 'Content-Type: application/json' \
  -d '{"status":"in_progress"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Status updated: {d[\"overall_status\"]}, current: {d[\"current_milestone\"]}')"
```
Expected: status updated response

- [ ] **Step 4: Test recalculate**

```bash
curl -s -X POST "http://localhost:8000/api/v1/projects/$PROJ/recalculate" | python3 -c "import sys,json; d=json.load(sys.stdin); m0=d['phases'][0]['milestones'][0]; print(f'Recalculated: {m0[\"fastest_start\"]} -> {m0[\"fastest_end\"]}')"
```
Expected: dates present

- [ ] **Step 5: Test CSV import**

```bash
echo 'project_name,cas_number,target_class,mechanism,indication,chemical_class
XYZ-002,123456-78-9,cox,inhibitor,骨关节炎疼痛,small_molecule
TEST-003,,kinase,antagonist,类风湿,small_molecule' > /tmp/test_import.csv

curl -s -X POST http://localhost:8000/api/v1/projects/import \
  -F "file=@/tmp/test_import.csv" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Imported {len(d)} projects')"
```
Expected: `Imported 2 projects`

- [ ] **Step 6: Stop server and verify JSON persistence**

```bash
kill %1 2>/dev/null || true
python3 -c "
import json
with open('src/drug_naming/data/projects.json') as f:
    data = json.load(f)
print(f'{len(data)} projects persisted:')
for p in data:
    print(f'  - {p[\"name\"]} ({len(p[\"phases\"])} phases)')
"
```
Expected: 3+ projects listed

- [ ] **Step 7: Commit (if everything passes)**

```bash
# Clean up test data
kill %1 2>/dev/null || true
echo '[]' > src/drug_naming/data/projects.json
git add src/drug_naming/data/projects.json
git commit -m "test: verify API CRUD, CSV import, and JSON persistence work correctly"
```

---

### Task 10: 版本号更新与最终提交

**Files:**
- Modify: `src/drug_naming/static/index.html` (version string)
- Modify: `pyproject.toml` (version string)

- [ ] **Step 1: 更新版本号**

```bash
# Update HTML version
sed -i '' 's/v0\.2\.2/v0.3.0/' /Users/owen/projectcc/src/drug_naming/static/index.html

# Update pyproject.toml version
sed -i '' 's/version = "0.1.0"/version = "0.3.0"/' /Users/owen/projectcc/pyproject.toml
```

- [ ] **Step 2: 最终验证**

```bash
cd /Users/owen/projectcc && pip3 install -e . 2>&1 | tail -3
python3 -c "
from src.drug_naming.models.project import Milestone, Phase, Project, build_default_phases
from src.drug_naming.engines.date_calculator import add_working_days, recalculate_project_dates
from src.drug_naming.api.projects import router
print('All imports successful')
print(f'API routes: {len(router.routes)}')
phases = build_default_phases(has_cas=False)
print(f'Default phases with no CAS: {len(phases)} phases, {sum(len(p.milestones) for p in phases)} milestones')
phases = build_default_phases(has_cas=True)
print(f'Default phases with CAS: {len(phases)} phases, {sum(len(p.milestones) for p in phases)} milestones')
print('v0.3.0 ready')
"
```
Expected: 所有导入成功，里程碑数量正确

- [ ] **Step 3: Commit**

```bash
git add src/drug_naming/static/index.html pyproject.toml
git commit -m "chore: bump version to v0.3.0"
```

- [ ] **Step 4: Tag**

```bash
git tag -a v0.3.0 -m "v0.3.0: 项目管线管理模块 — 双时间线甘特图 + 路径分叉 + JSON持久化"
```
```

---

## Verification Checklist

- [ ] `python3 -c "from src.drug_naming.models.project import *"` — 模型可导入
- [ ] `python3 -c "from src.drug_naming.engines.date_calculator import *"` — 日期引擎可导入
- [ ] `python3 -c "from src.drug_naming.api.projects import router"` — API 路由可导入
- [ ] 服务器启动无错误
- [ ] POST `/api/v1/projects/` 创建项目返回含 phases 的 Project
- [ ] GET `/api/v1/projects/` 列表正确
- [ ] PATCH `/api/v1/projects/{id}/milestones/{mid}` 更新状态成功
- [ ] POST `/api/v1/projects/{id}/recalculate` 重算日期
- [ ] POST `/api/v1/projects/import` CSV 导入成功
- [ ] DELETE `/api/v1/projects/{id}` 删除成功
- [ ] `projects.json` 文件在创建/修改后持久化数据
- [ ] 前端 Tab C 可切换显示
- [ ] 新建项目表单可提交
- [ ] 列表视图正确展示项目
- [ ] 管线图 Canvas 渲染无 JS 错误
- [ ] 管线图节点点击弹出抽屉
- [ ] 抽屉中状态/备注可更新

---

## 已知限制与后续改进

1. **法定假日**: 当前日期计算仅跳过周末，未处理中国法定假日。可在 `date_calculator.py` 中加入 `HOLIDAYS` 列表。
2. **分子式/结构式**: MoleculeInput 中暂无化学结构字段，后续可扩展。
3. **管线图拖拽**: 规格中提到支持拖拽里程碑日期，本版未实现，可作为 v0.3.1。
4. **路径自动分叉**: 当前默认展示两条路径的所有里程碑；路径 A/B 的自动过滤（基于 NDA 日期）已在前端逻辑中预留但未完全实现自动判断。
5. **响应式**: 管线图 Canvas 在窗口 resize 时需要手动重绘，未监听 resize 事件。
