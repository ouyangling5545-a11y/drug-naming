from __future__ import annotations
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException
from ..models.molecule import PharmacologicalProperties
from ..models.naming import (
    NameCandidate,
    NameGenerationConstraints,
    NameGenerationRequest,
    NameGenerationResponse,
)
from ..engines.stem_matcher import StemMatchingEngine
from ..engines.name_generator import NameGenerationEngine
from ..engines.poca_scorer import POCAScoringEngine
from ..data.inn_reference import get_inn_reference_db
from ..data.targets import get_target_tree, find_target, flatten_targets
from .stems import _get_default_provider
from .poca import _transliterate_prefix_variants

router = APIRouter()


class GenerateNamesRequest(BaseModel):
    properties: PharmacologicalProperties
    smiles: str | None = None
    stem_override: str | None = None
    existing_names_to_avoid: list[str] = []
    constraints: NameGenerationConstraints = NameGenerationConstraints()


class RecommendRequest(BaseModel):
    stem: str = Field(description="Core stem text, e.g. 'tinib', '-tinib'")
    properties: PharmacologicalProperties = Field(default_factory=PharmacologicalProperties)
    smiles: str | None = None
    top_k: int = Field(default=100, ge=10, le=200)


class RecommendCandidate(BaseModel):
    name: str
    prefix: str | None
    infix: str | None
    suffix: str | None
    phonological_score: float
    combined_score: float = Field(description="POCA 2D worst score, 0-100")
    phonetic_score: float
    orthographic_score: float
    chinese_transliterations: list[str] = Field(description="3 Chinese transliteration variants")
    poca_assessment: str = Field(description="PASS / REVIEW / REJECT")


class RecommendResponse(BaseModel):
    stem: str
    stem_chinese: str
    stem_meaning: str
    candidates: list[RecommendCandidate]
    total: int


@router.post("/generate", response_model=NameGenerationResponse)
def generate_names(body: GenerateNamesRequest) -> NameGenerationResponse:
    """Generate INN name candidates from pharmacological properties.

    If stem_override is provided, the specified stem is inserted as a
    high-priority match before running normal property-based matching.
    """
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

    if body.stem_override:
        from ..models.stem import StemMatch
        override_key = body.stem_override.strip("-").lower()
        for s in provider.get_all_stems():
            if s.stem.strip("-").lower() == override_key:
                override = StemMatch(
                    stem=s, match_score=1.0,
                    match_reasons=["user_override"],
                    relevance_weight=1.0,
                )
                matched_stems.insert(0, override)
                break

    gen_engine = NameGenerationEngine(inn_reference_db=get_inn_reference_db())
    gen_request = NameGenerationRequest(
        properties=body.properties,
        matched_stems=matched_stems,
        constraints=body.constraints,
        existing_names_to_avoid=body.existing_names_to_avoid,
    )
    return gen_engine.generate(gen_request)


@router.post("/recommend", response_model=RecommendResponse)
def recommend_names(body: RecommendRequest) -> RecommendResponse:
    """Generate 100 scored name candidates for a single user-selected stem.

    Uses relaxed generation (no trigram/existing-name filtering), POCA 2D
    scoring against smart INN references, and Chinese prefix transliteration
    with 3 character variants.
    """
    provider = _get_default_provider()

    # 1. Look up the stem
    override_key = body.stem.strip("-").lower()
    stem_obj = None
    for s in provider.get_all_stems():
        if s.stem.strip("-").lower() == override_key:
            stem_obj = s
            break

    if stem_obj is None:
        raise HTTPException(status_code=404, detail=f"Stem '{body.stem}' not found")

    # 2. Parse SMILES for structural features if provided
    if body.smiles:
        from ..engines.structure_parser import StructureParser
        try:
            parser = StructureParser()
            sf = parser.parse(body.smiles)
            if sf.scaffold_type and not body.properties.chemical_scaffold:
                body.properties.chemical_scaffold = sf.scaffold_type
        except Exception:
            pass

    # 3. Build a single-stem match
    from ..models.stem import StemMatch
    stem_match = StemMatch(
        stem=stem_obj,
        match_score=1.0,
        match_reasons=["user_selected"],
        relevance_weight=1.0,
    )

    # 4. Generate candidates with relaxed mode (skip trigram/INN-conflict filters)
    constraints = NameGenerationConstraints(
        max_candidates_per_stem=body.top_k,
        max_name_length=20,
        min_name_length=5,
    )

    gen_engine = NameGenerationEngine(inn_reference_db=get_inn_reference_db())
    gen_request = NameGenerationRequest(
        properties=body.properties,
        matched_stems=[stem_match],
        constraints=constraints,
        relaxed=True,
    )
    gen_response = gen_engine.generate(gen_request)

    # 5. Build POCA engine and select smart references once
    all_stems = [s.stem for s in provider.get_all_stems()]
    poca_engine = POCAScoringEngine(
        known_stems=all_stems,
        inn_reference_db=get_inn_reference_db(),
    )

    stem_core = stem_obj.stem.strip("-")
    refs = poca_engine.smart_references(stem_core + "ib", max_refs=12)
    if not refs:
        refs = ["imatinib", "erlotinib", "gefitinib", "osimertinib",
                "dasatinib", "nilotinib", "sorafenib", "sunitinib",
                "ibrutinib", "acalabrutinib"]

    # 6. Chinese transliteration prep: suffix stem detection
    suffix_cn = stem_obj.chinese.lstrip("-").strip() if stem_obj.chinese else ""
    suffix_core = stem_obj.stem.strip("-").lower()

    # 7. Score each candidate and generate Chinese transliterations
    results: list[RecommendCandidate] = []
    for c in gen_response.candidates:
        # POCA batch scoring against smart references
        worst_score = 0.0
        worst_phonetic = 0.0
        worst_ortho = 0.0
        for ref in refs:
            detail = poca_engine.score_pair(c.name, ref, mode="fda")
            if detail.overall_poca_score > worst_score:
                worst_score = detail.overall_poca_score
                worst_phonetic = detail.phonetic_score
                worst_ortho = detail.orthographic_score

        # Chinese transliteration: transliterate prefix + known suffix Chinese
        name_lower = c.name.lower()
        pfx = c.prefix or ""
        if suffix_cn and name_lower.endswith(suffix_core):
            pfx_variants = _transliterate_prefix_variants(pfx, n=3)
            cn_variants = [v + suffix_cn for v in pfx_variants]
        else:
            from ..engines.chinese_transliteration import transliterate_to_chinese
            cn = transliterate_to_chinese(c.name)
            cn_variants = [cn] * 3

        # Assessment threshold
        if worst_score >= 0.85:
            assessment = "REJECT"
        elif worst_score >= 0.70:
            assessment = "REVIEW"
        else:
            assessment = "PASS"

        results.append(RecommendCandidate(
            name=c.name,
            prefix=c.prefix,
            infix=c.infix,
            suffix=c.suffix,
            phonological_score=round(c.phonological_score, 3),
            combined_score=round(worst_score * 100),
            phonetic_score=round(worst_phonetic * 100),
            orthographic_score=round(worst_ortho * 100),
            chinese_transliterations=cn_variants,
            poca_assessment=assessment,
        ))

    # Sort: best (lowest POCA) first, break ties with phonological quality
    results.sort(key=lambda r: (r.combined_score, -r.phonological_score))

    return RecommendResponse(
        stem=stem_obj.stem,
        stem_chinese=stem_obj.chinese or "",
        stem_meaning=stem_obj.meaning or "",
        candidates=results,
        total=len(results),
    )


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
