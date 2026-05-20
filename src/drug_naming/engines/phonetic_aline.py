from __future__ import annotations
import re
from ..models.poca import PhoneticScoreDetail

# ═══════════════════════════════════════════════════════════════════════════════
# ALINE (Alignment of Intertranscribable Elements) phonetic similarity engine.
# Kondrak 2000: phoneme-level similarity via articulatory feature vectors.
#
# Unlike Double Metaphone (which maps spelling→4-char code and matches exactly),
# ALINE aligns phoneme sequences and computes continuous similarity from
# articulatory distance — /p/ vs /b/ differ only in voicing (score≈0.85),
# while /p/ vs /a/ have zero overlap (score≈0).
# ═══════════════════════════════════════════════════════════════════════════════

# ── Phoneme inventory & articulatory feature vectors ──────────────────────────
# Each phoneme → [cons, place, manner, voice, height, back, round]
#
#   cons    : 1 = consonant,         0 = vowel
#   place   : labial(0) → glottal(1)
#   manner  : stop(0) → approx(1)
#   voice   : 0 = voiceless,         1 = voiced
#   height  : high(0) → low(1)       (vowels only)
#   back    : front(0) → back(1)     (vowels only)
#   round   : 0 = unrounded,         1 = rounded  (vowels only)

_PHONEME_FEATURES: dict[str, list[float]] = {
    # Consonants
    "p":  [1, 0.00, 0.00, 0, 0, 0, 0],
    "b":  [1, 0.00, 0.00, 1, 0, 0, 0],
    "t":  [1, 0.25, 0.00, 0, 0, 0, 0],
    "d":  [1, 0.25, 0.00, 1, 0, 0, 0],
    "k":  [1, 0.75, 0.00, 0, 0, 0, 0],
    "g":  [1, 0.75, 0.00, 1, 0, 0, 0],
    "ʔ":  [1, 1.00, 0.00, 0, 0, 0, 0],
    "f":  [1, 0.00, 0.50, 0, 0, 0, 0],
    "v":  [1, 0.00, 0.50, 1, 0, 0, 0],
    "θ":  [1, 0.20, 0.50, 0, 0, 0, 0],
    "ð":  [1, 0.20, 0.50, 1, 0, 0, 0],
    "s":  [1, 0.25, 0.50, 0, 0, 0, 0],
    "z":  [1, 0.25, 0.50, 1, 0, 0, 0],
    "ʃ":  [1, 0.40, 0.50, 0, 0, 0, 0],
    "ʒ":  [1, 0.40, 0.50, 1, 0, 0, 0],
    "h":  [1, 1.00, 0.50, 0, 0, 0, 0],
    "tʃ": [1, 0.40, 0.25, 0, 0, 0, 0],
    "dʒ": [1, 0.40, 0.25, 1, 0, 0, 0],
    "m":  [1, 0.00, 1.00, 1, 0, 0, 0],
    "n":  [1, 0.25, 1.00, 1, 0, 0, 0],
    "ŋ":  [1, 0.75, 1.00, 1, 0, 0, 0],
    "l":  [1, 0.25, 0.75, 1, 0, 0, 0],
    "r":  [1, 0.40, 0.75, 1, 0, 0, 0],
    "ɹ":  [1, 0.40, 0.75, 1, 0, 0, 0],
    "j":  [1, 0.60, 1.00, 1, 0, 0, 0],
    "w":  [1, 0.00, 1.00, 1, 0, 0, 0],
    # Vowels
    "i":  [0, 0, 0, 1, 0.00, 0.00, 0],
    "ɪ":  [0, 0, 0, 1, 0.10, 0.10, 0],
    "e":  [0, 0, 0, 1, 0.25, 0.00, 0],
    "ɛ":  [0, 0, 0, 1, 0.40, 0.10, 0],
    "æ":  [0, 0, 0, 1, 0.60, 0.15, 0],
    "ə":  [0, 0, 0, 1, 0.50, 0.50, 0],
    "ʌ":  [0, 0, 0, 1, 0.55, 0.50, 0],
    "ɑ":  [0, 0, 0, 1, 1.00, 0.60, 0],
    "ɒ":  [0, 0, 0, 1, 1.00, 0.80, 1],
    "ɔ":  [0, 0, 0, 1, 0.60, 0.80, 1],
    "o":  [0, 0, 0, 1, 0.35, 0.80, 1],
    "ʊ":  [0, 0, 0, 1, 0.20, 0.90, 1],
    "u":  [0, 0, 0, 1, 0.00, 0.90, 1],
    # Semivowels / weak
    "ɚ":  [0, 0, 0, 1, 0.50, 0.50, 0],
    "ɝ":  [0, 0, 0, 1, 0.50, 0.50, 0],
}


