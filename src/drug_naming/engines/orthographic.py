from __future__ import annotations
import jellyfish
from ..models.poca import OrthographicScoreDetail


class OrthographicAnalyzer:
    """String-distance analysis for orthographic (visual) similarity."""

    @staticmethod
    def levenshtein_normalized(s1: str, s2: str) -> tuple[int, float]:
        s1_lower = s1.lower()
        s2_lower = s2.lower()
        dist = jellyfish.levenshtein_distance(s1_lower, s2_lower)
        norm = dist / max(len(s1), len(s2), 1)
        return dist, norm

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
        lev_dist, lev_norm = self.levenshtein_normalized(proposed, reference)
        bigram = self.bigram_overlap(proposed, reference)
        trigram = self.trigram_overlap(proposed, reference)
        prefix, pfx_len, suffix, sfx_len = self.common_prefix_suffix(proposed, reference)

        max_len = max(len(proposed), len(reference), 1)
        prefix_score = (pfx_len / max_len) * 0.6
        suffix_score = (sfx_len / max_len) * 0.4

        score = 0.0
        if lev_norm <= 0.25:
            score += 0.35
        elif lev_norm <= 0.50:
            score += 0.15
        score += 0.25 * bigram
        score += 0.15 * trigram
        score += 0.15 * prefix_score
        score += 0.10 * suffix_score
        score = min(1.0, score)

        detail = OrthographicScoreDetail(
            levenshtein_distance=lev_dist,
            levenshtein_normalized=lev_norm,
            bigram_overlap_coefficient=bigram,
            trigram_overlap_coefficient=trigram,
            longest_common_prefix=prefix,
            longest_common_prefix_len=pfx_len,
            longest_common_suffix=suffix,
            longest_common_suffix_len=sfx_len,
            prefix_similarity_score=prefix_score,
            suffix_similarity_score=suffix_score,
            orthographic_score=score,
        )
        return detail, score
