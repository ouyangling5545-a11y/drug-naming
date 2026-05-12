"""Derives Latin pharmaceutical names from English INN names using standard suffix rules.

Also provides French and Spanish taboo checks for regulatory compliance.
"""

LATIN_SUFFIX_RULES: list[tuple[str, str]] = [
    # Longest-first ordering to avoid partial matches
    ("gliflozin", "gliflozinum"),
    ("vastatin", "vastatinum"),
    ("gliptin", "gliptinum"),
    ("ciclib", "ciclibum"),
    ("tinib", "tinibum"),
    ("parib", "paribum"),
    ("lisib", "lisibum"),
    ("sartan", "sartanum"),
    ("prazole", "prazolum"),
    ("coxib", "coxibum"),
    ("milast", "milastum"),
    ("lukast", "lukastum"),
    ("setron", "setronum"),
    ("dipine", "dipinum"),
    ("olol", "ololum"),
    ("pril", "prilum"),
    ("navir", "navirum"),
    ("mab", "mabum"),
    ("grel", "grelum"),
    ("afil", "afilum"),
    ("cept", "ceptum"),
    ("cycline", "cyclinum"),
    ("cillin", "cillinum"),
    ("conazole", "conazolum"),
    ("mycin", "mycinum"),
    ("micin", "micinum"),
    ("platin", "platinum"),
    ("fibrate", "fibratum"),
    # Generic fallbacks
    ("ine", "inum"),
    ("ide", "idum"),
    ("ate", "atum"),
    ("one", "onum"),
    ("ole", "olum"),
    ("ant", "antum"),
    ("ent", "entum"),
]

LATIN_TABOO_TERMS: frozenset[str] = frozenset({
    "sanare", "curare", "miraculum", "divinum",
    "optimus", "maximus", "summus", "perfectus",
    "magicus", "supremus", "ultimus",
})

FRENCH_TABOO_TERMS: frozenset[str] = frozenset({
    "guerison", "guérison", "miracle", "merveille",
    "excellent", "parfait", "divin", "magique",
    "suprême", "ultime", "miraculeux", "prodigieux",
    "formidable", "extraordinaire", "remède",
})

SPANISH_TABOO_TERMS: frozenset[str] = frozenset({
    "curacion", "curación", "milagro", "maravilla",
    "excelente", "perfecto", "divino", "magico",
    "mágico", "supremo", "milagroso", "prodigioso",
    "formidable", "extraordinario", "remedio",
})


def derive_latin_name(english_name: str) -> str:
    """Apply Latin pharmaceutical suffix rules to an English INN name.

    Uses longest-suffix-first matching to ensure specific rules
    (e.g. -tinib) take precedence over generic ones (e.g. -ine).
    """
    name_lower = english_name.strip().lower()
    for eng_suffix, lat_suffix in LATIN_SUFFIX_RULES:
        if name_lower.endswith(eng_suffix):
            return name_lower[: -len(eng_suffix)] + lat_suffix
    if not name_lower.endswith("um"):
        return name_lower + "um"
    return name_lower


def check_latin_taboo(name: str) -> list[str]:
    """Check for taboo/claim-implying substrings in a Latin name."""
    flags = []
    name_lower = name.lower()
    for taboo in LATIN_TABOO_TERMS:
        if taboo in name_lower:
            flags.append(f"taboo_term:{taboo}")
    return flags


def check_french_taboo(name: str) -> list[str]:
    """Check for taboo/claim-implying substrings in a French name."""
    flags = []
    name_lower = name.lower()
    for taboo in FRENCH_TABOO_TERMS:
        if taboo in name_lower:
            flags.append(f"taboo_term:{taboo}")
    return flags


def check_spanish_taboo(name: str) -> list[str]:
    """Check for taboo/claim-implying substrings in a Spanish name."""
    flags = []
    name_lower = name.lower()
    for taboo in SPANISH_TABOO_TERMS:
        if taboo in name_lower:
            flags.append(f"taboo_term:{taboo}")
    return flags