def _feature_distance(f1: list[float], f2: list[float]) -> float:
    """Manhattan distance between two feature vectors, normalized to [0,1]."""
    diff = sum(abs(a - b) for a, b in zip(f1, f2))
    return min(1.0, diff / 7.0)


def _phoneme_salience(phoneme: str) -> float:
    """Salience of a phoneme for indel cost. Vowels less salient than consonants."""
    feats = _PHONEME_FEATURES.get(phoneme)
    if feats is None:
        return 0.5
    if feats[0] == 1:  # consonant
        return 0.6
    return 0.4  # vowel


# ── Grapheme-to-Phoneme (English rules) ───────────────────────────────────────
# Context-sensitive rewrite rules: (pattern, replacement)
# Applied left-to-right, longest-match greedy.

_G2P_RULES: list[tuple[str, str]] = [
    # Consonant digraphs
    ("tch",     "tʃ"),
    ("dge",     "dʒ"),
    ("ch",      "tʃ"),
    ("sh",      "ʃ"),
    ("th",      "θ"),   # default voiceless, voiced in function words
    ("ph",      "f"),
    ("gh",      ""),    # silent in most contexts
    ("wh",      "w"),
    ("kn",      "n"),
    ("gn",      "n"),
    ("wr",      "ɹ"),
    ("ck",      "k"),
    ("ng",      "ŋ"),
    ("dge",     "dʒ"),
    # Vowel digraphs
    ("ee",      "i"),
    ("ea",      "i"),
    ("oo",      "u"),
    ("ou",      "aʊ"),
    ("ow",      "oʊ"),
    ("oi",      "ɔɪ"),
    ("oy",      "ɔɪ"),
    ("ai",      "eɪ"),
    ("ay",      "eɪ"),
    ("au",      "ɔ"),
    ("aw",      "ɔ"),
    ("ew",      "ju"),
    # R-colored
    ("er",      "ɚ"),
    ("ir",      "ɝ"),
    ("ur",      "ɝ"),
    ("ar",      "ɑɹ"),
    ("or",      "ɔɹ"),
    # Consonant singletons (context-free)
    ("b",       "b"),
    ("c",       "k"),    # default hard-c; soft before e/i/y is handled below
    ("d",       "d"),
    ("f",       "f"),
    ("g",       "g"),
    ("h",       "h"),
    ("j",       "dʒ"),
    ("k",       "k"),
    ("l",       "l"),
    ("m",       "m"),
    ("n",       "n"),
    ("p",       "p"),
    ("q",       "k"),    # qu → kw handled separately
    ("r",       "ɹ"),
    ("s",       "s"),
    ("t",       "t"),
    ("v",       "v"),
    ("w",       "w"),
    ("x",       "ks"),
    ("y",       "j"),
    ("z",       "z"),
    # Vowel singletons (context-free defaults, overridden below)
    ("a",       "æ"),
    ("e",       "ɛ"),
    ("i",       "ɪ"),
    ("o",       "ɒ"),
    ("u",       "ʌ"),
]


def _apply_g2p(word: str) -> list[str]:
    """Convert an English word to a phoneme sequence using rewrite rules.

    Applies context-sensitive corrections for soft-c, soft-g, final-e, etc.
    Returns a list of phoneme symbols from the inventory above.
    """
    word = word.lower().strip()
    phonemes: list[str] = []

    # Soft c/g before front vowels
    word = re.sub(r"c(?=[eiy])", "s", word)
    word = re.sub(r"g(?=[eiy])", "dʒ", word)

    # qu → kw
    word = word.replace("qu", "kw")

    # Final silent -e: makes preceding vowel long, then drops
    # Pattern: vowel + cons + e$ → long vowel + cons
    word = re.sub(r"([aeiou])([^aeiouh]?)e$", _lengthen_vowel, word)

    # Apply context-free rules, longest first
    for pattern, replacement in _G2P_RULES:
        if pattern == replacement:
            continue  # skip identity mappings (e.g. b→b) to avoid infinite loop
        while pattern in word:
            word = word.replace(pattern, replacement, 1)

    # Filter out empty strings (silent letters that were deleted)
    i = 0
    while i < len(word):
        # Try multi-char phoneme match
        matched = False
        for length in (2, 1):
            if i + length <= len(word):
                chunk = word[i:i + length]
                if chunk in _PHONEME_FEATURES:
                    phonemes.append(chunk)
                    i += length
                    matched = True
                    break
        if not matched:
            i += 1

    return phonemes


