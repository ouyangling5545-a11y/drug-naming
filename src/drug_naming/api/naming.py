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
from .stems import _get_default_provider

router = APIRouter()


class GenerateNamesRequest(BaseModel):
    properties: PharmacologicalProperties
    existing_names_to_avoid: list[str] = []
    constraints: NameGenerationConstraints = NameGenerationConstraints()


@router.post("/generate", response_model=NameGenerationResponse)
def generate_names(body: GenerateNamesRequest) -> NameGenerationResponse:
    """Generate INN name candidates from pharmacological properties."""
    provider = _get_default_provider()
    stem_engine = StemMatchingEngine(provider)
    matched_stems = stem_engine.match(body.properties, top_k=5)

    gen_engine = NameGenerationEngine(inn_reference_db=get_inn_reference_db())
    gen_request = NameGenerationRequest(
        properties=body.properties,
        matched_stems=matched_stems,
        constraints=body.constraints,
        existing_names_to_avoid=body.existing_names_to_avoid,
    )
    return gen_engine.generate(gen_request)
