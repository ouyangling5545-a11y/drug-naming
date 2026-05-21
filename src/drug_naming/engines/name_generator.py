from __future__ import annotations
from ..models.molecule import ChemicalClass, PharmacologicalProperties
from ..models.stem import INNStem, StemMatch, StemPosition
from ..models.naming import (
    NameCandidate,
    NameGenerationConstraints,
    NameGenerationRequest,
    NameGenerationResponse,
)
from ..data.targets import find_target
from collections import OrderedDict


# ── Euphonious prefix pools by chemical class ──
CORE_PREFIXES: list[str] = [
    "a", "be", "ce", "da", "e", "fa", "ga", "ha", "i", "jo", "ka",
    "la", "le", "li", "lo", "lu", "ma", "me", "mi", "mo", "mu",
    "na", "ne", "ni", "no", "nu", "o", "pa", "pe", "pi", "po",
    "ra", "re", "ri", "ro", "ru",
    "sa", "se", "si", "so", "su",
    "ta", "te", "ti", "to", "tu",
    "va", "ve", "vi", "vo", "vu",
    "za", "ze", "zi", "zo", "zu",
]

SMALL_MOLECULE_PREFIXES: list[str] = [
    "ab", "ac", "af", "al", "am", "an", "ap", "ar", "as", "at", "ax", "az",
    "ba", "be", "bi", "bo", "br", "bu",
    "ca", "ce", "ci", "co", "cr", "cu",
    "da", "de", "di", "do", "dr", "du",
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
]

ANTIBODY_PREFIXES: list[str] = [
    "a", "ba", "be", "bi", "bo", "ca", "ce", "ci", "co", "cu", "da", "de", "di", "do",
    "e", "fa", "fe", "ga", "go", "gu", "ha", "he", "i", "ja", "je", "ka", "ki",
    "la", "le", "li", "lo", "lu", "ma", "me", "mi", "mo", "mu",
    "na", "ne", "ni", "no", "nu", "o", "pa", "pe", "pi", "po",
    "ra", "re", "ri", "ro", "ru",
    "sa", "se", "si", "so", "su",
    "ta", "te", "ti", "to", "tu",
    "va", "ve", "vi", "vo", "vu",
    "za", "ze", "zi", "zo", "zu",
]

VOWELS = frozenset("aeiouy")
CONSONANTS = frozenset("bcdfghjklmnpqrstvwxz")


