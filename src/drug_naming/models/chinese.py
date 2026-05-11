from __future__ import annotations
from pydantic import BaseModel, Field


class ChineseCharacterSimilarity(BaseModel):
    char1: str
    char2: str
    radical_similarity: float = 0.0
    stroke_count_diff: int = 0
    shape_similarity_score: float = 0.0
    pronunciation_similarity: float = 0.0
    overall_similarity: float = 0.0


class ChineseNameCandidate(BaseModel):
    chinese_name: str
    pinyin: str
    source_stem_translation: str | None = None
    characters: list[str] = Field(default_factory=list)
    stroke_count: int = 0
    meaning_gloss: str | None = None
    regulatory_compliance: bool = True
    regulatory_flags: list[str] = Field(default_factory=list)
    similarity_to_approved: list[ChineseCharacterSimilarity] = Field(default_factory=list)
    overall_score: float = 0.0


class ChineseNameRequest(BaseModel):
    inn_name: str
    pharmacological_properties: dict = Field(default_factory=dict)
    target_meaning: str | None = None
    preferred_characters: list[str] | None = None
    max_candidates: int = 20


class ChineseNameResponse(BaseModel):
    candidates: list[ChineseNameCandidate]
