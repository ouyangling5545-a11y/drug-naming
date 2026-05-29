from __future__ import annotations
from ..models.molecule import PharmacologicalProperties
from ..models.stem import INNStem, StemMatch, StemPosition
from ..models.naming import (
    NameCandidate,
    NameGenerationConstraints,
    NameGenerationRequest,
    NameGenerationResponse,
)
from ..data.targets import find_target
from ..data.prefixes import (
    CORE_PREFIXES, SMALL_MOLECULE_PREFIXES,
    ANTIBODY_PREFIXES, ANTIBODY_PREFIXES_L1,
)
from ..engines.phonotactic import (
    count_syllables,
    has_invalid_consonant_cluster,
    bad_ending,
    boundary_cluster_valid,
)
from collections import OrderedDict

VOWELS = frozenset("aeiouy")
CONSONANTS = frozenset("bcdfghjklmnpqrstvwxz")

# ── Syllable-template prefix generation ───────────────────────────────────

def _generate_syllable_prefixes() -> dict[int, list[str]]:
    """Generate phonotactically valid prefixes using English syllable templates."""
    from ..engines.phonotactic import (
        VALID_ONSET_CLUSTERS, VALID_TRIPLE_ONSETS, VALID_CODA_CLUSTERS,
    )

    single_cons = sorted(CONSONANTS)
    vowels = sorted(VOWELS)
    onsets = sorted(VALID_ONSET_CLUSTERS)
    triples = sorted(VALID_TRIPLE_ONSETS)
    codas = sorted(VALID_CODA_CLUSTERS)
    single_codas = ['b', 'd', 'f', 'g', 'l', 'm', 'n', 'p', 'r', 's', 't', 'v', 'x', 'z']

    by_length: dict[int, list[str]] = {2: [], 3: [], 4: [], 5: [], 6: []}

    # 2-letter: C + V
    for c in single_cons:
        for v in vowels:
            by_length[2].append(c + v)

    # 3-letter: onset_cluster + V
    for cl in onsets:
        for v in vowels:
            by_length[3].append(cl + v)

    # 3-letter: C + V + coda
    for c in single_cons:
        for v in vowels:
            for cd in single_codas:
                if c != cd:
                    by_length[3].append(c + v + cd)

    # 4-letter: onset_cluster + V + coda
    for cl in onsets:
        for v in vowels:
            for cd in single_codas:
                by_length[4].append(cl + v + cd)

    # 4-letter: C + V + coda_cluster
    for c in single_cons:
        for v in vowels:
            for cc in codas:
                by_length[4].append(c + v + cc)

    # 5-letter: triple_onset + V
    for to in triples:
        for v in vowels:
            by_length[5].append(to + v)

    # 5-letter: onset_cluster + V + coda_cluster
    for cl in onsets:
        for v in vowels:
            for cc in codas:
                by_length[5].append(cl + v + cc)

    # 6-letter: triple_onset + V + coda
    for to in triples:
        for v in vowels:
            for cd in single_codas:
                by_length[6].append(to + v + cd)

    # Filter: remove double-start and triple-repeated letters
    for length in by_length:
        filtered = []
        for p in by_length[length]:
            if len(p) >= 2 and p[0] == p[1]:
                continue
            if any(p[i] == p[i + 1] == p[i + 2] for i in range(len(p) - 2)):
                continue
            filtered.append(p)
        by_length[length] = filtered

    return by_length


_SYLLABLE_PREFIXES: dict[int, list[str]] | None = None