class NameGenerationEngine:
    """Structured INN name generation following WHO conventions.

    Uses a target-aware approach: derives prefix from target name, indication,
    or substructure; infix from mechanism subtype; suffix from matched stems.
    """

    def __init__(self, inn_reference_db=None) -> None:
        self._inn_db = inn_reference_db

    def generate(self, request: NameGenerationRequest) -> NameGenerationResponse:
        constraints = request.constraints
        properties = request.properties
        existing_set = set(n.lower() for n in request.existing_names_to_avoid)

        tc = getattr(properties.target_class, 'value', properties.target_class)
        mc = getattr(properties.mechanism, 'value', properties.mechanism)
        cc = getattr(properties.chemical_class, 'value', properties.chemical_class)

        target_meta = find_target(tc)
        target_root = self._target_root(tc, target_meta)

        # Build prefix pool: target-derived first, then euphonious
        target_prefixes = self._target_prefixes(target_root, mc, cc, properties, target_meta)
        base_prefixes = self._base_prefix_pool(cc)
        prefixes = list(OrderedDict.fromkeys(target_prefixes + base_prefixes))

        all_candidates: list[NameCandidate] = []

        for sm in request.matched_stems:
            stem_combos = self._build_stem_combos(sm)
            for prefix in prefixes[:80]:  # cap prefixes per stem for performance
                for infix, suffix in stem_combos:
                    parts = [p for p in [prefix, infix, suffix] if p]
                    name = "".join(parts)
                    all_candidates.append(NameCandidate(
                        name=name,
                        stems_used=[sm],
                        prefix=prefix,
                        infix=infix,
                        suffix=suffix,
                        generation_method="structured",
                    ))

        total_generated = len(all_candidates)

        # Phonological scoring
        for c in all_candidates:
            c.phonological_score = self._phonological_score(c.name)

        # Merge with INN reference db
        if self._inn_db is not None:
            existing_set = existing_set | self._inn_db.english_names

        # Filter pipeline
        filtered: list[NameCandidate] = []
        for c in all_candidates:
            name_lower = c.name.lower()
            if name_lower in existing_set:
                c.regulatory_flags.append("exact_inn_conflict")
                continue
            if not self._passes_trigram_screen(name_lower, existing_set):
                c.regulatory_flags.append("trigram_match_with_existing")
                continue
            if any(name_lower.startswith(p) for p in constraints.forbidden_prefixes):
                c.regulatory_flags.append("contains_forbidden_prefix")
                continue
            if any(name_lower.endswith(s) for s in constraints.forbidden_suffixes):
                c.regulatory_flags.append("contains_forbidden_suffix")
                continue
            if not (constraints.min_name_length <= len(c.name) <= constraints.max_name_length):
                continue
            if self._has_consecutive(name_lower, CONSONANTS, constraints.max_consecutive_consonants + 1):
                c.regulatory_flags.append("too_many_consecutive_consonants")
                continue
            if self._has_consecutive(name_lower, VOWELS, constraints.max_consecutive_vowels + 1):
                c.regulatory_flags.append("too_many_consecutive_vowels")
                continue
            filtered.append(c)

        # Sort: phonological score, deduplicate, cap
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

    # ── Target-aware prefix derivation ─────────────────────────────────────

    @staticmethod
    def _target_root(tc: str, target_meta) -> str:
        """Extract a short alphabetic root from the target name."""
        if target_meta:
            label = target_meta.label.lower()
        else:
            label = tc.lower()
        # Remove non-alpha characters and common suffixes
        label = "".join(c for c in label if c.isalpha())
        # Take first 2-4 characters as root
        if len(label) >= 4:
            return label[:4]
        return label[:max(2, len(label))]

    @staticmethod
    def _target_prefixes(
        target_root: str,
        mc: str,
        cc: str,
        properties: PharmacologicalProperties,
        target_meta,
    ) -> list[str]:
        """Generate prefixes derived from the target, mechanism, or indication."""
        prefixes = []

        # Variant 1: Target root direct (e.g., egfr → eg, ef)
        if len(target_root) >= 2:
            prefixes.append(target_root[:2])
            if len(target_root) >= 3:
                prefixes.append(target_root[:3])
            if len(target_root) >= 4:
                prefixes.append(target_root[:4])

        # Variant 2: Target root with vowel mutation (eg → ig, ag, og)
        if len(target_root) >= 2:
            first_char = target_root[0]
            for v in ['a', 'e', 'i', 'o', 'u']:
                variant = v + target_root[1:min(3, len(target_root))]
                if variant != target_root[:len(variant)]:
                    prefixes.append(variant)

        # Variant 3: Target root substitution at position 1 (swap consonant)
        if len(target_root) >= 2 and target_root[0] in CONSONANTS:
            for c in ['b', 'd', 'f', 'g', 'l', 'm', 'n', 'p', 'r', 's', 't', 'v', 'z']:
                variant = c + target_root[1:min(3, len(target_root))]
                if variant != target_root[:len(variant)]:
                    prefixes.append(variant)

        # Variant 4: From indication keywords
        if properties.indication:
            ind_words = properties.indication.replace('（', ' ').replace('）', ' ').replace('/', ' ').split()
            for w in ind_words:
                w_alpha = "".join(c for c in w if c.isalpha()).lower()
                if len(w_alpha) >= 3:
                    prefixes.append(w_alpha[:2])
                    prefixes.append(w_alpha[:3])

        # Variant 5: From scaffold
        if properties.chemical_scaffold:
            sub = "".join(c for c in properties.chemical_scaffold.lower() if c.isalpha())
            if len(sub) >= 2:
                prefixes.insert(0, sub[:2])
                if len(sub) >= 3:
                    prefixes.insert(0, sub[:3])

        # Deduplicate keeping order, filter invalid
        seen = set()
        result = []
        for p in prefixes:
            if p and p not in seen and len(p) >= 2 and p[0] in CONSONANTS | VOWELS:
                seen.add(p)
                result.append(p)
        return result

    @staticmethod
    def _base_prefix_pool(cc: str) -> list[str]:
        """Return the appropriate base prefix pool for the chemical class."""
        if cc in ('monoclonal_antibody', 'antibody_fragment', 'bispecific_antibody', 'antibody_drug_conjugate'):
            return ANTIBODY_PREFIXES
        return SMALL_MOLECULE_PREFIXES

    # ── Stem combo building ─────────────────────────────────────────────────

    def _build_stem_combos(self, sm: StemMatch) -> list[tuple[str | None, str | None]]:
        """Build (infix, suffix) combos for a single stem match."""
        stem = sm.stem
        stem_text = stem.stem.strip("-")
        results: list[tuple[str | None, str | None]] = []

        if stem.position == StemPosition.SUFFIX:
            if stem.infix_required and stem.allowed_infixes:
                for infix in stem.allowed_infixes:
                    results.append((infix.strip("-"), stem_text))
            elif stem.infix_required:
                # Infix required but none listed — use a euphonious infix
                for infix in self._euphonious_infixes():
                    results.append((infix, stem_text))
            else:
                results.append((None, stem_text))

        elif stem.position == StemPosition.PREFIX:
            if stem.allowed_infixes:
                for infix in stem.allowed_infixes:
                    # For prefix stems, name = stem + infix + (no suffix)
                    results.append((infix.strip("-") if infix else None, None))
            else:
                results.append((None, None))

        elif stem.position == StemPosition.INFIX:
            results.append((stem_text, None))

        return results

    @staticmethod
    def _euphonious_infixes() -> list[str]:
        """Generate euphonious 1-2 syllable infixes."""
        return ["a", "i", "o", "e", "a", "i", "o",
                "ba", "bi", "da", "fa", "ga", "la", "li", "ma", "mi",
                "na", "pa", "ra", "ri", "sa", "si", "ta", "ti", "va", "vi",
                "clo", "flo", "glo", "pro", "tro"]

    # ── Phonological scoring ───────────────────────────────────────────────

    @staticmethod
    def _phonological_score(name: str) -> float:
        """Score 0-1. Penalizes awkward patterns, rewards pharmaceutical euphony."""
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

        # Bonus: common pharmaceutical endings
        good_endings = ["ib", "il", "ine", "ole", "ane", "ene", "ant", "ast", "icin", "mycin", "tinib", "mab", "dipine", "sartan", "grel", "previr", "xaban", "lukast", "gliptin", "gliflozin"]
        for ending in good_endings:
            if name_lower.endswith(ending):
                score += 0.08
                break

        return max(0.0, min(1.0, score))

    # ── Validation helpers ──────────────────────────────────────────────────

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
        """Reject names whose trigram overlap with existing INN names is ≥80%."""
        name_lower = name.lower()
        if not existing_set:
            return True
        name_trigrams = {name_lower[i: i + 3] for i in range(len(name_lower) - 2)}
        if not name_trigrams:
            return True
        for existing in existing_set:
            existing_trigrams = {existing[i: i + 3] for i in range(len(existing) - 2)}
            overlap = len(name_trigrams & existing_trigrams)
            if overlap >= len(name_trigrams) * 0.8:
                return False
        return True