def _lengthen_vowel(m: re.Match) -> str:
    """Final-e lengthening: CVCe → CVːC (tense vowel)."""
    vowel = m.group(1)
    consonant = m.group(2) or ""
    long_map = {"a": "eɪ", "e": "i", "i": "aɪ", "o": "oʊ", "u": "ju"}
    return long_map.get(vowel, vowel) + consonant


# ── ALINE DP alignment ────────────────────────────────────────────────────────

def _aline_score(seq1: list[str], seq2: list[str]) -> float:
    """Compute ALINE similarity score between two phoneme sequences.

    DP alignment with phoneme-feature substitution costs and
    salience-weighted insertion/deletion costs.

    Returns normalized score in [0, 1].
    """
    if not seq1 and not seq2:
        return 1.0
    if not seq1 or not seq2:
        return 0.0

    # DP matrix
    m, n = len(seq1), len(seq2)
    dp = [[0.0] * (n + 1) for _ in range(m + 1)]

    # Base cases: cumulative indel costs
    for i in range(1, m + 1):
        dp[i][0] = dp[i - 1][0] + _phoneme_salience(seq1[i - 1])
    for j in range(1, n + 1):
        dp[0][j] = dp[0][j - 1] + _phoneme_salience(seq2[j - 1])

    for i in range(1, m + 1):
        p1 = seq1[i - 1]
        f1 = _PHONEME_FEATURES.get(p1)
        for j in range(1, n + 1):
            p2 = seq2[j - 1]
            f2 = _PHONEME_FEATURES.get(p2)

            if f1 is not None and f2 is not None:
                sub_cost = _feature_distance(f1, f2)
            else:
                sub_cost = 1.0 if p1 != p2 else 0.0

            sub = dp[i - 1][j - 1] + sub_cost
            ins = dp[i][j - 1] + _phoneme_salience(p2)
            dele = dp[i - 1][j] + _phoneme_salience(p1)
            dp[i][j] = min(sub, ins, dele)

    # Normalize: max possible cost = sum of saliences for longer sequence
    max_cost = sum(_phoneme_salience(p) for p in seq1) + sum(_phoneme_salience(p) for p in seq2)
    if max_cost == 0:
        return 1.0

    similarity = 1.0 - dp[m][n] / (max_cost * 0.5)
    return max(0.0, min(1.0, similarity))


# ── Public engine ─────────────────────────────────────────────────────────────

class AlineEncoder:
    """Phonetic similarity via ALINE (Kondrak 2000) articulatory feature alignment.

    Unlike Metaphone (which reduces names to 4-letter consonant codes and
    matches them exactly), ALINE:

    1. Converts spelling to IPA phoneme sequences via G2P rules
    2. Aligns phonemes using DP with articulatory feature distance
    3. Produces continuous 0-100 similarity scores

    This captures partial phonetic overlap that Metaphone misses — e.g.
    /ɪməˈtɪnɪb/ vs /ɜɹləˈtɪnɪb/ differ on the first two phonemes but
    share the entire -tinib suffix (last 5 phonemes identical).
    """

    @staticmethod
    def to_phonemes(word: str) -> list[str]:
        """Convert an English word to its phoneme sequence."""
        return _apply_g2p(word)

    def compute_phonetics(self, proposed: str, reference: str) -> tuple[PhoneticScoreDetail, float]:
        seq1 = self.to_phonemes(proposed)
        seq2 = self.to_phonemes(reference)

        aline_sim = _aline_score(seq1, seq2)
        score = round(max(0.0, min(100.0, aline_sim * 100.0)))

        detail = PhoneticScoreDetail(
            metaphone_proposed_primary="(".join(seq1),
            metaphone_reference_primary="(".join(seq2),
            phonetic_score=score / 100.0,
        )
        return detail, score / 100.0
