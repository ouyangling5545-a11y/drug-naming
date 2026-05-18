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


# Built-in reference stems (WHO INN Stem Book 2024)
# Enriched with definitions and examples from the WHO INN Programme
_REFERENCE_STEMS: list[INNStem] = []  # populated on first access

_STEMS_LOADED = False


def _ensure_stems_loaded() -> None:
    """Load stems from CSV on first access (lazy init)."""
    global _REFERENCE_STEMS, _STEMS_LOADED
    if _STEMS_LOADED:
        return
    from pathlib import Path
    from ..data.loader import CSVStemDataSource
    csv_path = Path(__file__).resolve().parent.parent / "data" / "stems.csv"
    source = CSVStemDataSource(csv_path)
    _REFERENCE_STEMS = source.load()
    _STEMS_LOADED = True


def _get_default_provider() -> InMemoryStemProvider:
    _ensure_stems_loaded()
    return InMemoryStemProvider(_REFERENCE_STEMS)




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