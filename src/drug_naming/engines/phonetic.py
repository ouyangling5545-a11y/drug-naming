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
    """Encodes names into phonetic representations and computes similarity scores.

    FDA POCA v2.19.5 phonetic formula (reverse-engineered from 168K pairs, MAE≈8.1):
        Phon = clamp(5 + 70*LCSnorm + 10*NEDnorm, 0, 100)

    NOTE: Despite the name "Phonetic", this formula is NOT pronunciation-based.
    Both Ortho and Phon use the same string-matching features (LCS + NED), just
    with different weights. FDA's "Phonetic" is more accurately described as
    "lexical similarity from a different angle" — a second view on the same
    string data to reduce single-dimension bias when averaged with Ortho.

    True phonetic features (Double Metaphone, syllable count, stress pattern)
    are computed and stored in PhoneticScoreDetail but NOT used in the final
    score, matching FDA's actual algorithm behavior.
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

        # Existing phonetic feature extraction (for detail display)
        s_prop = self.soundex(proposed)
        s_ref = self.soundex(reference)

        mp_prop_primary, mp_prop_secondary = self.double_metaphone(proposed)
        mp_ref_primary, mp_ref_secondary = self.double_metaphone(reference)

        mp_edit = self.metaphone_edit_distance(mp_prop_primary, mp_ref_primary)
        max_mp_len = max(len(mp_prop_primary), len(mp_ref_primary), 1)
        mp_norm = mp_edit / max_mp_len

        syl_prop = self.syllable_count(proposed)
        syl_ref = self.syllable_count(reference)
        syl_diff = abs(syl_prop - syl_ref)

        stress_sim = self.stress_pattern_similarity(proposed, reference)

        # FDA POCA v2.19.5 phonetic formula (reverse-engineered from 168K pairs, MAE≈8.1)
        lcs_len = _lcs(s1, s2)
        lev_dist = _levenshtein(s1, s2)
        max_len = max(len(s1), len(s2), 1)
        lcs_norm = lcs_len / max_len
        ned_norm = 1.0 - (lev_dist / max_len)

        raw = 5 + 70 * lcs_norm + 10 * ned_norm
        score = max(0.0, min(100.0, raw))
        score = round(score)

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