def _get_syllable_prefixes() -> dict[int, list[str]]:
    """Lazily build and return the syllable-template prefix cache."""
    global _SYLLABLE_PREFIXES
    if _SYLLABLE_PREFIXES is None:
        _SYLLABLE_PREFIXES = _generate_syllable_prefixes()
    return _SYLLABLE_PREFIXES


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

        # Interleave by length: 4-char, 3-char, 2-char, 5-char, 6-char in rotation.
        # This ensures diverse prefix lengths get a chance instead of all short first.
        by_length: dict[int, list[str]] = {2: [], 3: [], 4: [], 5: [], 6: []}
        for p in raw_prefixes:
            if len(p) in by_length:
                by_length[len(p)].append(p)
        prefixes: list[str] = []
        max_group = max(len(by_length[2]), len(by_length[3]), len(by_length[4]),
                        len(by_length[5]), len(by_length[6]))
        for i in range(max_group):
            for length in (4, 3, 2, 5, 6):
                group = by_length[length]
                if i < len(group):
                    prefixes.append(group[i])

        # ── Build existing-prefix avoidance space ──────────────────────────
        # Look up all prefixes already used by drugs sharing the same stem(s)
        # so we can steer new candidates away from already-taken patterns.
        existing_prefixes: list[str] = []
        if self._inn_db is not None:
            for sm in request.matched_stems:
                stem_text = sm.stem.stem.strip("-")
                existing_prefixes.extend(self._inn_db.get_prefixes_for_stem(stem_text))
        prefix_space = self._analyze_prefix_space(existing_prefixes)

        all_candidates: list[NameCandidate] = []
        prefix_blacklist = set(p.lower() for p in constraints.prefix_blacklist)
        prefix_whitelist = set(p.lower() for p in constraints.prefix_whitelist) if constraints.prefix_whitelist else None
        allowed_lengths = set(constraints.prefix_lengths) if constraints.prefix_lengths else set()
        boundary_skips = 0

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
                # Avoidance: skip prefixes that exactly match an existing same-stem drug's prefix
                if existing_prefixes and prefix.lower() in prefix_space["full_set"]:
                    continue
                for infix, suffix in stem_combos:
                    # Use harmonizer: if prefix-suffix boundary is bad, auto-fix
                    # with bridging vowels instead of discarding the combination.
                    if suffix is not None:
                        pfx_variants = self._harmonize_prefix(prefix, suffix)
                    else:
                        pfx_variants = [prefix]

                    for pfx in pfx_variants:
                        if infix is None and suffix is not None:
                            # prefix is already harmonized — combine directly
                            parts = [p for p in [pfx, suffix] if p]
                        else:
                            parts = [p for p in [pfx, infix, suffix] if p]

                        # Check boundary between adjacent parts
                        if any(
                            not boundary_cluster_valid(parts[i], parts[i + 1])
                            for i in range(len(parts) - 1)
                        ):
                            boundary_skips += 1
                            continue

                        name = "".join(parts)
                        # Detect if prefix was bridged (infix is a single vowel)
                        actual_infix = infix
                        if infix is None and pfx != prefix:
                            actual_infix = pfx[len(prefix):]

                        all_candidates.append(NameCandidate(
                            name=name,
                            stems_used=[sm],
                            prefix=prefix,
                            infix=actual_infix if actual_infix else infix,
                            suffix=suffix,
                            generation_method="structured",
                        ))

        total_generated = len(all_candidates)

        # Composite scoring (phonological + Chinese + WHO letter + length + avoidance)
        for c in all_candidates:
            avoidance = self._avoidance_score(c.prefix or "", prefix_space) if existing_prefixes else 0.0
            c.phonological_score = self._composite_score(c.name, c.prefix, avoidance)

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

        # Sort by phonological score, then apply diversity-aware cap:
        # reserve slots for each prefix length (2,3,4,5,6) so short prefixes
        # aren't drowned out by the larger volume of longer ones.
        filtered.sort(key=lambda c: c.phonological_score, reverse=True)
        total_cap = constraints.max_candidates_per_stem * len(request.matched_stems)
        per_length_quota = max(total_cap // 6, 8)

        by_length: dict[int, list[NameCandidate]] = {2: [], 3: [], 4: [], 5: [], 6: []}
        for c in filtered:
            pl = len(c.prefix or "")
            if pl in by_length:
                by_length[pl].append(c)

        # Each group is already sorted (inherited from filtered sort)
        seen: set[str] = set()
        unique: list[NameCandidate] = []
        for pl in (2, 3, 4, 5, 6):
            taken = 0
            for c in by_length[pl]:
                if c.name.lower() not in seen and taken < per_length_quota:
                    seen.add(c.name.lower())
                    unique.append(c)
                    taken += 1

        # Fill remaining slots with best remaining candidates (any length)
        for c in filtered:
            if len(unique) >= total_cap:
                break
            if c.name.lower() not in seen:
                seen.add(c.name.lower())
                unique.append(c)

        if boundary_skips:
            flag_counts["boundary_cluster_invalid"] = boundary_skips

        pipeline_rejected = sum(flag_counts.values())

        return NameGenerationResponse(
            candidates=unique,
            total_generated=total_generated,
            filtered_out=pipeline_rejected,
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
        """Generate prefixes derived from target name and indication.

        Kept minimal and meaningful — Variant 1 (direct target root) and
        Variant 4 (indication keywords) only.  Consonant substitution and
        vowel mutation removed because they produce near-duplicate prefixes
        that trigger mass POCA conflicts (e.g. eg→bg,dg,fg,lg,mg,ng...).
        """
        prefixes = []

        # Variant 1: Target root direct (e.g., egfr → eg, egr, egfr)
        if len(target_root) >= 2:
            prefixes.append(target_root[:2])
            if len(target_root) >= 3:
                prefixes.append(target_root[:3])
            if len(target_root) >= 4:
                prefixes.append(target_root[:4])

        # Variant 2: From indication keywords
        if properties.indication:
            ind_words = properties.indication.replace('（', ' ').replace('）', ' ').replace('/', ' ').split()
            for w in ind_words:
                w_alpha = "".join(c for c in w if c.isalpha()).lower()
                w_alpha = _who_normalize(w_alpha)
                if len(w_alpha) >= 3:
                    prefixes.append(w_alpha[:2])
                    prefixes.append(w_alpha[:3])

        # Variant 3: From scaffold
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

    # ═══ Existing-prefix avoidance analysis ═══════════════════════════════════

    @staticmethod
    def _analyze_prefix_space(existing_prefixes: list[str]) -> dict:
        """Build a compact lookup of which prefix patterns are already taken.

        Returns a dict with:
          - starts:    set of single starting letters in use
          - starts2:   set of starting 2-char sequences in use
          - starts3:   set of starting 3-char sequences in use
          - full_set:  set of all exact existing prefixes (lowercased)
        """
        start1: set[str] = set()
        start2: set[str] = set()
        start3: set[str] = set()
        full: set[str] = set()

        for pfx in existing_prefixes:
            p = pfx.lower()
            full.add(p)
            if len(p) >= 1:
                start1.add(p[0])
            if len(p) >= 2:
                start2.add(p[:2])
            if len(p) >= 3:
                start3.add(p[:3])

        return {"starts": start1, "starts2": start2, "starts3": start3, "full_set": full}

    @staticmethod
    def _avoidance_score(prefix: str, space: dict) -> float:
        """Score a candidate prefix by how different it is from existing ones.

        Returns 0.0 (best — explores new territory) to 1.0 (worst — too close).
        Lower is better.
        """
        p = prefix.lower()
        score = 0.0

        # Exact match to existing prefix → strongest penalty
        if p in space["full_set"]:
            score += 1.0

        # Same first 3 characters → strong penalty (confusingly similar)
        if len(p) >= 3 and p[:3] in space["starts3"]:
            score += 0.6

        # Same first 2 characters → moderate penalty
        if len(p) >= 2 and p[:2] in space["starts2"]:
            score += 0.3

        # Same first character → light penalty (crowded letter)
        if len(p) >= 1 and p[:1] in space["starts"]:
            score += 0.1

        return min(score, 1.0)

    @staticmethod
    def _base_prefix_pool(cc: str) -> list[str]:
        """Return the appropriate base prefix pool for the chemical class.

        Small molecules now use CORE_PREFIXES (54 single-syllable) +
        SMALL_MOLECULE_PREFIXES (40+ two-letter) as the primary pool,
        ordered by length (4→3→2) for diversity.

        Antibodies keep the merged L1 (453 real WHO prefixes) + core
        (55 single-syllable).
        """
        if cc in ('monoclonal_antibody', 'antibody_fragment', 'bispecific_antibody', 'antibody_drug_conjugate'):
            merged = list(OrderedDict.fromkeys(ANTIBODY_PREFIXES_L1 + ANTIBODY_PREFIXES))
            return merged

        # Small molecules: CORE_PREFIXES + SMALL_MOLECULE_PREFIXES as primary,
        # plus a small sample of longer syllable-template prefixes for length diversity.
        merged = list(OrderedDict.fromkeys(CORE_PREFIXES + SMALL_MOLECULE_PREFIXES))
        # Sample ~12 per length from syllable templates (3,4,5,6) as fallback
        sp = _get_syllable_prefixes()
        for length in (3, 4, 5, 6):
            samples = sp.get(length, [])
            # Take evenly spaced samples for diversity
            step = max(1, len(samples) // 15)
            merged.extend(samples[::step][:15])
        # Sort by length descending so longer prefixes participate in interleave
        merged.sort(key=lambda x: -len(x))
        return merged

    @staticmethod
    def _harmonize_prefix(prefix: str, suffix: str) -> list[str]:
        """Return boundary-safe variants of a prefix for a given suffix.

        When the prefix-suffix boundary forms an invalid consonant cluster
        (e.g. cd + kitug → "cdk"), inject bridging vowels to create valid
        English phonotactic transitions.  Returns the original prefix if no
        fix is needed.
        """
        if boundary_cluster_valid(prefix, suffix):
            return [prefix]

        variants: list[str] = []
        for vowel in ["a", "e", "i", "o"]:
            variant = prefix + vowel
            if boundary_cluster_valid(variant, suffix):
                variants.append(variant)
        # Also try with the prefix stripped of its trailing consonant
        if prefix and prefix[-1] in CONSONANTS:
            stripped = prefix[:-1]
            if len(stripped) >= 1 and boundary_cluster_valid(stripped, suffix):
                variants.append(stripped)
        return variants if variants else [prefix]

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
        """Score 0-1 with meaningful spread.

        Starts at a baseline (0.55), then applies graded penalties and bonuses
        so that euphonious names score 0.75-0.95 and awkward ones 0.30-0.55.
        """
        name_lower = name.lower()
        score = 0.55

        # Penalty: 3+ consecutive consonants (count each occurrence)
        consecutive_consonants = 0
        for ch in name_lower:
            if ch in CONSONANTS:
                consecutive_consonants += 1
                if consecutive_consonants == 3:
                    score -= 0.10
                elif consecutive_consonants >= 4:
                    score -= 0.20
            else:
                consecutive_consonants = 0

        # Penalty: 3+ consecutive vowels
        consecutive_vowels = 0
        for ch in name_lower:
            if ch in VOWELS:
                consecutive_vowels += 1
                if consecutive_vowels >= 3:
                    score -= 0.12
            else:
                consecutive_vowels = 0

        # Bonus: good consonant-vowel alternation (higher weight)
        alternations = sum(
            1 for i in range(len(name_lower) - 1)
            if (name_lower[i] in VOWELS) != (name_lower[i + 1] in VOWELS)
        )
        cv_ratio = alternations / max(len(name_lower) - 1, 1)
        score += 0.18 * cv_ratio

        # Bonus: valid English onset cluster at name start — natural and distinctive.
        # Use elif to prevent double-dipping: a triple onset (e.g. "squ") already
        # contains a valid 2-char onset ("sq"), so only the larger bonus applies.
        from ..engines.phonotactic import VALID_ONSET_CLUSTERS, VALID_TRIPLE_ONSETS
        if len(name_lower) >= 4 and name_lower[:3] in VALID_TRIPLE_ONSETS:
            score += 0.04
        elif len(name_lower) >= 3 and name_lower[:2] in VALID_ONSET_CLUSTERS:
            score += 0.03

        # Syllable count: optimal 3-5 (most INN drug names)
        syl = count_syllables(name_lower)
        if 3 <= syl <= 5:
            score += 0.06
        elif syl < 2:
            score -= 0.08
        elif syl > 6:
            score -= 0.05

        # Bonus: common pharmaceutical endings
        good_endings = ["ib", "il", "ine", "ole", "ane", "ene", "ant", "ast",
                        "icin", "mycin", "tinib", "mab", "dipine", "sartan",
                        "grel", "previr", "xaban", "lukast", "gliptin", "gliflozin"]
        for ending in good_endings:
            if name_lower.endswith(ending):
                score += 0.10
                break

        # Penalty: awkward non-pharmaceutical endings
        if bad_ending(name_lower):
            score -= 0.15

        return max(0.0, min(1.0, score))

    @staticmethod
    def _chinese_transliterability(prefix: str) -> float:
        """Pre-check how well a prefix can be transliterated into Chinese.

        Returns 0.0-1.0 where 1.0 means every syllable in the prefix has
        at least one good Chinese character mapping in SYLLABLE_TO_CHAR.
        """
        from ..engines.chinese_transliteration import SYLLABLE_TO_CHAR
        if not prefix:
            return 0.0

        pfx = prefix.lower()
        # Greedy syllable split (same as transliteration engine)
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
                pos += 1  # skip unmapped char

        if not syllables:
            return 0.5  # can't parse → neutral

        mapped = sum(1 for syl in syllables
                     if any(s == syl for s, ch in SYLLABLE_TO_CHAR))
        return mapped / len(syllables)

    @staticmethod
    def _who_letter_score(name: str) -> float:
        """Score prefix/name by WHO-preferred letter distribution.

        WHO recommends: b, c, d, g, p, t, v, z for drug names.
        Avoids: h, j, k, w, y (Rule 7).
        Returns 0.0-1.0 bonus.
        """
        preferred = frozenset("bcdgptvz")
        avoided = frozenset("hjkw")
        s = name.lower()
        if not s:
            return 0.0
        pref_ratio = sum(1 for ch in s if ch in preferred) / len(s)
        avoid_ratio = sum(1 for ch in s if ch in avoided) / len(s)
        return max(0.0, min(1.0, 0.5 + pref_ratio * 0.4 - avoid_ratio * 0.3))

    def _composite_score(self, name: str, prefix: str | None, avoidance: float = 0.0) -> float:
        """Multi-dimensional composite score for candidate ranking.

        Combines:
          - phonological quality     (0.35) — CVCV rhythm, syllable count, endings
          - Chinese transliterability (0.25) — how well prefix maps to Chinese
          - WHO letter preference    (0.10) — preferred/avoided letters
          - length bonus             (0.10) — 7-12 chars ideal
          - avoidance               (0.20) — distance from existing same-stem prefixes
        """
        phono = self._phonological_score(name)
        chinese = self._chinese_transliterability(prefix or name)
        who = self._who_letter_score(prefix or name)

        # Length bonus: 7-12 chars ideal (most WHO-approved names)
        nlen = len(name)
        if 7 <= nlen <= 12:
            length_bonus = 1.0
        elif 5 <= nlen <= 6:
            length_bonus = 0.7
        elif 13 <= nlen <= 15:
            length_bonus = 0.6
        else:
            length_bonus = 0.3

        # Avoidance bonus: 1.0 = completely novel prefix, 0.0 = exact match
        avoidance_bonus = 1.0 - avoidance

        return (
            0.35 * phono
            + 0.25 * chinese
            + 0.10 * who
            + 0.10 * length_bonus
            + 0.20 * avoidance_bonus
        )

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

    _trigram_index: dict[str, set[str]] | None = None  # cached index over INN DB names

    @classmethod
    def _get_trigram_index(cls, names: frozenset[str] | set[str]) -> dict[str, set[str]]:
        """Build a trigram→names index. Cached on first call (INN DB is static)."""
        if cls._trigram_index is not None:
            return cls._trigram_index
        idx: dict[str, set[str]] = {}
        for name in names:
            for i in range(len(name) - 2):
                t = name[i:i + 3]
                idx.setdefault(t, set()).add(name)
        cls._trigram_index = idx
        return idx

    @classmethod
    def _passes_trigram_screen(cls, name: str, existing_set: frozenset[str] | set[str], threshold: float = 0.75) -> bool:
        """Reject names whose trigram overlap with existing INN names exceeds threshold.

        Uses a cached trigram index over the INN DB for fast lookup (O(candidate_trigrams)
        instead of O(existing_names)). User-provided names are checked directly since
        they are typically few.
        """
        name_lower = name.lower()
        if not existing_set:
            return True
        name_trigrams = {name_lower[i: i + 3] for i in range(len(name_lower) - 2)}
        if not name_trigrams:
            return True
        limit = len(name_trigrams) * threshold

        idx = cls._get_trigram_index(existing_set)
        overlap_counter: dict[str, int] = {}
        for t in name_trigrams:
            for ref in idx.get(t, ()):
                overlap_counter[ref] = overlap_counter.get(ref, 0) + 1
                if overlap_counter[ref] >= limit:
                    return False
        return True
