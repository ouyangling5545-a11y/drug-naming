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
    worst_comparison: str = Field(default="", description="Closest-matching INN reference name")
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
        max_candidates_per_stem=max(body.top_k * 10, 500),
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

    # 5. Build POCA engine + trigram index over FULL INN reference database
    all_stems = [s.stem for s in provider.get_all_stems()]
    inn_db = get_inn_reference_db()
    poca_engine = POCAScoringEngine(
        known_stems=all_stems,
        inn_reference_db=inn_db,
    )

    all_inn_refs_list = sorted(inn_db.english_names) if inn_db else []
    trigram_index: dict[str, set[str]] = {}
    prefix_index: dict[str, set[str]] = {}  # 2-4 char prefix → matching INN refs
    for ref in all_inn_refs_list:
        rl = ref.lower()
        for i in range(len(rl) - 2):
            t = rl[i:i + 3]
            trigram_index.setdefault(t, set()).add(ref)
        for plen in (2, 3, 4):
            if len(rl) >= plen:
                p = rl[:plen]
                prefix_index.setdefault(p, set()).add(ref)

    # 6. Chinese transliteration prep: suffix stem detection
    suffix_cn = stem_obj.chinese.lstrip("-").strip() if stem_obj.chinese else ""
    suffix_core = stem_obj.stem.strip("-").lower()

    # 7. Score each candidate against the FULL INN DB with smart references,
    #    trigram overlap, and prefix matching (1000 ref cap). Score all refs
    #    for accurate worst-score, then apply stop-strategy filter: if ≥3 refs
    #    exceed threshold OR any ref ≥80%, the candidate is too similar.
    smart_base = poca_engine.smart_references(suffix_core + "ib", max_refs=500)
    if not smart_base:
        smart_base = ["imatinib", "erlotinib", "gefitinib", "osimertinib",
                      "dasatinib", "nilotinib", "sorafenib", "sunitinib",
                      "ibrutinib", "acalabrutinib"]

    poca_threshold_ratio = body.poca_threshold / 100.0
    stop_strategy_filtered = 0
    poca_scored = 0
    MAX_REFS_PER_CANDIDATE = 1000
    results: list[RecommendCandidate] = []

    for c in gen_response.candidates:
        name_lower = c.name.lower()

        # Collect trigram-matched refs, ranked by overlap count
        overlap: dict[str, int] = {}  # lower_name → overlap count
        for i in range(len(name_lower) - 2):
            t = name_lower[i:i + 3]
            for ref in trigram_index.get(t, ()):
                rl = ref.lower()
                if rl != name_lower:
                    overlap[rl] = overlap.get(rl, 0) + 1

        # Collect prefix-matched refs (same 2-4 char prefix with INN names)
        prefix_overlap: dict[str, int] = {}
        for plen in (2, 3, 4):
            if len(name_lower) >= plen:
                pfx = name_lower[:plen]
                for ref in prefix_index.get(pfx, ()):
                    rl = ref.lower()
                    if rl != name_lower:
                        prefix_overlap[rl] = prefix_overlap.get(rl, 0) + 1

        # Build ref list: smart_base → trigram overlap → prefix match
        refs_to_check: list[str] = []
        added: set[str] = set()
        for ref in smart_base:
            rl = ref.lower()
            if rl != name_lower and rl not in added:
                refs_to_check.append(ref)
                added.add(rl)

        for rl in sorted(overlap, key=overlap.get, reverse=True):
            if len(refs_to_check) >= MAX_REFS_PER_CANDIDATE:
                break
            if rl not in added:
                refs_to_check.append(rl)
                added.add(rl)

        for rl in sorted(prefix_overlap, key=prefix_overlap.get, reverse=True):
            if len(refs_to_check) >= MAX_REFS_PER_CANDIDATE:
                break
            if rl not in added:
                refs_to_check.append(rl)
                added.add(rl)

        if not refs_to_check:
            results.append(RecommendCandidate(
                name=c.name, prefix=c.prefix, infix=c.infix, suffix=c.suffix,
                phonological_score=round(c.phonological_score, 3),
                combined_score=0, phonetic_score=0, orthographic_score=0,
                worst_comparison="",
                chinese_transliterations=[],
                poca_assessment="PASS",
            ))
            continue

        # Score against all selected refs to find the true worst pair.
        # Also track stop-strategy counters: if ≥3 refs exceed threshold
        # OR any ref ≥80%, the candidate is too similar to existing INN names.
        worst_score = 0.0
        worst_phonetic = 0.0
        worst_ortho = 0.0
        worst_comp = ""
        over_threshold_count = 0
        found_80pct = False
        poca_scored += 1
        for ref in refs_to_check:
            detail = poca_engine.score_pair(c.name, ref, mode="fda")
            if detail.overall_poca_score > worst_score:
                worst_score = detail.overall_poca_score
                worst_phonetic = detail.phonetic_score
                worst_ortho = detail.orthographic_score
                worst_comp = ref

            if detail.overall_poca_score >= poca_threshold_ratio:
                over_threshold_count += 1
            if detail.overall_poca_score >= 0.80:
                found_80pct = True

        # Filter candidates matching the stop strategy (too similar to existing INN)
        if over_threshold_count >= 3 or found_80pct:
            stop_strategy_filtered += 1
            continue

        combined = round(worst_score * 100)

        # Chinese transliteration: transliterate prefix + known suffix Chinese
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
            worst_comparison=worst_comp,
            chinese_transliterations=cn_variants,
            poca_assessment=assessment,
        ))

    # Sort: phonological quality first (higher = more euphonious),
    # then lower POCA as tiebreaker.  Then group by score tier and
    # interleave tiers so that 2/3/4-letter prefixes all appear.
    # Within each tier, prefix families are spread out (no clustering).
    results.sort(key=lambda r: (-r.phonological_score, r.combined_score))

    tiers: dict[float, list[RecommendCandidate]] = {}
    for c in results:
        tier = round(c.phonological_score, 2)
        tiers.setdefault(tier, []).append(c)

    for tier in tiers:
        seen: set[str] = set()
        d: list[RecommendCandidate] = []
        r: list[RecommendCandidate] = []
        for c in tiers[tier]:
            pfx_family = (c.prefix or "")[:2].lower()
            if pfx_family not in seen:
                d.append(c)
                seen.add(pfx_family)
            else:
                r.append(c)
        tiers[tier] = d + r

    results = []
    tier_keys = sorted(tiers.keys(), reverse=True)
    max_tier = max(len(tiers[t]) for t in tier_keys)
    for i in range(max_tier):
        for t in tier_keys:
            if i < len(tiers[t]):
                results.append(tiers[t][i])

    return RecommendResponse(
        stem=stem_obj.stem,
        stem_chinese=stem_obj.chinese or "",
        stem_meaning=stem_obj.meaning or "",
        candidates=results,
        total=len(results),
        stats={
            "total_generated": gen_response.total_generated,
            "filtered_by_generation": gen_response.filtered_out,
            "filtered_by_poca_threshold": stop_strategy_filtered,
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
