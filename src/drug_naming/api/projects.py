from __future__ import annotations
from datetime import datetime, timezone
from uuid import UUID
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from ..models.molecule import MoleculeInput
from ..models.project import NamingProject, ProjectStatus, WorkflowStep, Decision
from ..engines.stem_matcher import StemMatchingEngine
from ..engines.name_generator import NameGenerationEngine
from ..engines.poca_scorer import POCAScoringEngine
from ..engines.chinese_name import ChineseNameEngine
from ..engines.brand_name import BrandNameEngine
from ..models.naming import NameGenerationConstraints, NameGenerationRequest
from ..models.poca import POCARequest
from ..models.chinese import ChineseNameRequest
from ..models.brand import BrandScreenRequest
from ..data.inn_reference import get_inn_reference_db
from .stems import _get_default_provider

router = APIRouter()

# In-memory project store (would be replaced with database)
_PROJECTS: dict[UUID, NamingProject] = {}


@router.post("/", response_model=NamingProject)
def create_project(molecule: MoleculeInput) -> NamingProject:
    """Create a new naming project for a molecule."""
    project = NamingProject(molecule=molecule)
    _PROJECTS[project.id] = project
    return project


@router.get("/{project_id}", response_model=NamingProject)
def get_project(project_id: UUID) -> NamingProject:
    """Get a naming project by ID."""
    project = _PROJECTS.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/", response_model=list[NamingProject])
def list_projects() -> list[NamingProject]:
    """List all naming projects."""
    return list(_PROJECTS.values())


@router.post("/{project_id}/workflow/stem-matching", response_model=NamingProject)
def run_stem_matching(project_id: UUID) -> NamingProject:
    """Run stem matching step in the workflow."""
    project = _PROJECTS.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    step = WorkflowStep(step_name="stem_matching", status=ProjectStatus.STEM_MATCHING,
                        started_at=datetime.now(timezone.utc))

    provider = _get_default_provider()
    engine = StemMatchingEngine(provider)
    matches = engine.match(project.molecule.properties)
    project.stem_matches = matches
    project.status = ProjectStatus.NAME_GENERATION

    step.completed_at = datetime.now(timezone.utc)
    step.result_summary = {"matched_count": len(matches), "top_match": matches[0].stem.stem if matches else "none"}
    step.decision = Decision.APPROVED if matches else Decision.REJECTED
    project.workflow.append(step)
    project.updated_at = datetime.now(timezone.utc)
    return project


class GenerateInnBody(BaseModel):
    existing_names: list[str] = []


@router.post("/{project_id}/workflow/generate-inn", response_model=NamingProject)
def run_inn_generation(
    project_id: UUID,
    body: GenerateInnBody = GenerateInnBody(),
) -> NamingProject:
    """Run INN name generation step."""
    project = _PROJECTS.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    step = WorkflowStep(step_name="name_generation", status=ProjectStatus.NAME_GENERATION,
                        started_at=datetime.now(timezone.utc))

    gen_engine = NameGenerationEngine(inn_reference_db=get_inn_reference_db())
    gen_request = NameGenerationRequest(
        properties=project.molecule.properties,
        matched_stems=project.stem_matches,
        existing_names_to_avoid=body.existing_names,
    )
    response = gen_engine.generate(gen_request)
    project.inn_candidates = response.candidates
    project.status = ProjectStatus.POCA_SCREENING

    step.completed_at = datetime.now(timezone.utc)
    step.result_summary = {"candidates_count": len(response.candidates)}
    step.decision = Decision.APPROVED if response.candidates else Decision.REJECTED
    project.workflow.append(step)
    project.updated_at = datetime.now(timezone.utc)
    return project


@router.post("/{project_id}/workflow/poca-screen", response_model=NamingProject)
def run_poca_screening(
    project_id: UUID,
    reference_names: list[str] | None = None,
) -> NamingProject:
    """Run POCA screening step."""
    project = _PROJECTS.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    step = WorkflowStep(step_name="poca_screening", status=ProjectStatus.POCA_SCREENING,
                        started_at=datetime.now(timezone.utc))

    known_stems = [s.stem for s in _get_default_provider().get_all_stems()]

    poca_engine = POCAScoringEngine(
        known_stems=known_stems,
        inn_reference_db=get_inn_reference_db(),
    )

    if reference_names:
        refs = reference_names
    else:
        first_candidate = project.inn_candidates[0].name if project.inn_candidates else ""
        refs = poca_engine.smart_references(first_candidate, max_refs=30)
        if not refs:
            refs = ["imatinib", "erlotinib", "gefitinib", "osimertinib",
                    "dasatinib", "nilotinib", "sorafenib", "sunitinib",
                    "ibrutinib", "acalabrutinib"]

    poca_results = []
    for candidate in project.inn_candidates[:10]:
        poca_request = POCARequest(
            proposed_name=candidate.name,
            reference_names=refs,
        )
        response = poca_engine.score_batch(poca_request)
        poca_results.extend(response.results)

    project.poca_results = poca_results
    project.status = ProjectStatus.CHINESE_NAMING

    pass_count = sum(1 for r in poca_results if r.alert_level == "PASS")
    review_count = sum(1 for r in poca_results if r.alert_level == "REVIEW")
    reject_count = sum(1 for r in poca_results if r.alert_level == "REJECT")

    step.completed_at = datetime.now(timezone.utc)
    step.result_summary = {"pass": pass_count, "review": review_count, "reject": reject_count}
    step.decision = Decision.APPROVED if reject_count == 0 else Decision.NEEDS_REVISION
    project.workflow.append(step)
    project.updated_at = datetime.now(timezone.utc)
    return project


