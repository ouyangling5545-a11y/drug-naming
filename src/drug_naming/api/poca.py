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
    poca_score: float
    poca_assessment: str  # PASS / REVIEW / REJECT
    phonetic_score: float
    orthographic_score: float
    compositional_score: float
    worst_comparison: str
    poca_detail: POCAScoreDetail | None = None
    chinese_suggestions: list[ChineseNameCandidate] = Field(default_factory=list)
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
def evaluate_name(proposed_name: str, request: Request = None) -> NameEvaluationResponse:
    """One-stop name evaluation: POCA scoring + Chinese name suggestions + verdict."""
    engine = _get_poca_engine(request)
    inn_db = get_inn_reference_db()
    name_lower = proposed_name.strip().lower()

    # 1. Smart POCA scoring
    refs = engine.smart_references(proposed_name, max_refs=15)
    if not refs:
        refs = ["imatinib", "erlotinib", "gefitinib", "osimertinib",
                "dasatinib", "nilotinib", "sorafenib", "sunitinib",
                "ibrutinib", "acalabrutinib"]
    poca_request = POCARequest(proposed_name=proposed_name, reference_names=refs)
    poca_response = engine.score_batch(poca_request)

    # 2. Best detail from worst comparison
    worst_detail = None
    for r in poca_response.results:
        if r.reference_name == poca_response.worst_comparison:
            worst_detail = r
            break

    # 3. Chinese name suggestions
    chinese_engine = ChineseNameEngine(approved_names_db=[])
    chinese_request = ChineseNameRequest(
        inn_name=proposed_name,
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

    if poca_response.worst_score < 0.70:
        reasons.append(
            f"与最接近的INN名称 '{poca_response.worst_comparison}' 的POCA综合得分 {poca_response.worst_score:.2f}，"
            f"低于 0.70 安全阈值，无混淆风险"
        )
    elif poca_response.worst_score < 0.85:
        risks.append(
            f"与 '{poca_response.worst_comparison}' 的POCA得分 {poca_response.worst_score:.2f}，"
            f"处于 0.70-0.85 审核区间，建议人工复核"
        )
    else:
        risks.append(
            f"与 '{poca_response.worst_comparison}' 的POCA得分 {poca_response.worst_score:.2f}，"
            f"超过 0.85 拒绝阈值，存在较高混淆风险"
        )

    # Trigram screening
    trigram_pass = engine._inn_db is not None and NameGenerationEngine._passes_trigram_screen(
        proposed_name, inn_db.english_names
    ) if inn_db else True
    if not trigram_pass:
        risks.append("该名称与已有INN名称的三字母组合高度重叠（>80%），存在混淆风险")
    else:
        reasons.append("三字母组合筛查通过，未与已有INN名称发生显著重叠")

    # Length check
    n_len = len(proposed_name)
    if 4 <= n_len <= 20:
        reasons.append(f"名称长度 {n_len} 个字符，符合WHO命名规范（4-20字符）")
    elif n_len < 4:
        risks.append(f"名称仅 {n_len} 个字符，过短，建议至少4个字符")
    else:
        risks.append(f"名称 {n_len} 个字符，超过20字符上限")

    # Exact INN conflict
    if inn_db and inn_db.exists(proposed_name):
        risks.append("该名称与已有INN名称完全相同，不可使用")

    # Phonological quality
    if worst_detail:
        if worst_detail.phonetic_score < 0.3:
            reasons.append(f"语音相似度仅 {worst_detail.phonetic_score:.2f}，发音差异明显，安全性高")
        if worst_detail.orthographic_score < 0.3:
            reasons.append(f"字形相似度仅 {worst_detail.orthographic_score:.2f}，拼写差异明显")

    if poca_response.overall_safety_assessment == "PASS":
        verdict = f"该名称通过POCA筛查，综合得分 {poca_response.worst_score:.2f}，无明显混淆风险，建议提交INN申请"
    elif poca_response.overall_safety_assessment == "REVIEW":
        verdict = f"该名称存在一定风险，建议人工复核后决定是否提交"
    else:
        verdict = f"该名称POCA得分过高（{poca_response.worst_score:.2f}），不建议使用"

    return NameEvaluationResponse(
        proposed_name=proposed_name,
        poca_score=poca_response.worst_score,
        poca_assessment=poca_response.overall_safety_assessment,
        phonetic_score=worst_detail.phonetic_score if worst_detail else 0,
        orthographic_score=worst_detail.orthographic_score if worst_detail else 0,
        compositional_score=worst_detail.compositional_score if worst_detail else 0,
        worst_comparison=poca_response.worst_comparison or "",
        poca_detail=worst_detail,
        chinese_suggestions=chinese_suggestions,
        verdict=verdict,
        reasons=reasons,
        risks=risks,
    )


# Import here to avoid circular dependency
from ..engines.name_generator import NameGenerationEngine
