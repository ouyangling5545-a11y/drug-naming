from __future__ import annotations
from fastapi import APIRouter, Request
from ..models.poca import POCARequest, POCAResponse, POCAWeights, POCAScoreDetail
from ..engines.poca_scorer import POCAScoringEngine
from ..engines.stem_matcher import StemMatchingEngine
from ..data.inn_reference import get_inn_reference_db
from .stems import _get_default_provider

router = APIRouter()


def _get_poca_engine(request: Request | None = None) -> POCAScoringEngine:
    """Build POCA engine with known stems and INN reference database."""
    known_stems: list[str] = []
    if request:
        registry = getattr(request.app.state, "data_registry", None)
        if registry:
            provider = registry.get("stems")
            if provider:
                known_stems = [s.stem for s in provider.get_all_stems()]
    if not known_stems:
        provider = _get_default_provider()
        known_stems = [s.stem for s in provider.get_all_stems()]
    return POCAScoringEngine(
        known_stems=known_stems,
        inn_reference_db=get_inn_reference_db(),
    )


@router.post("/score", response_model=POCAResponse)
def score_poca(request_body: POCARequest, request: Request = None) -> POCAResponse:
    """Score a proposed name against a list of reference names using full POCA methodology."""
    engine = _get_poca_engine(request)
    return engine.score_batch(request_body)


@router.post("/compare", response_model=POCAScoreDetail)
def compare_poca(
    proposed_name: str,
    reference_name: str,
    phonetic_weight: float = 0.40,
    orthographic_weight: float = 0.35,
    compositional_weight: float = 0.25,
    request: Request = None,
) -> POCAScoreDetail:
    """Compare two specific names with full POCA breakdown."""
    weights = POCAWeights(
        phonetic_weight=phonetic_weight,
        orthographic_weight=orthographic_weight,
        compositional_weight=compositional_weight,
    )
    engine = _get_poca_engine(request)
    engine.weights = weights
    return engine.score_pair(proposed_name, reference_name)


@router.post("/smart-references", response_model=list[str])
def smart_references(proposed_name: str, max_refs: int = 30, request: Request = None) -> list[str]:
    """Get the most relevant INN reference names for POCA comparison by stem matching."""
    engine = _get_poca_engine(request)
    return engine.smart_references(proposed_name, max_refs)


@router.post("/smart-score", response_model=POCAResponse)
def smart_score_poca(
    proposed_name: str,
    max_refs: int = 30,
    request: Request = None,
) -> POCAResponse:
    """Score a proposed name using smart-selected references from the INN database."""
    engine = _get_poca_engine(request)
    refs = engine.smart_references(proposed_name, max_refs)
    if not refs:
        refs = ["imatinib", "erlotinib", "gefitinib", "osimertinib",
                "dasatinib", "nilotinib", "sorafenib", "sunitinib",
                "ibrutinib", "acalabrutinib"]
    poca_request = POCARequest(proposed_name=proposed_name, reference_names=refs)
    return engine.score_batch(poca_request)
