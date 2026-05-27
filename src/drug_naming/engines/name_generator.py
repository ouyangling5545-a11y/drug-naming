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
from ..data.prefixes import CORE_PREFIXES, SMALL_MOLECULE_PREFIXES, ANTIBODY_PREFIXES
from ..engines.phonotactic import (
    count_syllables,
    has_invalid_consonant_cluster,
    bad_ending,
    boundary_cluster_valid,
)
from collections import OrderedDict

VOWELS = frozenset("aeiouy")
CONSONANTS = frozenset("bcdfghjklmnpqrstvwxz")

# WHO Rule 7: ph→f, th→t, y→i, avoid h/k
_WHO_NORMALIZE = str.maketrans("", "", "hk")  # strip h/k entirely
_WHO_REPLACE = str.maketrans({"y": "i"})  # y→i after stripping h/k
# ph→f and th→t are string-level replacements applied separately


def _who_normalize(s: str) -> str:
    """Apply WHO Rule 7 phonetic normalization to a prefix candidate."""
    s = s.replace("ph", "f").replace("th", "t")
    s = s.translate(_WHO_NORMALIZE)  # strip remaining h, k
    s = s.translate(_WHO_REPLACE)   # y → i
    return s


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
        raw_prefixes = list(OrderedDict.fromkeys(target_prefixes + base_prefixes))

        # Interleave by length: 4-char, 3-char, 2-char, 4-char, 3-char, ...
        # This ensures long+short prefixes both get a chance instead of all 2-char first.
        by_length: dict[int, list[str]] = {2: [], 3: [], 4: []}
        for p in raw_prefixes:
            if len(p) in by_length:
                by_length[len(p)].append(p)
        prefixes: list[str] = []
        max_group = max(len(by_length[2]), len(by_length[3]), len(by_length[4]))
        for i in range(max_group):
            for length in (4, 3, 2):
                group = by_length[length]
                if i < len(group):
                    prefixes.append(group[i])

        all_candidates: list[NameCandidate] = []
        prefix_blacklist = set(p.lower() for p in constraints.prefix_blacklist)
        prefix_whitelist = set(p.lower() for p in constraints.prefix_whitelist) if constraints.prefix_whitelist else None
        allowed_lengths = set(constraints.prefix_lengths) if constraints.prefix_lengths else set()

        # If whitelist is set, inject its entries at the front of the prefix pool
        # so Chinese reverse-lookup prefixes participate even if novel.
        if prefix_whitelist:
            prefixes = list(OrderedDict.fromkeys(
                [p for p in prefix_whitelist if len(p) >= 2] + prefixes
            ))

        for sm in request.matched_stems:
            stem_combos = self._build_stem_combos(sm)
            for prefix in prefixes:  # no cap — full pool participates
                if prefix.lower() in prefix_blacklist:
                    continue
                if prefix_whitelist and prefix.lower() not in prefix_whitelist:
                    continue
                if allowed_lengths and len(prefix) not in allowed_lengths:
                    continue
                # WHO Rule 7: avoid h and k in prefixes
                if "h" in prefix.lower() or "k" in prefix.lower():
                    continue
                for infix, suffix in stem_combos:
                    # If no infix and prefix→suffix boundary is bad, try bridging vowels
                    if infix is None and suffix is not None and not boundary_cluster_valid(prefix, suffix):
                        bridged = False
                        for bridge in ["i", "o", "a", "e"]:
                            if boundary_cluster_valid(prefix, bridge) and boundary_cluster_valid(bridge, suffix):
                                parts = [p for p in [prefix, bridge, suffix] if p]
                                name = "".join(parts)
                                all_candidates.append(NameCandidate(
                                    name=name,
                                    stems_used=[sm],
                                    prefix=prefix,
                                    infix=bridge,
                                    suffix=suffix,
                                    generation_method="structured",
                                ))
                                bridged = True
                        if bridged:
                            continue
                        # No bridge works — skip this combination
                        continue

                    parts = [p for p in [prefix, infix, suffix] if p]
                    # Check boundary consonant clusters between adjacent parts
                    if any(
                        not boundary_cluster_valid(parts[i], parts[i + 1])
                        for i in range(len(parts) - 1)
                    ):
                        continue
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
        trigram_threshold = getattr(constraints, 'trigram_overlap_threshold', 0.75)
        filtered: list[NameCandidate] = []
        flag_counts: dict[str, int] = {}
        for c in all_candidates:
            name_lower = c.name.lower()
            # Exact INN conflict — ALWAYS reject, even in relaxed mode
            if name_lower in existing_set:
                c.regulatory_flags.append("exact_inn_conflict")
                flag_counts["exact_inn_conflict"] = flag_counts.get("exact_inn_conflict", 0) + 1
                continue
            # Trigram screening: relaxed mode uses a wider threshold (1.0 = off),
            # strict mode uses the configured threshold (default 0.75).
            effective_trigram = 1.0 if request.relaxed else trigram_threshold
            if effective_trigram < 1.0 and not self._passes_trigram_screen(name_lower, existing_set, effective_trigram):
                c.regulatory_flags.append("trigram_match_with_existing")
                flag_counts["trigram_match_with_existing"] = flag_counts.get("trigram_match_with_existing", 0) + 1
                continue
            if has_invalid_consonant_cluster(name_lower):
                c.regulatory_flags.append("invalid_consonant_cluster")
                flag_counts["invalid_consonant_cluster"] = flag_counts.get("invalid_consonant_cluster", 0) + 1
                continue
            if any(name_lower.startswith(p) for p in constraints.forbidden_prefixes):
                c.regulatory_flags.append("contains_forbidden_prefix")
                flag_counts["contains_forbidden_prefix"] = flag_counts.get("contains_forbidden_prefix", 0) + 1
                continue
            if any(name_lower.endswith(s) for s in constraints.forbidden_suffixes):
                c.regulatory_flags.append("contains_forbidden_suffix")
                flag_counts["contains_forbidden_suffix"] = flag_counts.get("contains_forbidden_suffix", 0) + 1
                continue
            if not (constraints.min_name_length <= len(c.name) <= constraints.max_name_length):
                flag_counts["bad_length"] = flag_counts.get("bad_length", 0) + 1
                continue
            if self._has_consecutive(name_lower, CONSONANTS, constraints.max_consecutive_consonants + 1):
                c.regulatory_flags.append("too_many_consecutive_consonants")
                flag_counts["too_many_consecutive_consonants"] = flag_counts.get("too_many_consecutive_consonants", 0) + 1
                continue
            if self._has_consecutive(name_lower, VOWELS, constraints.max_consecutive_vowels + 1):
                c.regulatory_flags.append("too_many_consecutive_vowels")
                flag_counts["too_many_consecutive_vowels"] = flag_counts.get("too_many_consecutive_vowels", 0) + 1
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
            flag_counts=flag_counts,
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
        # WHO Rule 7: ph→f, th→t, strip h/k, y→i
        label = _who_normalize(label)
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
                w_alpha = _who_normalize(w_alpha)
                if len(w_alpha) >= 3:
                    prefixes.append(w_alpha[:2])
                    prefixes.append(w_alpha[:3])

        # Variant 5: From scaffold
        if properties.chemical_scaffold:
            sub = "".join(c for c in properties.chemical_scaffold.lower() if c.isalpha())
            sub = _who_normalize(sub)
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
        base = CORE_PREFIXES + SMALL_MOLECULE_PREFIXES
        # Generate 3-4 char euphonious prefixes ending in vowels for variety
        longer = []
        for p in base:
            if len(p) == 2 and p[-1] not in VOWELS:
                longer.append(p + "a")
                longer.append(p + "i")
                longer.append(p + "o")
            elif len(p) == 2:
                longer.append(p + "la")
                longer.append(p + "ra")
                longer.append(p + "na")
        return base + longer

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

        # Syllable count: optimal 3-5 (most INN drug names)
        syl = count_syllables(name_lower)
        if 3 <= syl <= 5:
            score += 0.04
        elif syl < 2:
            score -= 0.06
        elif syl > 6:
            score -= 0.03

        # Bonus: common pharmaceutical endings
        good_endings = ["ib", "il", "ine", "ole", "ane", "ene", "ant", "ast", "icin", "mycin", "tinib", "mab", "dipine", "sartan", "grel", "previr", "xaban", "lukast", "gliptin", "gliflozin"]
        for ending in good_endings:
            if name_lower.endswith(ending):
                score += 0.08
                break

        # Penalty: awkward non-pharmaceutical endings
        if bad_ending(name_lower):
            score -= 0.10

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
    def _passes_trigram_screen(name: str, existing_set: set[str], threshold: float = 0.75) -> bool:
        """Reject names whose trigram overlap with existing INN names exceeds threshold."""
        name_lower = name.lower()
        if not existing_set:
            return True
        name_trigrams = {name_lower[i: i + 3] for i in range(len(name_lower) - 2)}
        if not name_trigrams:
            return True
        limit = len(name_trigrams) * threshold
        for existing in existing_set:
            existing_trigrams = {existing[i: i + 3] for i in range(len(existing) - 2)}
            overlap = len(name_trigrams & existing_trigrams)
            if overlap >= limit:
                return False
        return True
