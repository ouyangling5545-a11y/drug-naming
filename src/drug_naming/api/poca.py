from __future__ import annotations
from pydantic import BaseModel, Field
from fastapi import APIRouter, Request
from ..models.poca import POCARequest, POCAResponse, POCAWeights, POCAScoreDetail, POCAScoreDetail
from ..models.chinese import ChineseNameCandidate
from ..engines.poca_scorer import POCAScoringEngine
from ..data.inn_reference import get_inn_reference_db
from ..engines.latin_name import (
    derive_latin_name,
    check_latin_taboo,
    check_french_taboo,
    check_spanish_taboo,
    LATIN_SUFFIX_RULES,
)
from ..engines.chinese_transliteration import (
    transliterate_to_chinese,
    check_chinese_transliteration_taboo,
    SYLLABLE_TO_CHAR,
)
from .stems import _get_default_provider

# Alternate syllable→character choices for prefix transliteration variants
# Each key maps to [primary, alternate1, alternate2]
_PFX_ALTERNATES: dict[str, list[str]] = {
    "so": ["索", "苏", "司"], "su": ["苏", "舒", "司"],
    "ra": ["拉", "雷", "瑞"], "re": ["瑞", "雷", "热"],
    "fa": ["法", "发", "伐"], "fe": ["非", "费", "芬"], "fi": ["非", "芬", "费"],
    "pa": ["帕", "派", "巴"], "pe": ["培", "佩", "普"], "pi": ["匹", "皮", "吡"],
    "ma": ["马", "玛", "麻"], "me": ["美", "梅", "莫"], "mi": ["米", "密", "咪"],
    "ta": ["他", "它", "塔"], "te": ["特", "忒", "替"], "ti": ["替", "提", "体"],
    "mo": ["莫", "摩", "模"], "to": ["托", "妥", "拓"],
    "ni": ["尼", "妮", "匿"], "na": ["那", "纳", "娜"],
    "ro": ["罗", "洛", "若"], "ri": ["利", "日", "力"],
    "va": ["伐", "瓦", "万"], "ve": ["维", "韦", "威"], "vi": ["维", "威", "韦"],
    "si": ["司", "西", "斯"], "sa": ["沙", "萨", "撒"],
    "ca": ["卡", "咖", "喀"], "co": ["考", "可", "柯"], "ci": ["西", "次", "此"],
    "ce": ["塞", "色", "策"], "le": ["来", "乐", "勒"],
    "li": ["利", "里", "力"], "lo": ["洛", "罗", "络"], "la": ["拉", "喇", "腊"],
    "do": ["多", "度", "朵"], "da": ["达", "大", "答"],
    "de": ["德", "得", "地"], "di": ["地", "迪", "底"], "du": ["度", "杜", "都"],
    "be": ["贝", "倍", "北"], "bo": ["博", "波", "泊"],
    "po": ["泊", "波", "颇"], "pu": ["普", "浦", "扑"],
    "bu": ["布", "补", "步"], "bi": ["比", "必", "必"],
    "ga": ["加", "伽", "嘎"], "ge": ["吉", "格", "哥"],
    "go": ["戈", "果", "过"], "gu": ["古", "谷", "固"],
    "ha": ["哈", "赫", "海"], "he": ["赫", "合", "和"],
    "ka": ["卡", "喀", "咖"], "ke": ["可", "克", "科"],
    "ne": ["奈", "内", "讷"], "no": ["诺", "挪", "娜"],
    "ru": ["鲁", "如", "汝"], "se": ["司", "色", "瑟"],
    "za": ["扎", "杂", "匝"], "zo": ["佐", "作", "左"],
    "an": ["安", "昂", "氨"], "ar": ["阿", "阿尔", "尔"],
    "es": ["艾司", "伊司", "厄司"], "ex": ["艾克", "伊克", "厄克"],
}


def _transliterate_with_alt(syllable: str, alt_idx: int) -> str:
    """Get transliteration for a syllable, optionally using an alternate character."""
    alts = _PFX_ALTERNATES.get(syllable)
    if alts and alt_idx < len(alts):
        return alts[alt_idx]
    # Fall back to standard mapping
    for syl, ch in SYLLABLE_TO_CHAR:
        if syl == syllable:
            return ch
    return syllable


