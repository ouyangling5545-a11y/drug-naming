from __future__ import annotations
import jellyfish
from ..models.poca import PhoneticScoreDetail


def _levenshtein(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(curr[-1] + 1, prev[j + 1] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


def _lcs(s1: str, s2: str) -> int:
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n]


class PhoneticEncoder:
    """Phoneme-driven auditory similarity scoring using Double Metaphone.

    Unlike FDA POCA's "Phonetic" (which reuses the same LCS+NED string features
    as Ortho with different weights), this engine measures how names actually
    sound to a human listener:

        Primary Metaphone (30%):
            Exact match → 1.0, near-match squashed (×1.5 penalty on edit distance).
            Captures the dominant English pronunciation — "phone" and "fone"
            both map to "FN" and score high, while "imatinib" (AMTN) and
            "erlotinib" (ARLT) diverge on the prefix → 0.

        Secondary Metaphone (10%):
            Alternative pronunciation variant, same squashing logic.

        Syllable count (15%):
            Same count = 1.0, off by 1 = 0.5, off by 2+ = 0.0.

        Stress pattern (10%):
            Intonation contour similarity between syllable sequences.

        NED baseline (35%):
            Normalized Edit Distance — residual string similarity to capture
            suffix rhyme effects that Metaphone may miss across prefix boundaries
            (e.g. -tinib, -caine, -afil shared suffixes).

    Score is scaled to 0-100 and divided by 100 for the 0-1 float interface.
    """

    @staticmethod
    def soundex(name: str) -> str:
        code = jellyfish.soundex(name)
        return code if code else ""

    @staticmethod
    def double_metaphone(name: str) -> tuple[str, str]:
        from ._double_metaphone import double_metaphone as dm
        return dm(name)

    @staticmethod
    def syllable_count(name: str) -> int:
        vowels = frozenset("aeiouy")
        name_lower = name.lower()
        count = 0
        prev_is_vowel = False
        for ch in name_lower:
            is_vowel = ch in vowels
            if is_vowel and not prev_is_vowel:
                count += 1
            prev_is_vowel = is_vowel
        return max(1, count)

    @staticmethod
    def metaphone_edit_distance(mp1: str, mp2: str) -> int:
        if not mp1 or not mp2:
            return max(len(mp1), len(mp2))
        return jellyfish.levenshtein_distance(mp1, mp2)

    @staticmethod
    def stress_pattern(name: str) -> str:
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
            syllables.append("".join(current))
        if len(syllables) <= 1:
            return "S"
        pattern = ""
        for i in range(len(syllables)):
            pattern += "S" if i == 0 or i == len(syllables) - 1 else "U"
        return pattern

    @staticmethod
    def stress_pattern_similarity(name1: str, name2: str) -> float:
        p1 = PhoneticEncoder.stress_pattern(name1)
        p2 = PhoneticEncoder.stress_pattern(name2)
        max_len = max(len(p1), len(p2))
        if max_len == 0:
            return 1.0
        match_count = 0
        for i in range(max_len):
            c1 = p1[i] if i < len(p1) else "U"
            c2 = p2[i] if i < len(p2) else "U"
            if c1 == c2:
                match_count += 1
        return match_count / max_len

    def compute_phonetics(self, proposed: str, reference: str) -> tuple[PhoneticScoreDetail, float]:
        s1 = proposed.lower()
        s2 = reference.lower()

        # Phonetic feature extraction
        s_prop = self.soundex(proposed)
        s_ref = self.soundex(reference)

        mp_prop_primary, mp_prop_secondary = self.double_metaphone(proposed)
        mp_ref_primary, mp_ref_secondary = self.double_metaphone(reference)

        # Primary Metaphone: exact match = full credit, near-match = squashed
        mp_edit = self.metaphone_edit_distance(mp_prop_primary, mp_ref_primary)
        max_mp_len = max(len(mp_prop_primary), len(mp_ref_primary), 1)
        mp_norm = mp_edit / max_mp_len
        if mp_prop_primary and mp_ref_primary and mp_prop_primary == mp_ref_primary:
            mp_similarity = 1.0
        else:
            mp_similarity = max(0.0, 1.0 - mp_norm * 1.5)

        # Secondary Metaphone similarity (if both available)
        mp2_similarity = 0.0
        mp2_edit = 0
        if mp_prop_secondary and mp_ref_secondary:
            mp2_edit = self.metaphone_edit_distance(mp_prop_secondary, mp_ref_secondary)
            mp2_max = max(len(mp_prop_secondary), len(mp_ref_secondary), 1)
            if mp_prop_secondary == mp_ref_secondary:
                mp2_similarity = 1.0
            else:
                mp2_similarity = max(0.0, 1.0 - (mp2_edit / mp2_max) * 1.5)

        # Syllable count similarity
        syl_prop = self.syllable_count(proposed)
        syl_ref = self.syllable_count(reference)
        syl_diff = abs(syl_prop - syl_ref)
        syl_similarity = 1.0 if syl_diff == 0 else 0.5 if syl_diff == 1 else 0.0

        # Stress pattern similarity
        stress_sim = self.stress_pattern_similarity(proposed, reference)

        # NED baseline (residual string-level similarity, captures suffix rhyme)
        lev_dist = _levenshtein(s1, s2)
        max_len = max(len(s1), len(s2), 1)
        ned_norm = 1.0 - (lev_dist / max_len)

        # Auditory phoneme-driven scoring:
        #   Primary Metaphone (30%) — dominant pronunciation match
        #   Secondary Metaphone (10%) — alternative pronunciation variant
        #   Syllable count (15%) — rhythm match
        #   Stress pattern (10%) — intonation contour
        #   NED baseline (35%) — suffix rhyme and string-level similarity
        score = (
            mp_similarity * 0.30
            + mp2_similarity * 0.10
            + syl_similarity * 0.15
            + stress_sim * 0.10
            + ned_norm * 0.35
        )
        score = round(max(0.0, min(100.0, score * 100.0)))

        detail = PhoneticScoreDetail(
            soundex_match=bool(s_prop and s_ref and s_prop == s_ref),
            soundex_code_proposed=s_prop,
            soundex_code_reference=s_ref,
            double_metaphone_primary_match=bool(mp_prop_primary and mp_ref_primary and mp_prop_primary == mp_ref_primary),
            double_metaphone_secondary_match=bool(mp_prop_secondary and mp_ref_secondary and mp_prop_secondary == mp_ref_secondary),
            metaphone_proposed_primary=mp_prop_primary,
            metaphone_proposed_secondary=mp_prop_secondary,
            metaphone_reference_primary=mp_ref_primary,
            metaphone_reference_secondary=mp_ref_secondary,
            metaphone_edit_distance=mp_edit,
            metaphone_normalized_distance=mp_norm,
            syllable_count_proposed=syl_prop,
            syllable_count_reference=syl_ref,
            syllable_count_diff=syl_diff,
            stress_pattern_similarity=stress_sim,
            phonetic_score=score / 100.0,
        )
        return detail, score / 100.0
