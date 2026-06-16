from __future__ import annotations

# ── Valid English onset clusters ────────────────────────────────────────────
# Two-consonant onsets that are phonotactically valid in English.
VALID_ONSET_CLUSTERS: frozenset[str] = frozenset([
    "bl", "br", "ch", "cl", "cr", "dr", "dw", "fl", "fr", "gh",
    "gl", "gn", "gr", "kn", "ph", "pl", "pr", "ps", "qu", "sc",
    "sh", "sk", "sl", "sm", "sn", "sp", "sq", "st", "sw", "th",
    "tr", "tw", "wh", "wr", "zh",
])

# Three-consonant onsets: must start with 's' + a valid two-consonant onset.
VALID_TRIPLE_ONSETS: frozenset[str] = frozenset([
    "sch", "scr", "shr", "sph", "spl", "spr", "squ", "str", "thr",
])

# Valid two-consonant codas (word-final).
VALID_CODA_CLUSTERS: frozenset[str] = frozenset([
    "ct", "ft", "ld", "lf", "lk", "ll", "lm", "ln", "lp", "lt",
    "mp", "nc", "nd", "ng", "nk", "nt", "pt", "rb", "rd", "rf",
    "rk", "rl", "rm", "rn", "rp", "rt", "sk", "sp", "st", "th",
    "ts", "xt",
])

# Awkward endings we want to avoid in drug names (non-pharmaceutical).
BAD_ENDINGS: frozenset[str] = frozenset([
    "xzx", "qk", "jq", "vq", "zq", "xq", "gk", "bk", "tk", "pk",
    "cg", "kg", "tg", "dg", "bg", "pg", "vg", "zg",
    "fv", "pf", "bv", "mv",
])

VOWELS: frozenset[str] = frozenset("aeiouy")
CONSONANTS: frozenset[str] = frozenset("bcdfghjklmnpqrstvwxz")


def count_syllables(name: str) -> int:
    """Approximate syllable count by counting vowel-to-consonant transitions."""
    s = name.lower()
    count = 0
    prev_vowel = False
    for ch in s:
        is_vowel = ch in VOWELS
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    return max(1, count)


def has_invalid_consonant_cluster(name: str) -> bool:
    """Check for consonant sequences that violate English phonotactics.

    Scans the name for runs of 2+ consecutive consonants and validates each
    run against the whitelist. A cluster is only valid if it appears in full
    as a known English onset, coda, or can be decomposed into valid parts.
    """
    s = name.lower()
    i = 0
    while i < len(s):
        if s[i] not in CONSONANTS:
            i += 1
            continue

        # Find the consonant run
        start = i
        while i < len(s) and s[i] in CONSONANTS:
            i += 1
        run = s[start:i]
        run_len = len(run)

        if run_len <= 1:
            continue

        # Determine if this run appears at the start of the name (onset position)
        is_onset = (start == 0)
        # Determine if at end (coda position)
        is_coda = (i == len(s))

        if run_len == 2:
            # Geminate (same letter twice): always valid across syllable boundary
            if run[0] == run[1]:
                continue
            if is_onset and run in VALID_ONSET_CLUSTERS:
                continue
            if is_coda and run in VALID_CODA_CLUSTERS:
                continue
            # Medial (between vowels): either valid onset or valid coda
            if not is_onset and not is_coda:
                if run in VALID_ONSET_CLUSTERS or run in VALID_CODA_CLUSTERS:
                    continue
            if run in VALID_ONSET_CLUSTERS or run in VALID_CODA_CLUSTERS:
                continue
            return True

        if run_len == 3:
            # Triple consonant clusters are only valid as onsets
            if is_onset and run in VALID_TRIPLE_ONSETS:
                continue
            # Medial triple: check if s+cluster or cluster can be split
            if not is_onset and not is_coda:
                # Try: first char is coda of previous syllable, last 2 are onset of next
                if run[1:] in VALID_ONSET_CLUSTERS:
                    continue
                # Try: first 2 are coda, last 1 is onset of next
                if run[:2] in VALID_CODA_CLUSTERS:
                    continue
            return True

        # 4+ consonants: always invalid in English
        return True

    return False


def boundary_cluster_valid(prefix: str, suffix: str) -> bool:
    """Check if the consonant cluster at prefix-suffix boundary is pronounceable.

    Returns True if the join is phonotactically valid.
    """
    if not prefix or not suffix:
        return True

    # Find trailing consonants of prefix, leading consonants of suffix
    pfx = prefix.lower()
    sfx = suffix.lower()

    # Trailing consonants of prefix (cap at 2 — boundary cluster is at most 3 total)
    trail = ""
    for ch in reversed(pfx):
        if ch in CONSONANTS:
            trail = ch + trail
            if len(trail) >= 2:
                break
        else:
            break

    # Leading consonants of suffix (cap at 2)
    lead = ""
    for ch in sfx:
        if ch in CONSONANTS:
            lead += ch
            if len(lead) >= 2:
                break
        else:
            break

    boundary = trail + lead
    if len(boundary) <= 1:
        return True
    if len(boundary) == 2:
        return boundary in VALID_ONSET_CLUSTERS or boundary in VALID_CODA_CLUSTERS
    if len(boundary) == 3:
        # Triple onset (e.g. "str") OR coda(2)+onset(1) (e.g. "ng"+"k")
        if boundary in VALID_TRIPLE_ONSETS:
            return True
        coda2 = boundary[:2]
        onset1 = boundary[2]
        if coda2 in VALID_CODA_CLUSTERS and onset1 in CONSONANTS:
            return True
        # Also check coda(1)+onset(2)
        coda1 = boundary[0]
        onset2 = boundary[1:]
        if coda1 in CONSONANTS and onset2 in VALID_ONSET_CLUSTERS:
            return True
        return False
    if len(boundary) == 4:
        # coda(2)+onset(2) only
        coda2 = boundary[:2]
        onset2 = boundary[2:]
        return coda2 in VALID_CODA_CLUSTERS and onset2 in VALID_ONSET_CLUSTERS
    return False


def bad_ending(name: str) -> bool:
    """Check if the name ends with an awkward, non-pharmaceutical letter sequence."""
    name_lower = name.lower()
    for ending in BAD_ENDINGS:
        if name_lower.endswith(ending):
            return True
    return False
