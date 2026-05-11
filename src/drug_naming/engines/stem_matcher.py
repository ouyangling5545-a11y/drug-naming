from __future__ import annotations
from typing import Protocol
from ..models.molecule import PharmacologicalProperties
from ..models.stem import INNStem, StemMatch, StemCategory, StemMatchingConfig


class StemDataProvider(Protocol):
    """Protocol for stem data source — user plugs in their data here."""

    def get_all_stems(self) -> list[INNStem]: ...
    def get_stems_by_category(self, category: StemCategory) -> list[INNStem]: ...


class StemMatchingEngine:
    """Maps pharmacological properties to relevant WHO INN stems."""

    def __init__(
        self,
        data_provider: StemDataProvider,
        config: StemMatchingConfig | None = None,
    ) -> None:
        self.data_provider = data_provider
        self.config = config or StemMatchingConfig()

    def match(
        self,
        properties: PharmacologicalProperties,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> list[StemMatch]:
        top_k = top_k or self.config.max_results
        min_score = min_score or self.config.min_score

        all_stems = self.data_provider.get_all_stems()
        matches: list[StemMatch] = []

        for stem in all_stems:
            score, reasons = self._score_stem(properties, stem)
            if score >= min_score:
                matches.append(StemMatch(stem=stem, match_score=score, match_reasons=reasons))

        # Sort by score descending, then by priority descending
        matches.sort(key=lambda m: (m.match_score, m.stem.priority), reverse=True)
        return matches[:top_k]

    def _score_stem(
        self,
        properties: PharmacologicalProperties,
        stem: INNStem,
    ) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []

        # Target class: 35%
        if stem.target_classes and properties.target_class.value in [t.lower() for t in stem.target_classes]:
            score += self.config.target_class_weight
            reasons.append(f"target_class '{properties.target_class.value}' matched")

        # Mechanism: 30%
        if stem.mechanisms and properties.mechanism.value in [m.lower() for m in stem.mechanisms]:
            score += self.config.mechanism_weight
            reasons.append(f"mechanism '{properties.mechanism.value}' matched")

        # Chemical class: 25%
        if stem.chemical_classes and properties.chemical_class.value in [c.lower() for c in stem.chemical_classes]:
            score += self.config.chemical_class_weight
            reasons.append(f"chemical_class '{properties.chemical_class.value}' matched")

        # Indication: 10% with Jaccard token overlap
        if stem.indications:
            indication_tokens = set(properties.indication.lower().split())
            best_jaccard = 0.0
            best_indication = ""
            for stem_ind in stem.indications:
                stem_tokens = set(stem_ind.lower().split())
                overlap = len(indication_tokens & stem_tokens)
                union = len(indication_tokens | stem_tokens)
                jaccard = overlap / union if union > 0 else 0.0
                if jaccard > best_jaccard:
                    best_jaccard = jaccard
                    best_indication = stem_ind
            indication_score = self.config.indication_weight * best_jaccard
            score += indication_score
            if indication_score > 0:
                reasons.append(f"indication keywords matched '{best_indication}' (Jaccard={best_jaccard:.2f})")

        # Chemical substructure bonus (up to +10%)
        if properties.chemical_structure_substructure and stem.chemical_classes:
            bonus = self._substructure_bonus(properties.chemical_structure_substructure, stem)
            score = min(1.0, score + bonus)
            if bonus > 0:
                reasons.append(f"substructure '{properties.chemical_structure_substructure}' matched chemical_class")

        return score, reasons

    def _substructure_bonus(self, substructure: str, stem: INNStem) -> float:
        """Bonus score if substructure name appears in stem meaning or chemical classes."""
        sub_lower = substructure.lower()
        # Check stem meaning
        if sub_lower in stem.meaning.lower():
            return self.config.substructure_bonus_max * 0.6
        # Check chemical classes
        for cc in stem.chemical_classes:
            if sub_lower in cc.lower():
                return self.config.substructure_bonus_max * 0.4
        # Check stem text itself
        if sub_lower in stem.stem.lower():
            return self.config.substructure_bonus_max * 0.3
        return 0.0
