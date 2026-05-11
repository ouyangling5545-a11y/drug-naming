from __future__ import annotations
from pypinyin import lazy_pinyin, Style
from ..models.chinese import (
    ChineseCharacterSimilarity,
    ChineseNameCandidate,
    ChineseNameRequest,
    ChineseNameResponse,
)


# Common Chinese characters used in drug naming by category
CHARACTER_BY_CATEGORY: dict[str, list[str]] = {
    "kinase_inhibitor": ["替", "尼", "瑞", "拉", "帕", "非", "托", "司", "吉", "布"],
    "antibody": ["单", "抗", "利", "珠", "妥", "依", "尤", "度", "帕", "德"],
    "anti_inflammatory": ["松", "奈", "德", "米", "替", "卡", "泼", "龙", "可", "乐"],
    "antibiotic": ["霉", "素", "沙", "星", "西", "林", "头", "孢", "环", "米"],
    "cardiovascular": ["普", "利", "沙", "坦", "地", "平", "洛", "尔", "卡", "替"],
    "oncology": ["替", "尼", "拉", "帕", "瑞", "非", "布", "司", "吉", "托"],
    "peptide": ["肽", "鲁", "拉", "米", "格", "那", "司", "替", "瑞", "来"],
    "antiviral": ["韦", "拉", "匹", "那", "瑞", "德", "布", "洛", "夫", "他"],
    "immunomodulator": ["莫", "德", "司", "替", "利", "克", "托", "瑞", "拉", "帕"],
    "generic": ["安", "康", "平", "宁", "通", "达", "舒", "泰", "克", "灵"],
}

# Common drug name radicals / components
DRUG_RADICALS: dict[str, str] = {
    "月": "flesh/organic — often in organ-related drugs",
    "艹": "grass/plant — herbal or natural origin",
    "酉": "wine/fermentation — chemical or fermented",
    "石": "stone/mineral — mineral-derived",
    "氵": "water — water-soluble or liquid",
    "火": "fire — thermal or metabolic",
    "木": "wood — botanical origin",
    "钅": "metal — metallic or coordination compounds",
}

# Chinese stroke count data for common drug characters
# (simplified; would be expanded with real database)
STROKE_DATA: dict[str, int] = {
    "替": 12, "尼": 5, "瑞": 13, "拉": 8, "帕": 8, "非": 8, "托": 6, "司": 5,
    "吉": 6, "布": 5, "单": 8, "抗": 7, "利": 7, "珠": 10, "妥": 7, "依": 8,
    "尤": 4, "度": 9, "德": 15, "松": 8, "奈": 8, "米": 6, "卡": 5, "泼": 8,
    "龙": 5, "可": 5, "乐": 5, "霉": 15, "素": 10, "沙": 7, "星": 9, "西": 6,
    "林": 8, "头": 5, "孢": 8, "环": 8, "普": 12, "坦": 8, "地": 6, "平": 5,
    "洛": 9, "尔": 5, "肽": 9, "鲁": 12, "格": 10, "那": 6, "韦": 4, "匹": 4,
    "夫": 4, "他": 5, "莫": 10, "克": 7, "托": 6, "安": 6, "康": 11, "宁": 5,
    "通": 10, "达": 6, "舒": 12, "泰": 10, "灵": 7, "伐": 6, "仑": 4, "伐": 6, "仑": 4,
}

# Characters forbidden in drug names (regulatory)
FORBIDDEN_CHARS: frozenset[str] = frozenset({
    "神", "仙", "灵", "宝", "圣", "王", "皇", "霸", "绝", "奇",
    "最", "第", "首", "冠", "金", "银", "钻",
})


