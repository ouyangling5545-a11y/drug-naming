from __future__ import annotations
import csv
import json
from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from pathlib import Path

T = TypeVar("T")


class DataSource(ABC, Generic[T]):
    """Abstract data source — implement for your file format."""

    @abstractmethod
    def load(self) -> list[T]:
        """Load all records from the data source."""
        ...

    @abstractmethod
    def validate(self, data: list[T]) -> bool:
        """Validate loaded data against expected schema."""
        ...


class DataRegistry:
    """Central registry for all data sources used by the naming system."""

    def __init__(self) -> None:
        self._sources: dict[str, DataSource] = {}

    def register(self, name: str, source: DataSource) -> None:
        self._sources[name] = source

    def get(self, name: str) -> DataSource | None:
        return self._sources.get(name)

    def list_sources(self) -> list[str]:
        return list(self._sources.keys())


# --- Built-in data sources for common formats ---

from ..models.stem import INNStem, StemPosition, StemCategory


class CSVStemDataSource(DataSource[INNStem]):
    """Load INN stems from CSV file.

    Expected columns:
    stem, position, category, meaning, who_definition, target_classes,
    mechanisms, chemical_classes, indications, examples, infix_required,
    allowed_infixes, exclusion_rules, priority
    """

    def __init__(self, filepath: str | Path) -> None:
        self.filepath = Path(filepath)

    def load(self) -> list[INNStem]:
        stems: list[INNStem] = []
        with open(self.filepath, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                stems.append(self._row_to_stem(row))
        return stems

    def validate(self, data: list[INNStem]) -> bool:
        if not data:
            return False
        for stem in data:
            if not stem.stem:
                return False
            if not stem.meaning:
                return False
        return True

    @staticmethod
    def _row_to_stem(row: dict[str, str]) -> INNStem:
        def split_list(val: str) -> list[str]:
            if not val.strip():
                return []
            return [v.strip() for v in val.split(";")]

        return INNStem(
            stem=row.get("stem", "").strip(),
            position=StemPosition(row.get("position", "suffix").strip().lower()),
            category=StemCategory(row.get("category", "target_class_stem").strip().lower()),
            meaning=row.get("meaning", "").strip(),
            who_definition=row.get("who_definition", "").strip() or None,
            chinese=row.get("chinese", "").strip() or "",
            target_classes=split_list(row.get("target_classes", "")),
            mechanisms=split_list(row.get("mechanisms", "")),
            chemical_classes=split_list(row.get("chemical_classes", "")),
            indications=split_list(row.get("indications", "")),
            examples=split_list(row.get("examples", "")),
            infix_required=row.get("infix_required", "").strip().lower() == "true",
            allowed_infixes=split_list(row.get("allowed_infixes", "")),
            exclusion_rules=split_list(row.get("exclusion_rules", "")),
            priority=int(row.get("priority", "0")),
            source=row.get("source", "WHO INN Programme").strip(),
        )


class JSONDataSource(DataSource, Generic[T]):
    """Load data from a JSON file. User provides a factory function to parse each record."""

    def __init__(self, filepath: str | Path, factory: callable[[dict], T]) -> None:
        self.filepath = Path(filepath)
        self.factory = factory

    def load(self) -> list[T]:
        with open(self.filepath, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, list):
            return [self.factory(item) for item in raw]
        if isinstance(raw, dict) and "data" in raw:
            return [self.factory(item) for item in raw["data"]]
        return []

    def validate(self, data: list[T]) -> bool:
        return len(data) > 0
