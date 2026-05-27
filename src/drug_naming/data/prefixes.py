"""Euphonious prefix pools by chemical class.

Single-syllable and two-letter prefixes used as building blocks for
name generation. Prefer prefixes that produce natural-sounding English
drug names.
"""

from __future__ import annotations

# Single-syllable prefixes (used to start names, produce short natural syllables)
CORE_PREFIXES: list[str] = [
    "a", "be", "ce", "da", "e", "fa", "ga", "i", "jo",
    "la", "le", "li", "lo", "lu", "ma", "me", "mi", "mo", "mu",
    "na", "ne", "ni", "no", "nu", "o", "pa", "pe", "pi", "po",
    "ra", "re", "ri", "ro", "ru",
    "sa", "se", "si", "so", "su",
    "ta", "te", "ti", "to", "tu",
    "va", "ve", "vi", "vo", "vu",
    "za", "ze", "zi", "zo", "zu",
]

# Two-letter prefixes (consonant-vowel pairs common in drug names)
SMALL_MOLECULE_PREFIXES: list[str] = [
    "ab", "ac", "af", "al", "am", "an", "ap", "ar", "as", "at", "ax", "az",
    "ba", "be", "bi", "bo", "br", "bu",
    "ca", "ce", "ci", "co", "cr", "cu",
    "da", "de", "di", "do", "dr", "du",
    "el", "em", "en", "er", "es", "ev", "ex",
    "fa", "fe", "fi", "fl", "fo", "fr", "fu",
    "ga", "ge", "gi", "gl", "go", "gr", "gu",
    "ic", "il", "im", "in", "ir", "is", "it", "iv",
    "la", "le", "li", "lo", "lu",
    "ma", "me", "mi", "mo", "mu",
    "na", "ne", "ni", "no", "nu",
    "ol", "om", "on", "op", "or", "os", "ov", "ox",
    "pa", "pe", "pi", "pl", "po", "pr", "pu",
    "ra", "re", "ri", "ro", "ru",
    "sa", "se", "si", "so", "sp", "st", "su",
    "ta", "te", "ti", "to", "tr", "tu",
    "va", "ve", "vi", "vo", "vu",
    "za", "ze", "zi", "zo", "zu",
]

# Antibody-specific prefixes (shorter, softer-sounding)
ANTIBODY_PREFIXES: list[str] = [
    "a", "ba", "be", "bi", "bo", "ca", "ce", "ci", "co", "cu", "da", "de", "di", "do",
    "e", "fa", "fe", "ga", "go", "gu", "i", "ja", "je",
    "la", "le", "li", "lo", "lu", "ma", "me", "mi", "mo", "mu",
    "na", "ne", "ni", "no", "nu", "o", "pa", "pe", "pi", "po",
    "ra", "re", "ri", "ro", "ru",
    "sa", "se", "si", "so", "su",
    "ta", "te", "ti", "to", "tu",
    "va", "ve", "vi", "vo", "vu",
    "za", "ze", "zi", "zo", "zu",
]
