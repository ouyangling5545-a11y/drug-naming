from __future__ import annotations
from pydantic import BaseModel
from fastapi import APIRouter
from ..models.molecule import PharmacologicalProperties
from ..models.naming import (
    NameCandidate,
    NameGenerationConstraints,
    NameGenerationRequest,
    NameGenerationResponse,
)
from ..engines.stem_matcher import StemMatchingEngine
from ..engines.name_generator import NameGenerationEngine
from ..data.inn_reference import get_inn_reference_db
from ..data.targets import get_target_tree, find_target, flatten_targets
from .stems import _get_default_provider

router = APIRouter()


class GenerateNamesRequest(BaseModel):
    properties: PharmacologicalProperties
    smiles: str | None = None
    existing_names_to_avoid: list[str] = []
    constraints: NameGenerationConstraints = NameGenerationConstraints()


@router.post("/generate", response_model=NameGenerationResponse)
def generate_names(body: GenerateNamesRequest) -> NameGenerationResponse:
    """Generate INN name candidates from pharmacological properties."""
    provider = _get_default_provider()
    stem_engine = StemMatchingEngine(provider)

    structure_features = None
    if body.smiles:
        from ..engines.structure_parser import StructureParser
        try:
            parser = StructureParser()
            structure_features = parser.parse(body.smiles)
            if structure_features.scaffold_type and not body.properties.chemical_scaffold:
                body.properties.chemical_scaffold = structure_features.scaffold_type
        except Exception:
            pass

    matched_stems = stem_engine.match(
        body.properties, top_k=5, structure_features=structure_features,
    )

    gen_engine = NameGenerationEngine(inn_reference_db=get_inn_reference_db())
    gen_request = NameGenerationRequest(
        properties=body.properties,
        matched_stems=matched_stems,
        constraints=body.constraints,
        existing_names_to_avoid=body.existing_names_to_avoid,
    )
    return gen_engine.generate(gen_request)


@router.get("/targets")
def get_targets() -> list[dict]:
    """Return the hierarchical target tree for the frontend dropdown."""
    return get_target_tree()


@router.get("/targets/{target_value}")
def get_target_info(target_value: str) -> dict | None:
    """Return metadata for a specific target (for auto-fill)."""
    t = find_target(target_value)
    if t:
        return t.to_dict()
    return None
