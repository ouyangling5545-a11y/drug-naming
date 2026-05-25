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
    poca_threshold: float = Field(default=85, ge=50, le=100, description="Max POCA combined score; candidates above this are filtered out")
    dedup_strict: bool = Field(default=True, description="If True, also apply trigram deduplication (75% threshold)")
    prefix_lengths: list[int] = Field(default_factory=lambda: [2, 3, 4, 5, 6], description="Allowed prefix letter counts")
    chinese_prefix_hint: str | None = Field(default=None, description="Desired Chinese prefix character(s); system reverse-maps to Latin prefixes")


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
    stats: dict = Field(default_factory=dict, description="Filtering statistics from generation pipeline")


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

    # 4. Build prefix blacklist from target root (avoid prefixes identical to target)
    target_root_blacklist: list[str] = []
    if body.properties.target_class:
        tc_val = getattr(body.properties.target_class, 'value', body.properties.target_class)
        tc_lower = tc_val.lower()
        target_root_blacklist.append(tc_lower)
        if len(tc_lower) >= 4:
            target_root_blacklist.append(tc_lower[:4])
        if len(tc_lower) >= 3:
            target_root_blacklist.append(tc_lower[:3])

    # Chinese prefix hint → reverse-map to Latin prefixes
    prefix_whitelist: list[str] | None = None
    prefix_lengths = body.prefix_lengths
    if body.chinese_prefix_hint:
        from ..engines.chinese_transliteration import latin_prefixes_for_chinese
        matched = latin_prefixes_for_chinese(body.chinese_prefix_hint.strip())
        if matched:
            prefix_whitelist = matched
            # Allow all matched prefix lengths
            matched_lengths = set(len(p) for p in matched)
            prefix_lengths = sorted(matched_lengths)

    constraints = NameGenerationConstraints(
        max_candidates_per_stem=body.top_k,
        max_name_length=20,
        min_name_length=5,
        prefix_blacklist=target_root_blacklist,
        prefix_lengths=prefix_lengths,
        prefix_whitelist=prefix_whitelist,
    )

    gen_engine = NameGenerationEngine(inn_reference_db=get_inn_reference_db())
    gen_request = NameGenerationRequest(
        properties=body.properties,
        matched_stems=[stem_match],
        constraints=constraints,
        relaxed=not body.dedup_strict,
    )
    gen_response = gen_engine.generate(gen_request)

    # 5. Build POCA engine with trigram-indexed full INN reference list
    all_stems = [s.stem for s in provider.get_all_stems()]
    inn_db = get_inn_reference_db()
    poca_engine = POCAScoringEngine(
        known_stems=all_stems,
        inn_reference_db=inn_db,
    )

    stem_core = stem_obj.stem.strip("-")
    smart_refs = poca_engine.smart_references(stem_core + "ib", max_refs=30)
    if not smart_refs:
        smart_refs = ["imatinib", "erlotinib", "gefitinib", "osimertinib",
                      "dasatinib", "nilotinib", "sorafenib", "sunitinib",
                      "ibrutinib", "acalabrutinib"]

    # Build trigram index over all INN refs for fast cross-stem lookup
    all_inn_refs_list = sorted(inn_db.english_names) if inn_db else []
    trigram_index: dict[str, list[str]] = {}
    for ref in all_inn_refs_list:
        for i in range(len(ref) - 2):
            t = ref[i:i + 3].lower()
            trigram_index.setdefault(t, []).append(ref)

    # 6. Chinese transliteration prep: suffix stem detection
    suffix_cn = stem_obj.chinese.lstrip("-").strip() if stem_obj.chinese else ""
    suffix_core = stem_obj.stem.strip("-").lower()

    # 7. Score each candidate: smart refs + trigram-matching refs, early stop at 3 over threshold
    poca_threshold_ratio = body.poca_threshold / 100.0
    poca_filtered = 0
    results: list[RecommendCandidate] = []
    for c in gen_response.candidates:
        worst_score = 0.0
        worst_phonetic = 0.0
        worst_ortho = 0.0
        over_threshold_count = 0

        # Collect trigram-matching refs for this candidate
        name_lower = c.name.lower()
        seen_refs = set(smart_refs)
        refs_to_check = list(smart_refs)
        for i in range(len(name_lower) - 2):
            t = name_lower[i:i + 3]
            for ref in trigram_index.get(t, []):
                if ref not in seen_refs:
                    seen_refs.add(ref)
                    refs_to_check.append(ref)

        for ref in refs_to_check:
            detail = poca_engine.score_pair(c.name, ref, mode="fda")
            if detail.overall_poca_score > worst_score:
                worst_score = detail.overall_poca_score
                worst_phonetic = detail.phonetic_score
                worst_ortho = detail.orthographic_score
            if detail.overall_poca_score >= poca_threshold_ratio:
                over_threshold_count += 1
                if over_threshold_count >= 3:
                    break  # early stop: 3 references above threshold → reject candidate

        if over_threshold_count >= 3:
            poca_filtered += 1
            continue

        combined = round(worst_score * 100)

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
            combined_score=combined,
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
        stats={
            "total_generated": gen_response.total_generated,
            "filtered_by_generation": gen_response.filtered_out,
            "filtered_by_poca_threshold": poca_filtered,
            "flag_counts": gen_response.flag_counts,
        },
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


class ChinesePrefixHintRequest(BaseModel):
    q: str = ""


@router.post("/chinese-prefix-hint")
def chinese_prefix_hint(body: ChinesePrefixHintRequest) -> dict:
    """Return Latin prefix candidates whose Chinese transliteration matches query char(s)."""
    q = body.q.strip()
    if not q:
        return {"hint": "", "prefixes": [], "lengths": []}
    from ..engines.chinese_transliteration import latin_prefixes_for_chinese
    prefixes = latin_prefixes_for_chinese(q)
    lengths = sorted(set(len(p) for p in prefixes)) if prefixes else []
    return {"hint": q, "prefixes": prefixes, "lengths": lengths}
