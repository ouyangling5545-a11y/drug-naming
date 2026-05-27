from __future__ import annotations
import json
import csv
import io
from pathlib import Path
from datetime import date, datetime, timezone
from uuid import UUID
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, UploadFile, File
from ..models.molecule import (
    MoleculeInput, PharmacologicalProperties, TargetClass, Mechanism, ChemicalClass,
)
from ..models.project import (
    Project, Phase, Milestone, MilestoneStatus,
    ProjectStatus, build_default_phases, MilestoneDateOverride,
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
    nda_date: date | None = None
    molecule: MoleculeInput
    milestone_overrides: list[MilestoneDateOverride] | None = None
    manual_path: str | None = None  # 'A', 'B', or None (auto-detect via NDA date)


def _apply_milestone_overrides(project: Project, overrides: list[MilestoneDateOverride]) -> None:
    """Apply milestone planned-date overrides to a project after recalculation."""
    override_map = {o.milestone_id: o for o in overrides}
    for phase in project.phases:
        for m in phase.milestones:
            if m.id in override_map:
                ov = override_map[m.id]
                if ov.planned_start is not None:
                    m.planned_start = ov.planned_start
                if ov.planned_end is not None:
                    m.planned_end = ov.planned_end


@router.post("/", response_model=Project)
def create_project(body: CreateProjectBody) -> Project:
    """Create a new pipeline project with default phases."""
    projects = _load()
    has_cas = bool(body.cas_number and body.cas_number.strip())
    phases = build_default_phases(has_cas)
    project = Project(
        name=body.name,
        cas_number=body.cas_number.strip() if body.cas_number else None,
        nda_date=body.nda_date,
        molecule=body.molecule,
        phases=phases,
    )
    recalculate_project_dates(project)
    if body.manual_path and body.manual_path in ('A', 'B'):
        project.active_path = body.manual_path
    if body.milestone_overrides:
        _apply_milestone_overrides(project, body.milestone_overrides)
    projects[project.id] = project
    _save(projects)
    return project


@router.post("/preview", response_model=Project)
def preview_project(body: CreateProjectBody) -> Project:
    """Preview milestone dates for a new project without saving."""
    has_cas = bool(body.cas_number and body.cas_number.strip())
    phases = build_default_phases(has_cas)
    project = Project(
        name=body.name,
        cas_number=body.cas_number.strip() if body.cas_number else None,
        nda_date=body.nda_date,
        molecule=body.molecule,
        phases=phases,
    )
    recalculate_project_dates(project)
    if body.manual_path and body.manual_path in ('A', 'B'):
        project.active_path = body.manual_path
    if body.milestone_overrides:
        _apply_milestone_overrides(project, body.milestone_overrides)
    return project


@router.get("/", response_model=list[Project])
def list_projects(status: str | None = None) -> list[Project]:
    """List all projects, optionally filtered by overall_status."""
    projects = _load()
    result = list(projects.values())
    if status:
        result = [p for p in result if p.overall_status == status]
    return sorted(result, key=lambda p: (p.sort_order, -p.created_at.timestamp()))


@router.post("/{project_id}/move", response_model=list[Project])
def move_project(project_id: UUID, direction: str = "up") -> list[Project]:
    """Move a project up or down in display order."""
    projects = _load()
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")

    sorted_projects = sorted(projects.values(), key=lambda p: (p.sort_order, -p.created_at.timestamp()))
    idx = None
    for i, p in enumerate(sorted_projects):
        if p.id == project_id:
            idx = i
            break

    if idx is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if direction == "up" and idx > 0:
        sorted_projects[idx], sorted_projects[idx - 1] = sorted_projects[idx - 1], sorted_projects[idx]
    elif direction == "down" and idx < len(sorted_projects) - 1:
        sorted_projects[idx], sorted_projects[idx + 1] = sorted_projects[idx + 1], sorted_projects[idx]

    # Renumber all sort_order values to keep them clean
    for i, p in enumerate(sorted_projects):
        p.sort_order = i

    _save(projects)
    return sorted(projects.values(), key=lambda p: (p.sort_order, -p.created_at.timestamp()))


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


# ===== Task 5: Milestone update + Recalculate =====

class UpdateMilestoneBody(BaseModel):
    status: MilestoneStatus | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    fastest_start: date | None = None
    fastest_end: date | None = None
    slowest_start: date | None = None
    slowest_end: date | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    depends_on: list[str] | None = None
    notes: str | None = None
    result: str | None = None


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

    for phase in sorted(project.phases, key=lambda p: p.order):
        for m in sorted(phase.milestones, key=lambda x: x.order):
            if m.status != MilestoneStatus.COMPLETED:
                project.current_phase = phase.id
                project.current_milestone = m.id
                return

    project.current_phase = project.phases[-1].id if project.phases else ""
    project.current_milestone = ""


# ===== Task 6: CSV Import =====

@router.post("/import", response_model=list[Project])
async def import_projects_csv(file: UploadFile = File(...)) -> list[Project]:
    """Import projects from a CSV file.

    Expected columns:
    project_name,cas_number,target_class,mechanism,indication,chemical_class
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

    for row in reader:
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
