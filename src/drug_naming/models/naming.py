from __future__ import annotations
from pydantic import BaseModel, Field
from .molecule import PharmacologicalProperties
from .stem import StemMatch


class NameGenerationConstraints(BaseModel):
    max_name_length: int = 20
    min_name_length: int = 5
    max_candidates_per_stem: int = 50
    max_consecutive_consonants: int = 3
    max_consecutive_vowels: int = 2
    forbidden_prefixes: list[str] = Field(default_factory=list)
    forbidden_suffixes: list[str] = Field(default_factory=list)
    required_infix_rules: bool = True
    avoid_single_char_difference: bool = True
    trigram_overlap_threshold: float = Field(default=0.75, description="Max trigram overlap ratio before rejection, 1.0=off")
    prefix_blacklist: list[str] = Field(default_factory=list, description="Prefixes to skip entirely during generation")
    prefix_lengths: list[int] = Field(default_factory=lambda: [2, 3, 4, 5, 6], description="Allowed prefix lengths; prefixes outside these lengths are skipped")
    prefix_whitelist: list[str] | None = Field(default=None, description="If set, only these prefixes are used during generation")


class NameCandidate(BaseModel):
    name: str
    stems_used: list[StemMatch]
    prefix: str | None = None
    infix: str | None = None
    suffix: str | None = None
    generation_method: str = "combinatorial"
    phonological_score: float = Field(default=0.0, description="0-1, higher = more phonologically natural")
    regulatory_flags: list[str] = Field(default_factory=list)


class NameGenerationRequest(BaseModel):
    properties: PharmacologicalProperties
    matched_stems: list[StemMatch]
    constraints: NameGenerationConstraints = Field(default_factory=NameGenerationConstraints)
    existing_names_to_avoid: list[str] = Field(default_factory=list)
    relaxed: bool = Field(default=False, description="Skip trigram/existing-name filters to generate more candidates")


class NameGenerationResponse(BaseModel):
    candidates: list[NameCandidate]
    total_generated: int
    filtered_out: int
    flag_counts: dict[str, int] = Field(default_factory=dict)