def _transliterate_prefix_variants(prefix: str, n: int = 3) -> list[str]:
    """Generate N Chinese transliteration variants for a prefix using syllable alternates."""
    if not prefix:
        return [""] * max(1, n)

    # Build syllable breakdown using existing greedy algorithm
    pfx = prefix.lower()
    syllables: list[str] = []
    pos = 0
    while pos < len(pfx):
        matched = False
        for syl, ch in SYLLABLE_TO_CHAR:
            if pfx.startswith(syl, pos):
                syllables.append(syl)
                pos += len(syl)
                matched = True
                break
        if not matched:
            pos += 1

    variants: list[str] = []
    for vi in range(n):
        result = ""
        for syl in syllables:
            result += _transliterate_with_alt(syl, vi)
        if result and result not in variants:
            variants.append(result)

    # Fill remaining slots if not enough unique variants
    while len(variants) < n:
        # Try different alternations of first/second syllable
        attempt = ""
        seed = len(variants)
        for i, syl in enumerate(syllables):
            if i == seed % len(syllables) if syllables else 0:
                attempt += _transliterate_with_alt(syl, (seed % 2) + 1)
            else:
                attempt += _transliterate_with_alt(syl, 0)
        if attempt not in variants:
            variants.append(attempt)
        else:
            break
    while len(variants) < n:
        variants.append(variants[0])

    return variants[:n]


class LanguageNameVariant(BaseModel):
    language: str       # "latin", "french", "spanish", "chinese_transliteration"
    name: str
    source: str         # "inn_database", "derived", "transliteration", "not_available"
    commentary: str
    taboo_flags: list[str] = Field(default_factory=list)


class NameEvaluationResponse(BaseModel):
    proposed_name: str
    poca_score: float  # worst (highest) FDA 2D score
    poca_assessment: str  # PASS / REVIEW / REJECT
    phonetic_score: float
    orthographic_score: float
    compositional_score: float
    worst_comparison: str
    poca_detail: POCAScoreDetail | None = None
    chinese_suggestions: list[ChineseNameCandidate] = Field(default_factory=list, description="Deprecated: use Tab A Chinese naming instead")
    similar_names: list[POCAScoreDetail] = Field(default_factory=list)
    similar_count: int = 0
    total_references: int = 0
    threshold: float = 0.55
    verdict: str
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    language_variants: list[LanguageNameVariant] = Field(default_factory=list)
    phonetic_method: str = "metaphone"
    # Alternate method results for instant sub-tab switching
    aline_phonetic_score: float = 0.0
    aline_poca_score: float = 0.0
    aline_similar_count: int = 0
    aline_worst_comparison: str = ""
    metaphone_phonetic_score: float = 0.0
    metaphone_poca_score: float = 0.0
    metaphone_similar_count: int = 0
    metaphone_worst_comparison: str = ""

def _describe_latin_taboos(flags: list[str]) -> str:
    if not flags:
        return "，未发现拉丁语禁忌词汇"
    terms = [f.split(":")[-1] for f in flags]
    return f"，注意：发现拉丁语禁忌词汇 {', '.join(terms)}（含医疗宣称或绝对化表述，可能被 EMA 拒绝）"


def _describe_french_taboos(flags: list[str]) -> str:
    if not flags:
        return "，未发现法语禁忌词汇"
    terms = [f.split(":")[-1] for f in flags]
    return f"，注意：发现法语禁忌词汇 {', '.join(terms)}（含治愈、神奇等暗示性表述，可能被 ANSM 拒绝）"


def _describe_spanish_taboos(flags: list[str]) -> str:
    if not flags:
        return "，未发现西班牙语禁忌词汇"
    terms = [f.split(":")[-1] for f in flags]
    return f"，注意：发现西班牙语禁忌词汇 {', '.join(terms)}（含治愈、奇迹等暗示性表述，可能被 AEMPS 拒绝）"