@router.post("/{project_id}/workflow/chinese-naming", response_model=NamingProject)
def run_chinese_naming(
    project_id: UUID,
    target_meaning: str | None = None,
) -> NamingProject:
    """Run Chinese name generation step."""
    project = _PROJECTS.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    step = WorkflowStep(step_name="chinese_naming", status=ProjectStatus.CHINESE_NAMING,
                        started_at=datetime.now(timezone.utc))

    top_inn = project.inn_candidates[0].name if project.inn_candidates else ""
    engine = ChineseNameEngine(approved_names_db=[
        {"chinese_name": "伊马替尼"}, {"chinese_name": "厄洛替尼"},
        {"chinese_name": "吉非替尼"}, {"chinese_name": "阿达木单抗"},
    ])
    chinese_request = ChineseNameRequest(
        inn_name=top_inn,
        pharmacological_properties={
            "target_class": project.molecule.properties.target_class.value,
            "mechanism": project.molecule.properties.mechanism.value,
            "chemical_class": project.molecule.properties.chemical_class.value,
            "indication": project.molecule.properties.indication,
        },
        target_meaning=target_meaning,
        max_candidates=10,
    )
    response = engine.suggest(chinese_request)
    project.chinese_candidates = response.candidates
    project.status = ProjectStatus.BRAND_SCREENING

    step.completed_at = datetime.now(timezone.utc)
    step.result_summary = {"candidates_count": len(response.candidates)}
    step.decision = Decision.APPROVED if response.candidates else Decision.REJECTED
    project.workflow.append(step)
    project.updated_at = datetime.now(timezone.utc)
    return project


@router.post("/{project_id}/workflow/brand-screening", response_model=NamingProject)
def run_brand_screening(
    project_id: UUID,
    proposed_brands: list[str] | None = None,
) -> NamingProject:
    """Run brand name screening step."""
    project = _PROJECTS.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    step = WorkflowStep(step_name="brand_screening", status=ProjectStatus.BRAND_SCREENING,
                        started_at=datetime.now(timezone.utc))

    top_inn = project.inn_candidates[0].name if project.inn_candidates else ""
    brands = proposed_brands or [f"Zel{top_inn[:4]}", f"Nova{top_inn[:3]}", f"Via{top_inn[:4]}"]

    engine = BrandNameEngine()
    screen_request = BrandScreenRequest(
        proposed_brand_names=brands,
        inn_name=top_inn,
    )
    response = engine.screen(screen_request)
    project.brand_candidates = response.results
    project.status = ProjectStatus.DECISION_PENDING

    step.completed_at = datetime.now(timezone.utc)
    step.result_summary = {"candidates_count": len(response.results)}
    step.decision = Decision.APPROVED if response.results else Decision.REJECTED
    project.workflow.append(step)
    project.updated_at = datetime.now(timezone.utc)
    return project


class DecisionBody(BaseModel):
    decision: Decision
    notes: str | None = None
    final_selection: dict | None = None


@router.post("/{project_id}/workflow/decide", response_model=NamingProject)
def make_decision(project_id: UUID, body: DecisionBody) -> NamingProject:
    """Make a final decision on the naming project."""
    project = _PROJECTS.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    step = WorkflowStep(step_name="decision", status=ProjectStatus.DECISION_PENDING,
                        started_at=datetime.now(timezone.utc),
                        completed_at=datetime.now(timezone.utc),
                        decision=body.decision, decision_notes=body.notes)
    project.workflow.append(step)
    project.final_selection = body.final_selection
    project.status = ProjectStatus.COMPLETED if body.decision == Decision.APPROVED else ProjectStatus.REJECTED
    project.updated_at = datetime.now(timezone.utc)
    return project
