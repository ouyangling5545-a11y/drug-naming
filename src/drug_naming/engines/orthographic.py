from __future__ import annotations
from ..models.poca import OrthographicScoreDetail


def _levenshtein(s1: str, s2: str) -> int:
    """Levenshtein edit distance."""
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
    """Longest common subsequence length."""
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n]


class OrthographicAnalyzer:
    """FDA POCA v2.19.5 orthographic similarity scoring.

    Reverse-engineered from 10 FDA POCA Excel exports (374K pairs across 10
    proposed names). Best-fit formula:
      Ortho = clamp(24 + 66*LCSnorm + 14*NEDnorm, 0, 100)
      MAE=4.17, R²=0.59 vs FDA Ortho scores.

    LCSnorm = LCS / max(len1, len2), NEDnorm = 1 - LD / max(len1, len2).
    FDA Combined = round((Ortho + Phon) / 2).
    """

    @staticmethod
    def levenshtein_normalized(s1: str, s2: str) -> tuple[int, float]:
        s1_lower = s1.lower()
        s2_lower = s2.lower()
        dist = _levenshtein(s1_lower, s2_lower)
        norm = dist / max(len(s1), len(s2), 1)
        return dist, norm

    @staticmethod
    def lcs_normalized(s1: str, s2: str) -> tuple[int, float]:
        s1_lower = s1.lower()
        s2_lower = s2.lower()
        lcs_len = _lcs(s1_lower, s2_lower)
        norm = lcs_len / max(len(s1), len(s2), 1)
        return lcs_len, norm

    @staticmethod
    def bigram_overlap(s1: str, s2: str) -> float:
        s1_lower = s1.lower()
        s2_lower = s2.lower()
        bigrams1 = {s1_lower[i : i + 2] for i in range(len(s1_lower) - 1)}
        bigrams2 = {s2_lower[i : i + 2] for i in range(len(s2_lower) - 1)}
        if not bigrams1 or not bigrams2:
            return 0.0
        intersection = bigrams1 & bigrams2
        return len(intersection) / min(len(bigrams1), len(bigrams2))

    @staticmethod
    def trigram_overlap(s1: str, s2: str) -> float:
        s1_lower = s1.lower()
        s2_lower = s2.lower()
        trigrams1 = {s1_lower[i : i + 3] for i in range(len(s1_lower) - 2)}
        trigrams2 = {s2_lower[i : i + 3] for i in range(len(s2_lower) - 2)}
        if not trigrams1 or not trigrams2:
            return 0.0
        intersection = trigrams1 & trigrams2
        return len(intersection) / min(len(trigrams1), len(trigrams2))

    @staticmethod
    def common_prefix_suffix(s1: str, s2: str) -> tuple[str, int, str, int]:
        s1_lower = s1.lower()
        s2_lower = s2.lower()

        prefix_len = 0
        for c1, c2 in zip(s1_lower, s2_lower):
            if c1 == c2:
                prefix_len += 1
            else:
                break
        prefix = s1[:prefix_len]

        suffix_len = 0
        for c1, c2 in zip(reversed(s1_lower), reversed(s2_lower)):
            if c1 == c2:
                suffix_len += 1
            else:
                break
        suffix = s1[-suffix_len:] if suffix_len > 0 else ""

        return prefix, prefix_len, suffix, suffix_len

    def compute_orthographic(self, proposed: str, reference: str) -> tuple[OrthographicScoreDetail, float]:
        s1 = proposed.lower()
        s2 = reference.lower()

        lev_dist, lev_norm = self.levenshtein_normalized(s1, s2)
        lcs_len, lcs_norm = self.lcs_normalized(s1, s2)
        bigram = self.bigram_overlap(s1, s2)
        trigram = self.trigram_overlap(s1, s2)
        prefix, pfx_len, suffix, sfx_len = self.common_prefix_suffix(s1, s2)

        max_len = max(len(s1), len(s2), 1)
        prefix_ratio = pfx_len / max_len
        suffix_ratio = sfx_len / max_len

        # FDA POCA v2.19.5 formula (reverse-engineered from 374K pairs across 10 drugs)
        # Ortho = clamp(24 + 66*LCSnorm + 14*NEDnorm, 0, 100), MAE=4.17, R²=0.59
        raw = 24 + 66 * lcs_norm + 14 * (1.0 - lev_norm)
        score = max(0.0, min(100.0, raw))
        score = round(score)

        detail = OrthographicScoreDetail(
            levenshtein_distance=lev_dist,
            levenshtein_normalized=lev_norm,
            bigram_overlap_coefficient=bigram,
            trigram_overlap_coefficient=trigram,
            longest_common_prefix=prefix,
            longest_common_prefix_len=pfx_len,
            longest_common_suffix=suffix,
            longest_common_suffix_len=sfx_len,
            prefix_similarity_score=prefix_ratio,
            suffix_similarity_score=suffix_ratio,
            orthographic_score=score / 100.0,
        )
        return detail, score / 100.0
