from __future__ import annotations
from .phonetic import PhoneticEncoder
from .phonetic_aline import AlineEncoder
from .orthographic import OrthographicAnalyzer
from .compositional import CompositionalAnalyzer
from ..models.poca import (
    POCAScoreDetail,
    POCAWeights,
    POCARequest,
    POCAResponse,
)


class POCAScoringEngine:
    """Full FDA POCA scoring coordinator combining phonetic, orthographic, and compositional analysis.

    Can use an InnReferenceDB for intelligent reference name selection instead of
    brute-force comparison against all names.

    Supports two phonetic backends: 'metaphone' (default, fast phoneme-driven scoring
    via Double Metaphone + syllables + stress + NED) and 'aline' (Kondrak 2000
    articulatory feature alignment, continuous similarity from G2P→IPA→DP alignment).
    """

    def __init__(
        self,
        weights: POCAWeights | None = None,
        known_stems: list[str] | None = None,
        inn_reference_db=None,
        phonetic_method: str = "metaphone",
    ) -> None:
        self.weights = weights or POCAWeights()
        self._phonetic_method = phonetic_method
        self._phonetic_metaphone = PhoneticEncoder()
        self._phonetic_aline = AlineEncoder()
        self.orthographic = OrthographicAnalyzer()
        self.compositional = CompositionalAnalyzer(known_stems or [])
        self._inn_db = inn_reference_db

    @property
    def phonetic_method(self) -> str:
        return self._phonetic_method

    @phonetic_method.setter
    def phonetic_method(self, value: str) -> None:
        if value not in ("metaphone", "aline"):
            raise ValueError(f"Unknown phonetic method: {value}")
        self._phonetic_method = value

    def _get_phonetic_encoder(self):
        return self._phonetic_aline if self._phonetic_method == "aline" else self._phonetic_metaphone

    def set_known_stems(self, stems: list[str]) -> None:
        self.compositional.set_stems(stems)

    def smart_references(self, proposed_name: str, max_refs: int = 30) -> list[str]:
        """Select the most relevant reference names for POCA comparison.

        Uses the INN reference database to find names sharing the same stems,
        falling back to the provided reference list if no DB is available.
        """
        if self._inn_db is None:
            return []

        # Detect stems present in the proposed name
        detected_stems = []
        for stem, freq in self._inn_db.get_stem_frequencies().items():
            if stem in proposed_name.lower():
                detected_stems.append(stem)

        if detected_stems:
            return self._inn_db.get_references_for_stems(detected_stems, max_refs)
        return self._inn_db.get_random_references(max_refs)

    def score_pair(self, proposed: str, reference: str, mode: str = "full") -> POCAScoreDetail:
        """Score a pair of names. mode='full' uses 3D, mode='fda' uses Phon+Orth only."""
        phonetic_encoder = self._get_phonetic_encoder()
        phonetic_detail, phonetic_score = phonetic_encoder.compute_phonetics(proposed, reference)
        orthographic_detail, orthographic_score = self.orthographic.compute_orthographic(proposed, reference)
        compositional_detail, compositional_score = self.compositional.compute_compositional(proposed, reference)

        if mode == "fda":
            overall = (phonetic_score + orthographic_score) / 2.0
        else:
            overall = (
                self.weights.phonetic_weight * phonetic_score
                + self.weights.orthographic_weight * orthographic_score
                + self.weights.compositional_weight * compositional_score
            )

        overall = min(1.0, overall)

        if overall >= self.weights.high_alert_threshold:
            alert_level = "REJECT"
        elif overall >= self.weights.safety_threshold:
            alert_level = "REVIEW"
        else:
            alert_level = "PASS"

        return POCAScoreDetail(
            proposed_name=proposed,
            reference_name=reference,
            phonetic=phonetic_detail,
            orthographic=orthographic_detail,
            compositional=compositional_detail,
            phonetic_score=phonetic_score,
            orthographic_score=orthographic_score,
            compositional_score=compositional_score,
            overall_poca_score=overall,
            is_safety_alert=alert_level in ("REVIEW", "REJECT"),
            alert_level=alert_level,
        )

    def score_batch(self, request: POCARequest) -> POCAResponse:
        if request.weights:
            self.weights = request.weights

        results: list[POCAScoreDetail] = []
        worst_score = 0.0
        worst_comparison: str | None = None

        for ref_name in request.reference_names:
            result = self.score_pair(request.proposed_name, ref_name)
            results.append(result)
            if result.overall_poca_score > worst_score:
                worst_score = result.overall_poca_score
                worst_comparison = ref_name

        if worst_score >= self.weights.high_alert_threshold:
            assessment = "REJECT"
        elif worst_score >= self.weights.safety_threshold:
            assessment = "REVIEW"
        else:
            assessment = "PASS"

        return POCAResponse(
            results=results,
            worst_score=worst_score,
            worst_comparison=worst_comparison,
            overall_safety_assessment=assessment,
        )

    def score_batch_fda(
        self,
        proposed_name: str,
        reference_names: list[str],
        threshold: float = 0.55,
        max_results: int = 100,
    ) -> list[POCAScoreDetail]:
        """FDA-style 2D scoring with threshold filtering.

        Returns only names at or above the threshold, sorted by score descending,
        capped at max_results.
        """
        results: list[POCAScoreDetail] = []
        for ref_name in reference_names:
            result = self.score_pair(proposed_name, ref_name, mode="fda")
            if result.overall_poca_score >= threshold:
                results.append(result)

        results.sort(key=lambda r: r.overall_poca_score, reverse=True)
        return results[:max_results]
