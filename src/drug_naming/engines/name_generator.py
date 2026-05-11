from __future__ import annotations
from ..models.molecule import ChemicalClass, PharmacologicalProperties
from ..models.stem import INNStem, StemMatch, StemPosition
from ..models.naming import (
    NameCandidate,
    NameGenerationConstraints,
    NameGenerationRequest,
    NameGenerationResponse,
)


# Prefix pools by chemical class
CHEMICAL_PREFIX_MAP: dict[ChemicalClass, list[str]] = {
    ChemicalClass.MONOCLONAL_ANTIBODY: [
        "a", "ba", "bi", "bo", "ca", "ce", "ci", "co", "cu", "da", "de", "di", "do",
        "e", "fa", "fe", "ga", "go", "gu", "ha", "he", "i", "ja", "je", "ka", "ki",
        "la", "le", "li", "lo", "lu", "ma", "me", "mi", "mo", "mu",
        "na", "ne", "ni", "no", "nu", "o", "pa", "pe", "pi", "po",
        "ra", "re", "ri", "ro", "ru",
        "sa", "se", "si", "so", "su",
        "ta", "te", "ti", "to", "tu",
        "va", "ve", "vi", "vo", "vu",
        "za", "ze", "zi", "zo", "zu",
    ],
    ChemicalClass.SMALL_MOLECULE: [
        "ab", "ac", "af", "al", "am", "an", "ap", "ar", "as", "at", "ax", "az",
        "ba", "be", "bi", "bo", "br", "bu",
        "ca", "ce", "ci", "co", "cu",
        "da", "de", "di", "do", "du",
        "el", "em", "en", "er", "es", "ev", "ex",
        "fa", "fe", "fi", "fl", "fo", "fr", "fu",
        "ga", "ge", "gi", "gl", "go", "gr", "gu",
        "ic", "il", "im", "in", "ir", "is", "it", "iv",
        "la", "le", "li", "lo", "lu",
        "ma", "me", "mi", "mo", "mu",
        "na", "ne", "ni", "no", "nu",
        "ol", "om", "on", "op", "or", "os", "ov", "ox",
        "pa", "pe", "pi", "pl", "po", "pr", "pu",
        "ra", "re", "ri", "ro", "ru",
        "sa", "se", "si", "so", "sp", "st", "su",
        "ta", "te", "th", "ti", "to", "tr", "tu",
        "va", "ve", "vi", "vo", "vu",
        "za", "ze", "zi", "zo", "zu",
    ],
    ChemicalClass.PEPTIDE: [
        "aba", "aca", "ala", "ara", "arg", "asn", "asp",
        "cys", "gln", "glu", "gly", "his", "ile", "leu",
        "lira", "lys", "met", "nal", "orn", "phe", "pro",
        "sema", "ser", "thr", "tide", "tir", "trp", "tyr", "val",
    ],
    ChemicalClass.OLIGONUCLEOTIDE: [
        "ali", "apo", "ato", "de", "gi", "mi", "oligo", "pli", "ri", "si", "te", "vi",
    ],
    ChemicalClass.SIRNA: [
        "fit", "gi", "li", "pa", "si", "ta", "te", "vi",
    ],
    ChemicalClass.MRNA: [
        "co", "mer", "mod", "ne", "re", "va", "vi", "za",
    ],
    ChemicalClass.ANTIBODY_FRAGMENT: [
        "ab", "an", "be", "ci", "da", "el", "fa", "ga", "la", "li", "ma", "na", "pa", "ra", "ta", "va", "za",
    ],
    ChemicalClass.BISPECIFIC_ANTIBODY: [
        "a", "ba", "bi", "ci", "da", "e", "fa", "ga", "la", "li", "ma", "na", "pa", "ra", "ta", "va", "za",
    ],
    ChemicalClass.ANTIBODY_DRUG_CONJUGATE: [
        "a", "be", "ce", "da", "e", "fa", "ga", "la", "li", "ma", "na", "pa", "ra", "ta", "va", "za",
    ],
    ChemicalClass.FUSION_PROTEIN: [
        "a", "ba", "bel", "cep", "da", "e", "fa", "ga", "la", "li", "ma", "na", "pa", "ra", "ta", "va",
    ],
}

