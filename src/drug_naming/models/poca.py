from __future__ import annotations
from pydantic import BaseModel, Field


class PhoneticScoreDetail(BaseModel):
    soundex_match: bool = False
    soundex_code_proposed: str = ""
    soundex_code_reference: str = ""
    double_metaphone_primary_match: bool = False
    double_metaphone_secondary_match: bool = False
    metaphone_proposed_primary: str = ""
    metaphone_proposed_secondary: str = ""
    metaphone_reference_primary: str = ""
    metaphone_reference_secondary: str = ""
    metaphone_edit_distance: int = 0
    metaphone_normalized_distance: float = 0.0
    syllable_count_proposed: int = 0
    syllable_count_reference: int = 0
    syllable_count_diff: int = 0
    stress_pattern_similarity: float = 0.0
    phonetic_score: float = Field(default=0.0, description="0-1 aggregated phonetic score")


class OrthographicScoreDetail(BaseModel):
    levenshtein_distance: int = 0
    levenshtein_normalized: float = 0.0
    bigram_overlap_coefficient: float = 0.0
    trigram_overlap_coefficient: float = 0.0
    longest_common_prefix: str = ""
    longest_common_prefix_len: int = 0
    longest_common_suffix: str = ""
    longest_common_suffix_len: int = 0
    prefix_similarity_score: float = 0.0
    suffix_similarity_score: float = 0.0
    orthographic_score: float = Field(default=0.0, description="0-1 aggregated orthographic score")


class CompositionalScoreDetail(BaseModel):
    shared_stems: list[str] = Field(default_factory=list)
    shared_affixes: list[str] = Field(default_factory=list)
    stem_overlap_ratio: float = 0.0
    first_three_chars_match: bool = False
    last_three_chars_match: bool = False
    positional_score: float = 0.0
    shared_syllable_count: int = 0
    total_syllable_score: float = 0.0
    compositional_score: float = Field(default=0.0, description="0-1 aggregated compositional score")


class POCAWeights(BaseModel):
    phonetic_weight: float = Field(default=0.40, ge=0.0, le=1.0)
    orthographic_weight: float = Field(default=0.35, ge=0.0, le=1.0)
    compositional_weight: float = Field(default=0.25, ge=0.0, le=1.0)
    safety_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    high_alert_threshold: float = Field(default=0.85, ge=0.0, le=1.0)


class POCAScoreDetail(BaseModel):
    proposed_name: str
    reference_name: str
    phonetic: PhoneticScoreDetail
    orthographic: OrthographicScoreDetail
    compositional: CompositionalScoreDetail
    phonetic_score: float
    orthographic_score: float
    compositional_score: float
    overall_poca_score: float = Field(description="Weighted combination, 0-1 (higher = more similar = riskier)")
    is_safety_alert: bool = False
    alert_level: str = Field(default="PASS", description="PASS, REVIEW, or REJECT")


class POCARequest(BaseModel):
    proposed_name: str
    reference_names: list[str] = Field(description="List of existing names to compare against")
    weights: POCAWeights = Field(default_factory=POCAWeights)


class POCAResponse(BaseModel):
    results: list[POCAScoreDetail]
    worst_score: float
    worst_comparison: str | None = None
    overall_safety_assessment: str = Field(description="PASS, REVIEW, or REJECT")
