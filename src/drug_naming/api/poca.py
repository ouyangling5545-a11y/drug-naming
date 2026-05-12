from __future__ import annotations
from pydantic import BaseModel, Field
from fastapi import APIRouter, Request
from ..models.poca import POCARequest, POCAResponse, POCAWeights, POCAScoreDetail, POCAScoreDetail
from ..models.chinese import ChineseNameCandidate, ChineseNameRequest
from ..engines.poca_scorer import POCAScoringEngine
from ..engines.chinese_name import ChineseNameEngine
from ..data.inn_reference import get_inn_reference_db
from .stems import _get_default_provider


class NameEvaluationResponse(BaseModel):
    proposed_name: str
    poca_score: float  # worst (highest) FDA 2D score
    poca_assessment: str  # PASS / REVIEW / REJECT
    phonetic_score: float
    orthographic_score: float
    compositional_score: float
    worst_comparison: str
    poca_detail: POCAScoreDetail | None = None
    chinese_suggestions: list[ChineseNameCandidate] = Field(default_factory=list)
    similar_names: list[POCAScoreDetail] = Field(default_factory=list)
    similar_count: int = 0
    threshold: float = 0.55
    verdict: str
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

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


@router.post("/evaluate", response_model=NameEvaluationResponse)
def evaluate_name(
    proposed_name: str,
    threshold: float = 0.55,
    max_similar: int = 100,
    request: Request = None,
) -> NameEvaluationResponse:
    """One-stop name evaluation with FDA-style 2D POCA scoring.

    Scores the proposed name against the entire INN reference database
    using Phonetic + Orthographic dimensions only (FDA POCA methodology).
    Returns all names scoring at or above the threshold (default 55%), capped at max_similar.
    """
    engine = _get_poca_engine(request)
    inn_db = get_inn_reference_db()
    name_clean = proposed_name.strip()
    name_lower = name_clean.lower()

    # 1. Get all INN reference names and run FDA 2D scoring with threshold
    all_refs = sorted(inn_db.english_names) if inn_db else []
    similar_names = engine.score_batch_fda(name_clean, all_refs, threshold=threshold / 100.0, max_results=max_similar)

    # 2. Determine worst comparison and scores
    worst_detail = similar_names[0] if similar_names else None
    worst_score = worst_detail.overall_poca_score if worst_detail else 0.0
    worst_comparison = worst_detail.reference_name if worst_detail else ""
    phonetic_score = worst_detail.phonetic_score if worst_detail else 0.0
    orthographic_score = worst_detail.orthographic_score if worst_detail else 0.0
    compositional_score = worst_detail.compositional_score if worst_detail else 0.0

    # 3. Chinese name suggestions
    chinese_engine = ChineseNameEngine(approved_names_db=[])
    chinese_request = ChineseNameRequest(
        inn_name=name_clean,
        pharmacological_properties={},
        max_candidates=4,
    )
    try:
        chinese_response = chinese_engine.suggest(chinese_request)
        chinese_suggestions = chinese_response.candidates[:4]
    except Exception:
        chinese_suggestions = []

    # 4. Build verdict and reasons
    reasons: list[str] = []
    risks: list[str] = []

    if not similar_names:
        reasons.append(f"在 INN 数据库中未找到与 '{name_clean}' POCA 得分超过 {threshold:.0f}% 的相似名称")
        reasons.append("该名称具有良好的独特性")
    elif worst_score < 0.70:
        reasons.append(
            f"最接近的 INN 名称 '{worst_comparison}' 的 POCA 综合得分 {worst_score*100:.0f}%，"
            f"低于 70% 安全阈值，混淆风险低"
        )
    elif worst_score < 0.85:
        risks.append(
            f"与 '{worst_comparison}' 的 POCA 得分 {worst_score*100:.0f}%，"
            f"处于 70%-85% 审核区间，建议人工复核"
        )
    else:
        risks.append(
            f"与 '{worst_comparison}' 的 POCA 得分 {worst_score*100:.0f}%，"
            f"超过 85% 拒绝阈值，存在较高混淆风险"
        )

    # Trigram screening
    trigram_pass = True
    if inn_db:
        from ..engines.name_generator import NameGenerationEngine
        trigram_pass = NameGenerationEngine._passes_trigram_screen(name_clean, inn_db.english_names)
    if not trigram_pass:
        risks.append("该名称与已有 INN 名称的三字母组合高度重叠（>80%），存在混淆风险")
    else:
        reasons.append("三字母组合筛查通过，未与已有 INN 名称发生显著重叠")

    # Length check
    n_len = len(name_clean)
    if 4 <= n_len <= 20:
        reasons.append(f"名称长度 {n_len} 个字符，符合 WHO 命名规范（4-20 字符）")
    elif n_len < 4:
        risks.append(f"名称仅 {n_len} 个字符，过短，建议至少 4 个字符")
    else:
        risks.append(f"名称 {n_len} 个字符，超过 20 字符上限")

    # Exact INN conflict
    if inn_db and inn_db.exists(name_clean):
        risks.append("该名称与已有 INN 名称完全相同，不可使用")

    # Phonological quality
    if worst_detail:
        if worst_detail.phonetic_score < 0.30:
            reasons.append(f"语音相似度仅 {worst_detail.phonetic_score*100:.0f}%，发音差异明显，安全性高")
        if worst_detail.orthographic_score < 0.30:
            reasons.append(f"字形相似度仅 {worst_detail.orthographic_score*100:.0f}%，拼写差异明显")
        reasons.append(f"共发现 {len(similar_names)} 个超过阈值 {threshold:.0f}% 的相似 INN 名称")

    # Determine assessment
    if worst_score >= 0.85:
        assessment = "REJECT"
    elif worst_score >= 0.70:
        assessment = "REVIEW"
    else:
        assessment = "PASS"

    if assessment == "PASS":
        verdict = f"该名称通过 FDA POCA 筛查（阈值 {threshold:.0f}%），综合最高得分 {worst_score*100:.0f}%，无明显混淆风险"
    elif assessment == "REVIEW":
        verdict = f"该名称存在一定风险（最高得分 {worst_score*100:.0f}%），建议人工复核后决定"
    else:
        verdict = f"该名称 POCA 得分过高（最高 {worst_score*100:.0f}%），存在较高混淆风险，不建议使用"

    return NameEvaluationResponse(
        proposed_name=name_clean,
        poca_score=worst_score,
        poca_assessment=assessment,
        phonetic_score=phonetic_score,
        orthographic_score=orthographic_score,
        compositional_score=compositional_score,
        worst_comparison=worst_comparison,
        poca_detail=worst_detail,
        chinese_suggestions=chinese_suggestions,
        similar_names=similar_names[:max_similar],
        similar_count=len(similar_names),
        threshold=threshold / 100.0,
        verdict=verdict,
        reasons=reasons,
        risks=risks,
    )
