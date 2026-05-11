from __future__ import annotations
from ..models.brand import BrandNameCandidate, BrandScreenRequest, BrandScreenResponse
from .poca_scorer import POCAScoringEngine
from .phonetic import PhoneticEncoder
from .orthographic import OrthographicAnalyzer


class BrandNameEngine:
    """Screens and scores brand/trade names against regulatory and market criteria."""

    def __init__(
        self,
        existing_brands: list[str] | None = None,
        poca_engine: POCAScoringEngine | None = None,
    ) -> None:
        self.existing_brands: list[str] = existing_brands or []
        self.poca = poca_engine or POCAScoringEngine()
        self.phonetic = PhoneticEncoder()
        self.orthographic = OrthographicAnalyzer()

    def screen(self, request: BrandScreenRequest) -> BrandScreenResponse:
        results: list[BrandNameCandidate] = []
        for brand_name in request.proposed_brand_names:
            candidate = self._evaluate_brand(
                brand_name, request.inn_name, request.existing_brand_db or self.existing_brands
            )
            results.append(candidate)

        results.sort(key=lambda r: r.overall_score, reverse=True)
        top = results[0] if results else None

        return BrandScreenResponse(results=results, top_candidate=top)

    def _evaluate_brand(
        self, brand_name: str, inn_name: str, existing_brand_db: list[str]
    ) -> BrandNameCandidate:
        # 1. Similarity to INN (should be LOW for safety)
        inn_similarity = self._compute_inn_similarity(brand_name, inn_name)

        # 2. Similarity to existing brands
        max_brand_similarity = self._compute_max_brand_similarity(brand_name, existing_brand_db)

        # 3. Semantic associations
        semantic_associations = self._analyze_semantics(brand_name)

        # 4. Marketability
        marketability = self._marketability_score(brand_name)

        # 5. Regulatory flags
        flags = self._check_regulatory(brand_name, inn_name, inn_similarity, max_brand_similarity)

        # Overall score: weighted combination (higher = better candidate)
        # INN similarity: penalty (want LOW), so use (1 - similarity)
        # Brand similarity: penalty (want LOW)
        # Marketability: bonus
        overall = (
            0.30 * (1.0 - inn_similarity)
            + 0.35 * (1.0 - max_brand_similarity)
            + 0.15 * marketability
            + 0.20 * (1.0 if not flags else max(0.0, 1.0 - 0.3 * len(flags)))
        )

        return BrandNameCandidate(
            brand_name=brand_name,
            inn_name=inn_name,
            similarity_to_inn=inn_similarity,
            similarity_to_existing_brands=max_brand_similarity,
            semantic_associations=semantic_associations,
            regulatory_flags=flags,
            marketability_score=marketability,
            overall_score=overall,
        )

    def _compute_inn_similarity(self, brand: str, inn: str) -> float:
        """Compute how similar the brand name is to the INN (should be low)."""
        # Use orthographic and phonetic similarity
        _, ortho_score = self.orthographic.compute_orthographic(brand, inn)
        _, phonetic_score = self.phonetic.compute_phonetics(brand, inn)
        return 0.55 * ortho_score + 0.45 * phonetic_score

    def _compute_max_brand_similarity(self, brand: str, existing_db: list[str]) -> float:
        if not existing_db:
            return 0.0
        max_sim = 0.0
        for existing in existing_db:
            result = self.poca.score_pair(brand, existing)
            if result.overall_poca_score > max_sim:
                max_sim = result.overall_poca_score
        return max_sim

    @staticmethod
    def _analyze_semantics(brand_name: str) -> list[str]:
        """Check for semantic associations — positive/negative connotations."""
        associations: list[str] = []
        name_lower = brand_name.lower()

        positive_roots = {
            "vita": "life/vitality",
            "nova": "new/innovation",
            "cura": "care/cure",
            "thera": "therapy",
            "medi": "medicine",
            "pharma": "pharmaceutical",
            "bio": "life/biotechnology",
            "gen": "genesis/creation",
            "cel": "speed/excellence",
            "sol": "solution/sun",
        }

        negative_roots = {
            "tox": "toxic",
            "mort": "death",
            "mal": "bad/illness",
            "fatal": "fatal",
            "pain": "pain",
            "virus": "virus",
        }

        for root, meaning in positive_roots.items():
            if root in name_lower:
                associations.append(f"positive: {meaning}")

        for root, meaning in negative_roots.items():
            if root in name_lower:
                associations.append(f"WARNING — negative: {meaning}")

        return associations

    @staticmethod
    def _marketability_score(name: str) -> float:
        """Score 0-1 for marketability: length, pronounceability, uniqueness."""
        score = 1.0
        name_lower = name.lower()

        # Length: ideal 5-8 characters
        length = len(name)
        if length < 4:
            score -= 0.15
        elif length > 12:
            score -= 0.10
        elif 5 <= length <= 8:
            score += 0.10

        # Pronounceability: consonant-vowel alternation
        vowels = frozenset("aeiouy")
        alt_count = sum(
            1 for i in range(len(name_lower) - 1)
            if (name_lower[i] in vowels) != (name_lower[i + 1] in vowels)
        )
        cv_ratio = alt_count / max(len(name_lower) - 1, 1)
        if cv_ratio > 0.7:
            score += 0.10
        elif cv_ratio < 0.4:
            score -= 0.10

        # Uniqueness: penalize very common syllables
        common_syllables = ["pro", "max", "plus", "med", "drug", "cure", "health"]
        for syl in common_syllables:
            if syl in name_lower:
                score -= 0.10
                break

        return max(0.0, min(1.0, score))

    @staticmethod
    def _check_regulatory(
        brand: str, inn: str, inn_sim: float, brand_sim: float
    ) -> list[str]:
        flags: list[str] = []
        if inn_sim > 0.50:
            flags.append("too_similar_to_INN")
        if brand_sim > 0.70:
            flags.append("too_similar_to_existing_brand")
        if len(brand) < 3:
            flags.append("name_too_short")
        if len(brand) > 20:
            flags.append("name_too_long")
        # Check if brand name contains INN stem
        brand_lower = brand.lower()
        inn_lower = inn.lower()
        if len(inn_lower) >= 4 and inn_lower in brand_lower:
            flags.append("contains_INN_name")
        if brand_lower == inn_lower:
            flags.append("identical_to_INN")
        return flags