def _describe_chinese_taboos(flags: list[str]) -> str:
    if not flags:
        return "，未发现禁用汉字"
    chars = [f.split(":")[-1] for f in flags]
    count = len(chars)
    return f"，注意：发现 {count} 个禁用汉字{'、'.join(chars) if chars else ''}（含“神、仙、灵、宝”等暗示功效/夸大表述，违反中国药典命名原则）"


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
    threshold: float = 55.0,
    max_similar: int = 100,
    phonetic_method: str = "metaphone",
    request: Request = None,
) -> NameEvaluationResponse:
    """One-stop name evaluation with FDA-style 2D POCA scoring.

    Scores the proposed name against the entire INN reference database
    using Phonetic + Orthographic dimensions only (FDA POCA methodology).
    Returns all names scoring at or above the threshold (default 55%), capped at max_similar.

    phonetic_method: 'metaphone' (default, fast Double Metaphone engine) or
                     'aline' (Kondrak 2000 articulatory feature alignment, slower but
                     captures partial phonetic overlap across prefix boundaries).
    """
    engine = _get_poca_engine(request)
    inn_db = get_inn_reference_db()
    name_clean = proposed_name.strip()
    name_lower = name_clean.lower()

    # 1. Fast batch screening with Metaphone (always) — ALINE is too slow for 13K names
    engine.phonetic_method = "metaphone"
    all_refs = sorted(inn_db.english_names) if inn_db else []
    similar_names = engine.score_batch_fda(name_clean, all_refs, threshold=threshold / 100.0, max_results=max_similar)

    # 2. Worst comparison from Metaphone screening
    worst_detail = similar_names[0] if similar_names else None
    worst_comparison = worst_detail.reference_name if worst_detail else ""

    # 3. Compute BOTH methods' scores for the worst pair only (avoids ALINE O(N) cost)
    engine.phonetic_method = "metaphone"
    meta_detail = engine.score_pair(name_clean, worst_comparison) if worst_comparison else None
    metaphone_phonetic = meta_detail.phonetic_score if meta_detail else 0.0
    metaphone_poca = meta_detail.overall_poca_score if meta_detail else 0.0

    engine.phonetic_method = "aline"
    aline_detail = engine.score_pair(name_clean, worst_comparison) if worst_comparison else None
    aline_phonetic = aline_detail.phonetic_score if aline_detail else 0.0
    aline_poca = aline_detail.overall_poca_score if aline_detail else 0.0

    # 4. Use requested method's scores as primary display
    if phonetic_method == "aline":
        phonetic_score = aline_phonetic
        orthographic_score = worst_detail.orthographic_score if worst_detail else 0.0
        worst_score = aline_poca
    else:
        phonetic_score = metaphone_phonetic
        orthographic_score = worst_detail.orthographic_score if worst_detail else 0.0
        worst_score = metaphone_poca
    compositional_score = worst_detail.compositional_score if worst_detail else 0.0

    # 3. 多语言名称变体（拉丁/法语/西语查询+推导，中文音译）
    language_variants: list[LanguageNameVariant] = []

    # 拉丁名：优先查 INN 数据库，否则用尾缀规则推导
    latin_from_db = inn_db.lookup_latin(name_clean) if inn_db else None
    if latin_from_db:
        latin_taboos = check_latin_taboo(latin_from_db)
        latin_note = _describe_latin_taboos(latin_taboos)
        language_variants.append(LanguageNameVariant(
            language="latin",
            name=latin_from_db,
            source="inn_database",
            commentary=f"从 WHO INN 数据库直接获取 '{name_clean}' 的官方拉丁名{latin_note}",
            taboo_flags=latin_taboos,
        ))
    else:
        derived_latin = derive_latin_name(name_clean)
        latin_taboos = check_latin_taboo(derived_latin)
        latin_note = _describe_latin_taboos(latin_taboos)
        language_variants.append(LanguageNameVariant(
            language="latin",
            name=derived_latin,
            source="derived",
            commentary=f"数据库中未收录 '{name_clean}'，通过 {len(LATIN_SUFFIX_RULES)} 条拉丁尾缀规则自动推导（如 -tinib→-tinibum, -mab→-mabum，按最长匹配优先）{latin_note}",
            taboo_flags=latin_taboos,
        ))

    # 法语名：仅查 INN 数据库，无推导规则
    french_from_db = inn_db.lookup_french(name_clean) if inn_db else None
    if french_from_db:
        french_taboos = check_french_taboo(french_from_db)
        french_note = _describe_french_taboos(french_taboos)
        language_variants.append(LanguageNameVariant(
            language="french",
            name=french_from_db,
            source="inn_database",
            commentary=f"从 WHO INN 数据库直接获取 '{name_clean}' 的官方法语名{french_note}",
            taboo_flags=french_taboos,
        ))
    else:
        language_variants.append(LanguageNameVariant(
            language="french",
            name=name_clean,
            source="not_available",
            commentary=f"数据库中无 '{name_clean}' 的法语对应数据，建议在提交欧盟 ANSM 前进行人工语言学审查",
            taboo_flags=[],
        ))

    # 西班牙语名：仅查 INN 数据库，无推导规则
    spanish_from_db = inn_db.lookup_spanish(name_clean) if inn_db else None
    if spanish_from_db:
        spanish_taboos = check_spanish_taboo(spanish_from_db)
        spanish_note = _describe_spanish_taboos(spanish_taboos)
        language_variants.append(LanguageNameVariant(
            language="spanish",
            name=spanish_from_db,
            source="inn_database",
            commentary=f"从 WHO INN 数据库直接获取 '{name_clean}' 的官方西班牙语名{spanish_note}",
            taboo_flags=spanish_taboos,
        ))
    else:
        language_variants.append(LanguageNameVariant(
            language="spanish",
            name=name_clean,
            source="not_available",
            commentary=f"数据库中无 '{name_clean}' 的西班牙语对应数据，建议在提交拉美 AEMPS 前进行人工语言学审查",
            taboo_flags=[],
        ))

    # 中文音译：后缀词干用 stems.csv 固定中文，前缀音译 ×3 组
    provider = _get_default_provider()
    all_stems = provider.get_all_stems()

    # Build stem→chinese lookup, longest first
    stem_cn_list: list[tuple[str, str, str]] = []  # (core_lower, chinese, original_stem)
    for s in all_stems:
        if s.chinese and s.stem:
            core = s.stem.lstrip("-").lower()
            cn = s.chinese.lstrip("-").strip()
            if len(core) >= 2 and cn:
                stem_cn_list.append((core, cn, s.stem))
    stem_cn_list.sort(key=lambda x: -len(x[0]))

    # Detect longest matching suffix stem
    detected_core = ""
    detected_cn = ""
    detected_pfx = name_clean
    for core, cn, orig in stem_cn_list:
        if name_lower.endswith(core) and len(core) > len(detected_core):
            detected_core = core
            detected_cn = cn
            detected_pfx = name_clean[:len(name_clean) - len(core)].rstrip("-")

    if detected_core and len(detected_pfx) >= 1:
        # Suffix stem found — generate 3 prefix transliteration variants
        pfx_variants = _transliterate_prefix_variants(detected_pfx, n=3)
        for i, pfx_cn in enumerate(pfx_variants):
            cn_name = pfx_cn + detected_cn
            cn_taboos = check_chinese_transliteration_taboo(cn_name)
            cn_note = _describe_chinese_taboos(cn_taboos)
            label = f"CN-{i+1}"
            language_variants.append(LanguageNameVariant(
                language="chinese_transliteration",
                name=cn_name,
                source="transliteration",
                commentary=f"词干 '-{detected_core}' → '{detected_cn}'（stems.csv固定），前缀 '{detected_pfx}' 音译变体{label[-1]}{cn_note}",
                taboo_flags=cn_taboos,
            ))
    else:
        # No known suffix stem — full-name transliteration
        chinese_trans = transliterate_to_chinese(name_clean)
        chinese_taboos = check_chinese_transliteration_taboo(chinese_trans)
        chinese_note = _describe_chinese_taboos(chinese_taboos)
        language_variants.append(LanguageNameVariant(
            language="chinese_transliteration",
            name=chinese_trans,
            source="transliteration",
            commentary=f"未检测到已知词干后缀，将 '{name_clean}' 按 {len(SYLLABLE_TO_CHAR)} 条音节-汉字映射表进行贪心最长匹配音译{chinese_note}",
            taboo_flags=chinese_taboos,
        ))

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
        chinese_suggestions=[],
        similar_names=similar_names[:max_similar],
        similar_count=len(similar_names),
        total_references=len(all_refs),
        threshold=threshold / 100.0,
        verdict=verdict,
        reasons=reasons,
        risks=risks,
        language_variants=language_variants,
        phonetic_method=phonetic_method,
        aline_phonetic_score=aline_phonetic,
        aline_poca_score=aline_poca,
        aline_similar_count=len(similar_names),
        aline_worst_comparison=worst_comparison,
        metaphone_phonetic_score=metaphone_phonetic,
        metaphone_poca_score=metaphone_poca,
        metaphone_similar_count=len(similar_names),
        metaphone_worst_comparison=worst_comparison,
    )
