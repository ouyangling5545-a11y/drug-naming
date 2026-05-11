from __future__ import annotations
from ..models.poca import CompositionalScoreDetail


class CompositionalAnalyzer:
    """Compares drug names at the morphological level — stems, affixes, position."""

    def __init__(self, known_stems: list[str] | None = None) -> None:
        self.known_stems: set[str] = {s.lower().lstrip("-").rstrip("-") for s in (known_stems or [])}

    def set_stems(self, stems: list[str]) -> None:
        self.known_stems = {s.lower().lstrip("-").rstrip("-") for s in stems}

    def extract_stems(self, name: str) -> list[str]:
        name_lower = name.lower()
        found = []
        for stem in self.known_stems:
            if stem and stem in name_lower:
                found.append(stem)
        return sorted(found, key=len, reverse=True)

    def extract_affixes(self, name: str) -> list[str]:
        """Extract common pharmaceutical affixes from name."""
        common_affixes = [
            "ab", "ac", "ad", "af", "al", "am", "an", "ap", "ar", "as", "at", "ax", "az",
            "ba", "be", "bi", "bo", "bu",
            "ca", "ce", "ci", "co", "cu", "cy",
            "da", "de", "di", "do", "du",
            "el", "em", "en", "er", "es", "et", "ev", "ex",
            "fa", "fe", "fi", "fl", "fo", "fu",
            "ga", "ge", "gi", "gl", "go", "gr", "gu",
            "ic", "il", "im", "in", "io", "ir", "is", "it", "iv",
            "la", "le", "li", "lo", "lu", "ly",
            "ma", "me", "mi", "mo", "mu", "my",
            "na", "ne", "ni", "no", "nu", "ny",
            "ol", "om", "on", "op", "or", "os", "ot", "ov", "ox",
            "pa", "pe", "pi", "pl", "po", "pr", "pu",
            "ra", "re", "ri", "ro", "ru", "ry",
            "sa", "se", "si", "so", "sp", "st", "su", "sy",
            "ta", "te", "th", "ti", "to", "tr", "tu", "ty",
            "um", "un", "ur", "us", "ut",
            "va", "ve", "vi", "vo", "vu",
            "za", "ze", "zi", "zo", "zu",
        ]
        name_lower = name.lower()
        found = []
        for affix in common_affixes:
            if len(affix) >= 2 and affix in name_lower:
                found.append(affix)
        return found

    @staticmethod
    def syllable_breakdown(name: str) -> list[str]:
        """Split name into approximate syllables."""
        vowels = frozenset("aeiouy")
        name_lower = name.lower()
        syllables: list[str] = []
        current: list[str] = []
        prev_is_vowel = False
        for ch in name_lower:
            is_vowel = ch in vowels
            if is_vowel and not prev_is_vowel and current:
                syllables.append("".join(current))
                current = [ch]
            else:
                current.append(ch)
            prev_is_vowel = is_vowel
        if current:
            # Attach trailing consonants to last syllable
            if syllables and all(c not in vowels for c in current):
                syllables[-1] += "".join(current)
            else:
                syllables.append("".join(current))
        return syllables

    def compute_compositional(self, proposed: str, reference: str) -> tuple[CompositionalScoreDetail, float]:
        stems_prop = self.extract_stems(proposed)
        stems_ref = self.extract_stems(reference)
        shared_stems = [s for s in stems_prop if s in stems_ref]

        affixes_prop = self.extract_affixes(proposed)
        affixes_ref = self.extract_affixes(reference)
        shared_affixes = [a for a in affixes_prop if a in affixes_ref]

        # Stem overlap ratio
        all_stems = set(stems_prop) | set(stems_ref)
        stem_overlap = len(shared_stems) / max(len(all_stems), 1)

        # First/last three chars match
        first_three = proposed.lower()[:3] == reference.lower()[:3]
        last_three = proposed.lower()[-3:] == reference.lower()[-3:]

        # Positional score — first/last character matches weighted more
        p_lower = proposed.lower()
        r_lower = reference.lower()
        max_len = max(len(p_lower), len(r_lower), 1)
        positional_score = 0.0
        # First character match: 30% weight
        if p_lower[0] == r_lower[0]:
            positional_score += 0.30
        # Last character match: 20% weight
        if p_lower[-1] == r_lower[-1]:
            positional_score += 0.20
        # First 2 chars: 20% weight
        if len(p_lower) >= 2 and len(r_lower) >= 2 and p_lower[:2] == r_lower[:2]:
            positional_score += 0.20
        # Last 2 chars: 15% weight
        if len(p_lower) >= 2 and len(r_lower) >= 2 and p_lower[-2:] == r_lower[-2:]:
            positional_score += 0.15
        # Remaining middle match: 15% weight
        mid_prop = set(p_lower[1:-1]) if len(p_lower) > 2 else set()
        mid_ref = set(r_lower[1:-1]) if len(r_lower) > 2 else set()
        if mid_prop and mid_ref:
            mid_overlap = len(mid_prop & mid_ref) / max(len(mid_prop | mid_ref), 1)
            positional_score += 0.15 * mid_overlap

        # Shared syllable count
        syl_prop = self.syllable_breakdown(proposed)
        syl_ref = self.syllable_breakdown(reference)
        shared_syl = len(set(syl_prop) & set(syl_ref))
        total_syl_score = shared_syl / max(len(set(syl_prop) | set(syl_ref)), 1)

        # Aggregate compositional score (0–1)
        score = 0.0
        if stem_overlap > 0:
            score += 0.35 * stem_overlap
        if shared_affixes:
            score += 0.10 * min(1.0, len(shared_affixes) / max(len(set(affixes_prop) | set(affixes_ref)), 1))
        if first_three:
            score += 0.20
        if last_three:
            score += 0.15
        score += 0.15 * positional_score
        score += 0.05 * total_syl_score

        detail = CompositionalScoreDetail(
            shared_stems=shared_stems,
            shared_affixes=shared_affixes,
            stem_overlap_ratio=stem_overlap,
            first_three_chars_match=first_three,
            last_three_chars_match=last_three,
            positional_score=positional_score,
            shared_syllable_count=shared_syl,
            total_syllable_score=total_syl_score,
            compositional_score=min(1.0, score),
        )
        return detail, detail.compositional_score
