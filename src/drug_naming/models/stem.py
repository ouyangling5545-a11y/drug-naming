from __future__ import annotations
from .._compat import StrEnum
from pydantic import BaseModel, Field


class StemPosition(StrEnum):
    PREFIX = "prefix"
    INFIX = "infix"
    SUFFIX = "suffix"


class StemCategory(StrEnum):
    TARGET_CLASS_STEM = "target_class_stem"
    MECHANISM_STEM = "mechanism_stem"
    CHEMICAL_CLASS_STEM = "chemical_class_stem"
    INDICATION_STEM = "indication_stem"
    COMBINATION_STEM = "combination_stem"


class INNStem(BaseModel):
    stem: str = Field(description="Stem text, e.g. '-tinib', '-mab', '-lukast'")
    position: StemPosition
    category: StemCategory
    meaning: str = Field(description="What the stem indicates, e.g. 'tyrosine kinase inhibitor'")
    who_definition: str | None = None
    target_classes: list[str] = Field(default_factory=list)
    mechanisms: list[str] = Field(default_factory=list)
    chemical_classes: list[str] = Field(default_factory=list)
    indications: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    infix_required: bool = False
    allowed_infixes: list[str] = Field(default_factory=list)
    exclusion_rules: list[str] = Field(default_factory=list)
    priority: int = Field(default=0, description="Higher = more specific match preferred")
    source: str = Field(default="WHO INN Programme")


class StemMatch(BaseModel):
    stem: INNStem
    match_score: float = Field(description="0.0 to 1.0 overall match score")
    match_reasons: list[str] = Field(default_factory=list)
    relevance_weight: float = Field(default=1.0)


class StemMatchingConfig(BaseModel):
    target_class_weight: float = 0.35
    mechanism_weight: float = 0.30
    chemical_class_weight: float = 0.25
    indication_weight: float = 0.10
    substructure_bonus_max: float = 0.10
    min_score: float = 0.20
    max_results: int = 10
