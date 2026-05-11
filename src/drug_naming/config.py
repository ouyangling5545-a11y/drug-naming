from __future__ import annotations
from pydantic_settings import BaseSettings
from pydantic import Field


class EngineSettings(BaseSettings):
    model_config = {"env_prefix": "DN_", "env_nested_delimiter": "__"}

    poca_phonetic_weight: float = Field(default=0.40, ge=0.0, le=1.0)
    poca_orthographic_weight: float = Field(default=0.35, ge=0.0, le=1.0)
    poca_compositional_weight: float = Field(default=0.25, ge=0.0, le=1.0)
    poca_safety_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    poca_high_alert_threshold: float = Field(default=0.85, ge=0.0, le=1.0)

    stem_target_weight: float = 0.35
    stem_mechanism_weight: float = 0.30
    stem_chemical_weight: float = 0.25
    stem_indication_weight: float = 0.10
    stem_substructure_bonus_max: float = 0.10
    stem_min_match_score: float = 0.20
    stem_max_results: int = 10

    name_min_length: int = 5
    name_max_length: int = 20
    name_max_candidates_per_stem: int = 50
    name_max_consecutive_consonants: int = 3
    name_max_consecutive_vowels: int = 2

    chinese_max_candidates: int = 20
    chinese_name_min_chars: int = 2
    chinese_name_max_chars: int = 5
