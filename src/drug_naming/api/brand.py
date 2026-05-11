from __future__ import annotations
from fastapi import APIRouter, Request
from ..models.brand import BrandNameCandidate, BrandScreenRequest, BrandScreenResponse
from ..engines.brand_name import BrandNameEngine

router = APIRouter()

# Reference brand database (would be replaced with real data)
_REFERENCE_BRANDS: list[str] = [
    "Gleevec", "Tasigna", "Sprycel", "Iressa", "Tarceva",
    "Avastin", "Herceptin", "Rituxan", "Humira", "Remicade",
    "Keytruda", "Opdivo", "Yervoy", "Tecentriq", "Bavencio",
    "Lipitor", "Crestor", "Zocor", "Plavix", "Eliquis",
    "Xarelto", "Januvia", "Jardiance", "Ozempic", "Trulicity",
]


@router.post("/screen", response_model=BrandScreenResponse)
def screen_brands(request_body: BrandScreenRequest, request: Request = None) -> BrandScreenResponse:
    """Screen proposed brand names against regulatory and market criteria."""
    engine = BrandNameEngine(existing_brands=_REFERENCE_BRANDS)
    return engine.screen(request_body)


@router.post("/evaluate", response_model=BrandNameCandidate)
def evaluate_brand(
    brand_name: str,
    inn_name: str,
    existing_brand_db: list[str] | None = None,
) -> BrandNameCandidate:
    """Evaluate a single brand name candidate."""
    engine = BrandNameEngine(existing_brands=existing_brand_db or _REFERENCE_BRANDS)
    result = engine.screen(BrandScreenRequest(
        proposed_brand_names=[brand_name],
        inn_name=inn_name,
        existing_brand_db=existing_brand_db or _REFERENCE_BRANDS,
    ))
    return result.results[0] if result.results else BrandNameCandidate(
        brand_name=brand_name, inn_name=inn_name
    )
