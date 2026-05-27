from __future__ import annotations
from fastapi import APIRouter, Request
from ..models.molecule import PharmacologicalProperties
from ..models.stem import INNStem, StemMatch, StemMatchingConfig
from ..engines.stem_matcher import StemMatchingEngine, StemDataProvider

router = APIRouter()


class InMemoryStemProvider:
    """In-memory stem provider."""

    def __init__(self, stems: list[INNStem]) -> None:
        self._stems = stems

    def get_all_stems(self) -> list[INNStem]:
        return self._stems

    def get_stems_by_category(self, category) -> list[INNStem]:
        return [s for s in self._stems if s.category == category]


def _get_default_provider() -> InMemoryStemProvider:
    from ..data.stems import get_all
    return InMemoryStemProvider(get_all())




@router.post("/match", response_model=list[StemMatch])
def match_stems(properties: PharmacologicalProperties) -> list[StemMatch]:
    """Match a molecule's pharmacological properties to relevant INN stems."""
    provider = _get_default_provider()
    engine = StemMatchingEngine(provider)
    return engine.match(properties)


@router.get("/list", response_model=list[INNStem])
def list_stems(request: Request) -> list[INNStem]:
    """List all INN stems in the database."""
    registry = getattr(request.app.state, "data_registry", None)
    provider = registry.get("stems") if registry else None
    if not provider:
        provider = _get_default_provider()
    return provider.get_all_stems()