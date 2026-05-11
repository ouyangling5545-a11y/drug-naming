from __future__ import annotations
from pydantic import BaseModel, Field


class BrandNameCandidate(BaseModel):
    brand_name: str
    inn_name: str | None = None
    similarity_to_inn: float = 0.0
    similarity_to_existing_brands: float = 0.0
    semantic_associations: list[str] = Field(default_factory=list)
    regulatory_flags: list[str] = Field(default_factory=list)
    marketability_score: float = 0.0
    overall_score: float = 0.0


class BrandScreenRequest(BaseModel):
    proposed_brand_names: list[str]
    inn_name: str
    existing_brand_db: list[str] = Field(default_factory=list)
    regulatory_rules: dict = Field(default_factory=dict)


class BrandScreenResponse(BaseModel):
    results: list[BrandNameCandidate]
    top_candidate: BrandNameCandidate | None = None