class ChineseNameEngine:
    """Generates and screens Chinese drug names per CDE/NMPA conventions."""

    def __init__(self, approved_names_db: list[dict] | None = None) -> None:
        self.approved_names: list[dict] = approved_names_db or []

    def suggest(self, request: ChineseNameRequest) -> ChineseNameResponse:
        candidates: list[ChineseNameCandidate] = []
        properties = request.pharmacological_properties

        # Determine drug category for character selection
        category = self._infer_category(properties)
        char_pool = CHARACTER_BY_CATEGORY.get(category, CHARACTER_BY_CATEGORY["generic"])

        # Add user-preferred characters
        if request.preferred_characters:
            char_pool = request.preferred_characters + char_pool

        # Generate 2-5 character name combinations
        min_chars = 2
        max_chars = min(5, len(char_pool))

        for length in range(min_chars, max_chars + 1):
            for i in range(min(len(char_pool), 20)):
                combos = self._gen_combinations(char_pool, length, max_combos=5)
                for combo in combos:
                    chinese_name = "".join(combo)
                    pinyin = "".join(lazy_pinyin(chinese_name, style=Style.TONE))
                    candidates.append(self._build_candidate(chinese_name, pinyin, request))

                if len(candidates) >= request.max_candidates:
                    break
            if len(candidates) >= request.max_candidates:
                break

        candidates = candidates[:request.max_candidates]
        return ChineseNameResponse(candidates=candidates)

    def check_similarity(self, name1: str, name2: str) -> ChineseCharacterSimilarity:
        """Compute character-level similarity between two Chinese drug names."""
        if not name1 or not name2:
            return ChineseCharacterSimilarity(char1="", char2="")

        # Compare character by character
        similarities: list[ChineseCharacterSimilarity] = []
        for c1, c2 in zip(name1, name2):
            sim = self._char_similarity(c1, c2)
            similarities.append(sim)

        if not similarities:
            return ChineseCharacterSimilarity(char1=name1, char2=name2)

        # Aggregate
        avg_radical = sum(s.radical_similarity for s in similarities) / len(similarities)
        avg_shape = sum(s.shape_similarity_score for s in similarities) / len(similarities)
        avg_pron = sum(s.pronunciation_similarity for s in similarities) / len(similarities)
        avg_stroke = sum(s.stroke_count_diff for s in similarities) / len(similarities)

        overall = 0.4 * avg_shape + 0.35 * avg_pron + 0.25 * (1.0 - min(avg_stroke / 20, 1.0))

        return ChineseCharacterSimilarity(
            char1=name1,
            char2=name2,
            radical_similarity=avg_radical,
            stroke_count_diff=int(avg_stroke),
            shape_similarity_score=avg_shape,
            pronunciation_similarity=avg_pron,
            overall_similarity=overall,
        )

    def screen_against_approved(self, candidate: ChineseNameCandidate) -> ChineseNameCandidate:
        """Screen a candidate name against all approved names."""
        for approved in self.approved_names:
            approved_name = approved.get("chinese_name", "")
            if not approved_name:
                continue
            sim = self.check_similarity(candidate.chinese_name, approved_name)
            if sim.overall_similarity > 0.70:
                candidate.regulatory_flags.append(f"too_similar_to_{approved_name}")
                candidate.regulatory_compliance = False
            candidate.similarity_to_approved.append(sim)
        return candidate

    def _build_candidate(
        self, chinese_name: str, pinyin: str, request: ChineseNameRequest
    ) -> ChineseNameCandidate:
        chars = list(chinese_name)
        stroke_count = sum(STROKE_DATA.get(c, 10) for c in chars)
        flags: list[str] = []

        # Regulatory checks
        if any(c in FORBIDDEN_CHARS for c in chars):
            flags.append("contains_forbidden_character")
        if len(chars) < 2:
            flags.append("too_few_characters")
        if len(chars) > 5:
            flags.append("too_many_characters")

        candidate = ChineseNameCandidate(
            chinese_name=chinese_name,
            pinyin=pinyin,
            source_stem_translation=request.target_meaning,
            characters=chars,
            stroke_count=stroke_count,
            meaning_gloss=request.target_meaning,
            regulatory_compliance=len(flags) == 0,
            regulatory_flags=flags,
            overall_score=1.0 if len(flags) == 0 else max(0.0, 1.0 - 0.3 * len(flags)),
        )

        # Screen against approved names
        if self.approved_names:
            candidate = self.screen_against_approved(candidate)

        return candidate

    def _char_similarity(self, c1: str, c2: str) -> ChineseCharacterSimilarity:
        """Compare two individual Chinese characters."""
        if c1 == c2:
            return ChineseCharacterSimilarity(
                char1=c1, char2=c2,
                radical_similarity=1.0, stroke_count_diff=0,
                shape_similarity_score=1.0, pronunciation_similarity=1.0,
                overall_similarity=1.0,
            )

        strokes1 = STROKE_DATA.get(c1, 10)
        strokes2 = STROKE_DATA.get(c2, 10)
        stroke_diff = abs(strokes1 - strokes2)
        stroke_sim = 1.0 - min(stroke_diff / 15.0, 1.0)

        pinyin1 = "".join(lazy_pinyin(c1, style=Style.NORMAL))
        pinyin2 = "".join(lazy_pinyin(c2, style=Style.NORMAL))
        pron_sim = 1.0 if pinyin1 == pinyin2 else (0.5 if pinyin1 and pinyin2 and pinyin1[0] == pinyin2[0] else 0.0)

        # Radical similarity: placeholder (would use real radical DB)
        radical_sim = 0.0

        # Shape similarity proxy: stroke count similarity + radical placeholder
        shape_sim = 0.6 * stroke_sim + 0.4 * radical_sim

        overall = 0.4 * shape_sim + 0.35 * pron_sim + 0.25 * stroke_sim

        return ChineseCharacterSimilarity(
            char1=c1, char2=c2,
            radical_similarity=radical_sim,
            stroke_count_diff=stroke_diff,
            shape_similarity_score=shape_sim,
            pronunciation_similarity=pron_sim,
            overall_similarity=overall,
        )

    @staticmethod
    def _infer_category(properties: dict) -> str:
        target = properties.get("target_class", "").lower()
        mechanism = properties.get("mechanism", "").lower()
        chemical = properties.get("chemical_class", "").lower()

        if "kinase" in target or "kinase" in mechanism:
            return "kinase_inhibitor"
        if "antibody" in chemical or "monoclonal" in chemical:
            return "antibody"
        if "peptide" in chemical:
            return "peptide"
        if "oncology" in properties.get("indication", "").lower() or "cancer" in properties.get("indication", "").lower():
            return "oncology"
        if "infection" in properties.get("indication", "").lower() or "antiviral" in mechanism:
            return "antiviral"
        if "cardiovascular" in properties.get("indication", "").lower():
            return "cardiovascular"
        if "immune" in mechanism or "immunomod" in mechanism:
            return "immunomodulator"
        if "antibiotic" in mechanism or "antibacterial" in mechanism:
            return "antibiotic"
        return "generic"

    @staticmethod
    def _gen_combinations(char_pool: list[str], length: int, max_combos: int = 5) -> list[tuple[str, ...]]:
        """Generate a few representative character combinations of given length."""
        results: list[tuple[str, ...]] = []
        pool = char_pool[:12]  # Limit pool for combinatorial sanity
        if length > len(pool):
            return results
        if length == 2:
            for i, c1 in enumerate(pool[:6]):
                for c2 in pool[i + 1 : i + 7]:
                    if len(results) < max_combos:
                        results.append((c1, c2))
        elif length == 3:
            for i, c1 in enumerate(pool[:3]):
                for j, c2 in enumerate(pool[3:6]):
                    for c3 in pool[6:9]:
                        if len(results) < max_combos:
                            results.append((c1, c2, c3))
        elif length == 4:
            for c1 in pool[:2]:
                for c2 in pool[2:4]:
                    for c3 in pool[4:6]:
                        for c4 in pool[6:8]:
                            if len(results) < max_combos:
                                results.append((c1, c2, c3, c4))
        return results