VOWELS = frozenset("aeiouy")
CONSONANTS = frozenset("bcdfghjklmnpqrstvwxz")


class NameGenerationEngine:
    """Combinatorial INN name generation following WHO conventions.

    Can use an InnReferenceDB for comprehensive deduplication against 9378 real INN names.
    """

    def __init__(self, inn_reference_db=None) -> None:
        self._inn_db = inn_reference_db

    def generate(self, request: NameGenerationRequest) -> NameGenerationResponse:
        constraints = request.constraints
        prefixes = self._generate_prefix_pool(request.properties)
        stem_combos = self._build_stem_combos(request.matched_stems)
        existing_set = set(n.lower() for n in request.existing_names_to_avoid)

        all_candidates: list[NameCandidate] = []
        for stem_match in request.matched_stems:
            candidates = self._combinatorial_assemble(
                prefixes, stem_combos, stem_match, constraints
            )
            all_candidates.extend(candidates)

        total_generated = len(all_candidates)

        # Apply phonological scoring
        for c in all_candidates:
            c.phonological_score = self._phonological_score(c.name)

        # Merge user-provided existing names with INN reference database
        if self._inn_db is not None:
            inn_names = self._inn_db.english_names
            existing_set = existing_set | inn_names

        # Filter: existing names (trigram screening + exact INN match)
        filtered: list[NameCandidate] = []
        for c in all_candidates:
            if c.name.lower() in existing_set:
                c.regulatory_flags.append("exact_inn_conflict")
                continue
            if not self._passes_trigram_screen(c.name, existing_set):
                c.regulatory_flags.append("trigram_match_with_existing")
                continue
            # Check forbidden prefixes/suffixes
            name_lower = c.name.lower()
            if any(name_lower.startswith(p) for p in constraints.forbidden_prefixes):
                c.regulatory_flags.append("contains_forbidden_prefix")
                continue
            if any(name_lower.endswith(s) for s in constraints.forbidden_suffixes):
                c.regulatory_flags.append("contains_forbidden_suffix")
                continue
            # Length check
            if not (constraints.min_name_length <= len(c.name) <= constraints.max_name_length):
                continue
            # Consecutive consonant/vowel check
            if self._has_consecutive(c.name, CONSONANTS, constraints.max_consecutive_consonants + 1):
                c.regulatory_flags.append("too_many_consecutive_consonants")
                continue
            if self._has_consecutive(c.name, VOWELS, constraints.max_consecutive_vowels + 1):
                c.regulatory_flags.append("too_many_consecutive_vowels")
                continue
            filtered.append(c)

        # Sort by phonological score, deduplicate by name, cap
        filtered.sort(key=lambda c: c.phonological_score, reverse=True)
        seen: set[str] = set()
        unique: list[NameCandidate] = []
        for c in filtered:
            if c.name.lower() not in seen:
                seen.add(c.name.lower())
                unique.append(c)
                if len(unique) >= constraints.max_candidates_per_stem * len(request.matched_stems):
                    break

        return NameGenerationResponse(
            candidates=unique,
            total_generated=total_generated,
            filtered_out=total_generated - len(unique),
        )

    def _generate_prefix_pool(self, properties: PharmacologicalProperties) -> list[str]:
        prefixes = CHEMICAL_PREFIX_MAP.get(properties.chemical_class, CHEMICAL_PREFIX_MAP[ChemicalClass.SMALL_MOLECULE])
        # Add substructure-derived prefixes if available
        if properties.chemical_structure_substructure:
            sub = properties.chemical_structure_substructure.lower()
            if len(sub) >= 2:
                prefixes = [sub[:2], sub[:3], sub[:4]] + prefixes
        return prefixes

    def _build_stem_combos(
        self, matched_stems: list[StemMatch]
    ) -> list[tuple[str | None, str | None, str, StemMatch]]:
        """Build (prefix_placeholder, infix, suffix_stem, stem_match) combos."""
        results: list[tuple[str | None, str | None, str, StemMatch]] = []
        for sm in matched_stems:
            stem = sm.stem
            stem_text = stem.stem.strip("-")

            if stem.position == StemPosition.SUFFIX:
                if stem.infix_required and stem.allowed_infixes:
                    for infix in stem.allowed_infixes:
                        results.append((None, infix.strip("-"), stem_text, sm))
                else:
                    results.append((None, None, stem_text, sm))
            elif stem.position == StemPosition.PREFIX:
                if stem.allowed_infixes:
                    for infix in stem.allowed_infixes:
                        results.append((stem_text, infix.strip("-") if infix else None, None, sm))
                else:
                    results.append((stem_text, None, None, sm))
            elif stem.position == StemPosition.INFIX:
                results.append((None, stem_text, None, sm))

        return results

    def _combinatorial_assemble(
        self,
        prefixes: list[str],
        stem_combos: list[tuple[str | None, str | None, str, StemMatch]],
        stem_match: StemMatch,
        constraints: NameGenerationConstraints,
    ) -> list[NameCandidate]:
        candidates: list[NameCandidate] = []
        for prefix in prefixes:
            for pfx_placeholder, infix, suffix, sm in stem_combos:
                if sm != stem_match:
                    continue
                parts = [p for p in [prefix, infix, suffix] if p]
                name = "".join(parts)
                candidates.append(
                    NameCandidate(
                        name=name,
                        stems_used=[stem_match],
                        prefix=prefix,
                        infix=infix,
                        suffix=suffix,
                        generation_method="combinatorial",
                    )
                )
        return candidates

    @staticmethod
    def _phonological_score(name: str) -> float:
        """Score 0-1. Penalize awkward consonant/vowel patterns."""
        name_lower = name.lower()
        score = 1.0

        # Penalty: 3+ consecutive consonants
        consecutive_consonants = 0
        for ch in name_lower:
            if ch in CONSONANTS:
                consecutive_consonants += 1
                if consecutive_consonants >= 4:
                    score -= 0.15
                elif consecutive_consonants == 3:
                    score -= 0.08
            else:
                consecutive_consonants = 0

        # Penalty: 3+ consecutive vowels
        consecutive_vowels = 0
        for ch in name_lower:
            if ch in VOWELS:
                consecutive_vowels += 1
                if consecutive_vowels >= 3:
                    score -= 0.10
            else:
                consecutive_vowels = 0

        # Bonus: good consonant-vowel alternation
        alternations = sum(
            1 for i in range(len(name_lower) - 1)
            if (name_lower[i] in VOWELS) != (name_lower[i + 1] in VOWELS)
        )
        cv_ratio = alternations / max(len(name_lower) - 1, 1)
        score += 0.05 * cv_ratio

        # Bonus: common pharmaceutical endings sound natural
        good_endings = ["ib", "il", "ine", "ole", "ane", "ene", "ant", "ast", "icin", "mycin"]
        for ending in good_endings:
            if name_lower.endswith(ending):
                score += 0.05
                break

        return max(0.0, min(1.0, score))

    @staticmethod
    def _has_consecutive(name: str, char_set: frozenset[str], threshold: int) -> bool:
        count = 0
        for ch in name.lower():
            if ch in char_set:
                count += 1
                if count >= threshold:
                    return True
            else:
                count = 0
        return False

    @staticmethod
    def _passes_trigram_screen(name: str, existing_set: set[str]) -> bool:
        """Quick trigram screening — rejects only exact trigram matches."""
        name_lower = name.lower()
        if not existing_set:
            return True
        name_trigrams = {name_lower[i : i + 3] for i in range(len(name_lower) - 2)}
        for existing in existing_set:
            existing_trigrams = {existing[i : i + 3] for i in range(len(existing) - 2)}
            overlap = len(name_trigrams & existing_trigrams)
            if overlap >= len(name_trigrams) * 0.8:
                return False
        return True
