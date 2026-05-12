from __future__ import annotations
import csv
from pathlib import Path
from collections import defaultdict

_inn_db_singleton: InnReferenceDB | None = None


def get_inn_reference_db() -> InnReferenceDB:
    """Lazy singleton for the INN reference database."""
    global _inn_db_singleton
    if _inn_db_singleton is None:
        _inn_db_singleton = InnReferenceDB()
    return _inn_db_singleton


class InnReferenceDB:
    """Fast in-memory reference database of 9378 real INN names from WHO PL01-PL134."""

    def __init__(self, csv_path: str | Path | None = None) -> None:
        self._names: list[dict] = []
        self._by_stem: dict[str, list[str]] = defaultdict(list)
        self._english_set: set[str] = set()
        self._latin_set: set[str] = set()
        self._french_set: set[str] = set()
        self._spanish_set: set[str] = set()
        self._stem_frequencies: dict[str, int] = {}
        self._english_to_latin: dict[str, str] = {}
        self._english_to_french: dict[str, str] = {}
        self._english_to_spanish: dict[str, str] = {}

        if csv_path is None:
            csv_path = Path(__file__).parent / "inn_reference.csv"

        self._load(csv_path)

    def _load(self, csv_path: str | Path) -> None:
        with open(csv_path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                self._names.append(row)
                eng = row["english"].strip().lower()
                lat = row["latin"].strip().lower()
                fre = row["french"].strip().lower()
                spa = row["spanish"].strip().lower()
                if eng:
                    self._english_set.add(eng)
                    if lat:
                        self._english_to_latin[eng] = lat
                    if fre:
                        self._english_to_french[eng] = fre
                    if spa:
                        self._english_to_spanish[eng] = spa
                if lat:
                    self._latin_set.add(lat)
                if fre:
                    self._french_set.add(fre)
                if spa:
                    self._spanish_set.add(spa)

        self._index_stems()

    def _index_stems(self) -> None:
        common_stems = [
            "tinib", "mab", "ciclib", "parib", "lisib", "gliptin", "gliflozin",
            "sartan", "vastatin", "prazole", "vir", "grel", "coxib", "afil",
            "milast", "lukast", "setron", "dipine", "olol", "pril", "navir",
            "anib", "cept", "tide", "fibrate", "steride", "caine", "dopa", "entan",
            "bulin", "ast", "astine", "anserin", "adenant", "ampanel", "oxacin",
            "cycline", "cillin", "conazole", "bactam", "barb", "bamate", "bendazole",
            "bradine", "clone", "dan", "dil", "drine", "erg", "estr", "frine",
            "gest", "gli", "imod", "imus", "kin", "kinra", "mer", "micin", "mustine",
            "mycin", "nidazole", "olone", "one", "orphan", "penem", "perone",
            "platin", "poetin", "porfin", "pramine", "pred", "pressin", "pride",
            "profen", "prost", "relin", "rsen", "semide", "spirone", "stigmine",
            "stim", "sulfa", "tant", "terol", "tiazem", "tidine", "tizide",
            "tocin", "toin", "uridine", "vaptan", "verine",
        ]

        for stem in common_stems:
            matches = [n for n in self._english_set if stem in n]
            if matches:
                self._by_stem[stem] = matches
                self._stem_frequencies[stem] = len(matches)

    @property
    def total_names(self) -> int:
        return len(self._names)

    @property
    def english_names(self) -> set[str]:
        return self._english_set

    @property
    def french_names(self) -> set[str]:
        return self._french_set

    @property
    def spanish_names(self) -> set[str]:
        return self._spanish_set

    def lookup_latin(self, english_name: str) -> str | None:
        return self._english_to_latin.get(english_name.strip().lower())

    def lookup_french(self, english_name: str) -> str | None:
        return self._english_to_french.get(english_name.strip().lower())

    def lookup_spanish(self, english_name: str) -> str | None:
        return self._english_to_spanish.get(english_name.strip().lower())

    def exists(self, name: str) -> bool:
        """Check if a name (English or Latin) already exists in the INN database."""
        n = name.strip().lower()
        return n in self._english_set or n in self._latin_set

    def exists_english(self, name: str) -> bool:
        return name.strip().lower() in self._english_set

    def get_references_for_stems(
        self, stem_patterns: list[str], max_per_stem: int = 30
    ) -> list[str]:
        """Get reference INN names that share the given stem patterns (for POCA screening)."""
        results: list[str] = []
        seen: set[str] = set()
        for stem in stem_patterns:
            for name in self._by_stem.get(stem, []):
                if name not in seen:
                    seen.add(name)
                    results.append(name)
                    if len(results) >= max_per_stem:
                        break
        return results

    def get_random_references(self, count: int = 50) -> list[str]:
        """Get a random sample of reference names across all stems."""
        import random
        names = list(self._english_set)
        random.shuffle(names)
        return names[:count]

    def get_stem_frequencies(self) -> dict[str, int]:
        return dict(self._stem_frequencies)

    def get_stem_examples(self, stem: str, limit: int = 10) -> list[str]:
        """Get example INN names for a given stem."""
        return self._by_stem.get(stem, [])[:limit]
