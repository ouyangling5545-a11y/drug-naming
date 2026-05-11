"""
Double Metaphone algorithm — Python implementation.

Ported from the public-domain C++ reference by Lawrence Philips (1999).
Used by FDA POCA methodology for phonetic similarity scoring of drug names.

Returns (primary, secondary) encodings for each input string.
"""

VOWELS = frozenset("AEIOUY")


def double_metaphone(value: str) -> tuple[str, str]:
    """Return (primary_code, secondary_code) Double Metaphone encodings."""
    if not value:
        return "", ""

    primary = _Metaphone()
    secondary = _Metaphone()
    current = 0
    length = len(value)

    # Work with uppercase
    word = value.upper()
    last = length - 1

    # Skip if input is too short
    if length < 2:
        primary.add(word)
        secondary.add(word)
        return str(primary), str(secondary)

    # Pad with spaces for lookahead safety — original uses 4 pad columns
    original = word
    word += "     "

    # -- Slavo-Germanic flag --
    slavo_germanic = (
        original.find("W") != -1
        or original.find("K") != -1
        or original.find("CZ") != -1
        or original.find("WITZ") != -1
    )

    # -- Initial exceptions --
    # Skip these when building encodings
    _initial_silent = False

    # GN, KN, PN, WR, PS → drop first letter
    if word[:2] in ("GN", "KN", "PN", "WR", "PS"):
        current += 1

    # Initial X → encode as S
    if word[0] == "X":
        primary.add("S")
        secondary.add("S")
        current += 1

    # Vowel at start
    _vowel_start = word[0] in VOWELS

    # Initial WH → encode W if not Slavo-Germanic
    if word[:2] == "WH":
        if word[2] in VOWELS and not slavo_germanic:
            primary.add("A")
            secondary.add("A")
        current += 1

    # Main loop
    while current < length:
        ch = word[current]

        if ch in VOWELS:
            current = _handle_vowel(word, current, primary, secondary)
        elif ch == " ":
            current += 1
        elif ch == "B":
            _handle_char(primary, secondary, "P", "P")
            current += 1
            if word[current] == "B":
                current += 1
        elif ch == "C":
            current = _handle_c(word, current, primary, secondary)
        elif ch == "D":
            current = _handle_d(word, current, primary, secondary)
        elif ch == "F":
            _handle_char(primary, secondary, "F", "F")
            current += 1
            if word[current] == "F":
                current += 1
        elif ch == "G":
            current = _handle_g(word, current, primary, secondary, slavo_germanic)
        elif ch == "H":
            current = _handle_h(word, current, primary, secondary)
        elif ch == "J":
            current = _handle_j(word, current, primary, secondary)
        elif ch == "K":
            _handle_char(primary, secondary, "K", "K")
            current += 1
            if word[current] == "K":
                current += 1
        elif ch == "L":
            current = _handle_l(word, current, primary, secondary)
        elif ch == "M":
            _handle_char(primary, secondary, "M", "M")
            current += 1
            if word[current] == "M":
                current += 1
        elif ch == "N":
            _handle_char(primary, secondary, "N", "N")
            current += 1
            if word[current] == "N":
                current += 1
        elif ch == "P":
            current = _handle_p(word, current, primary, secondary)
        elif ch == "Q":
            _handle_char(primary, secondary, "K", "K")
            current += 1
            if word[current] == "Q":
                current += 1
        elif ch == "R":
            current = _handle_r(word, current, primary, secondary, slavo_germanic)
        elif ch == "S":
            current = _handle_s(word, current, primary, secondary, slavo_germanic)
        elif ch == "T":
            current = _handle_t(word, current, primary, secondary)
        elif ch == "V":
            _handle_char(primary, secondary, "F", "F")
            current += 1
            if word[current] == "V":
                current += 1
        elif ch == "W":
            current = _handle_w(word, current, primary, secondary)
        elif ch == "X":
            current = _handle_x(word, current, primary, secondary)
        elif ch == "Z":
            current = _handle_z(word, current, primary, secondary, slavo_germanic)
        else:
            current += 1

        if primary.length >= 4 and secondary.length >= 4:
            break

    return str(primary), str(secondary)


class _Metaphone:
    def __init__(self) -> None:
        self._buf: list[str] = []
        self.length = 0

    def add(self, s: str) -> None:
        self._buf.append(s)
        self.length += len(s)

    def add_primary_secondary(self, primary_val: str, secondary_val: str, is_primary: bool) -> None:
        self.add(primary_val if is_primary else secondary_val)

    def __str__(self) -> str:
        return "".join(self._buf)[:4]


def _handle_char(primary: _Metaphone, secondary: _Metaphone, p_val: str, s_val: str) -> None:
    primary.add(p_val)
    secondary.add(s_val)


def _handle_vowel(word: str, current: int, primary: _Metaphone, secondary: _Metaphone) -> int:
    """Vowel at start → encode 'A', otherwise skip."""
    if current == 0:
        primary.add("A")
        secondary.add("A")
    return current + 1


def _handle_c(word: str, current: int, primary: _Metaphone, secondary: _Metaphone) -> int:
    """C → K or S depending on context."""
    # CIA, CIO, CIT, CIE → X (KS)
    if current >= 1 and word[current - 1] == "S" and word[current + 1 : current + 3] in ("IA", "IO", "IT", "IE"):
        primary.add("X")
        if word[current + 1 : current + 3] in ("IA", "IO", "IT"):
            secondary.add("X")
        current += 3
        return current

    # CH → various
    if word[current + 1] == "H":
        # CHAE, CHIA → K
        if current == 0 and word[current + 2 : current + 4] in ("AE", "IA"):
            primary.add("K")
            secondary.add("K")
            current += 2
            return current
        # Michael → K, KS
        if word[current - 2 : current] == "MI" and word[current - 1] == "I":
            primary.add("X")
            secondary.add("X")
            current += 2
            return current
        if current == 0 and word[:2] == "CH":
            primary.add("K")
            secondary.add("K")
            current += 2
            return current
        if current > 0 and word[current - 2 : current] == "AC":
            primary.add("K")
            secondary.add("K")
            current += 2
            return current
        # Germanic / Slavic: SCH, etc → X or K
        if current > 1 and word[current - 2 : current] in ("UC", "OC", "IC", "EC", "NC", "RC"):
            primary.add("K")
            secondary.add("K")
            current += 2
            return current
        primary.add("X")
        secondary.add("K")
        current += 2
        return current

    # CI, CE, CY → S
    if word[current + 1] in ("I", "E", "Y"):
        primary.add("S")
        secondary.add("S")
        current += 2
        return current

    # CZ → first C silent
    if word[current + 1] == "Z" and word[current - 2 : current] != "WI":
        primary.add("S")
        secondary.add("S")
        current += 2
        return current

    # CC with vowel → KS
    if word[current + 1] == "C":
        if current < 1 or word[current - 1] not in ("M", "N", "R"):
            if word[current + 2] in ("I", "E", "H") and word[current + 2 : current + 4] != "HU":
                primary.add("X")
                secondary.add("X")
                current += 3
                return current
        primary.add("K")
        secondary.add("K")
        current += 2
        return current

    # CK, CG, CQ → K
    if word[current + 1] in ("K", "G", "Q"):
        primary.add("K")
        secondary.add("K")
        current += 2
        return current

    # Default C → K
    primary.add("K")
    secondary.add("K")
    current += 1
    return current


def _handle_d(word: str, current: int, primary: _Metaphone, secondary: _Metaphone) -> int:
    """D → T or J depending on context."""
    # DGE, DGI, DGY → J
    if word[current + 1] == "G" and word[current + 2] in ("E", "I", "Y"):
        primary.add("J")
        secondary.add("J")
        current += 3
        return current
    # DT, DD → T
    if word[current + 1] in ("T", "D"):
        primary.add("T")
        secondary.add("T")
        current += 2
        return current
    primary.add("T")
    secondary.add("T")
    current += 1
    return current


def _handle_g(word: str, current: int, primary: _Metaphone, secondary: _Metaphone, slavo_germanic: bool) -> int:
    """G → K or J depending on context."""
    next_ch = word[current + 1]
    # GH → various
    if next_ch == "H":
        return _handle_gh(word, current, primary, secondary)

    # GN, GNED → N
    if next_ch == "N":
        if current == 0:
            primary.add("K")
            secondary.add("N")
            current += 1
            return current
        if word[current + 2 : current + 4] == "EY" or next_ch == "Y" or not slavo_germanic:
            primary.add("K")
            secondary.add("N")
            current += 2
            return current
        primary.add("K")
        secondary.add("K")
        current += 2
        return current

    # GLI → L or KL
    if next_ch == "L" and word[current + 2] in ("I", "Y"):
        if current == 0:
            primary.add("K")
            secondary.add("L")
            current += 2
            return current
        primary.add("K")
        secondary.add("K")
        current += 2
        return current

    # GER, GERY, GES, GET, GE, GI, GY → J
    if current > 0 or next_ch not in ("E", "I", "Y"):
        if next_ch in ("E", "I", "Y") or (next_ch == "G" and word[current + 2] == "E"):
            primary.add("J")
            secondary.add("J")
            current += 2
            return current

    # GG → K
    if next_ch == "G":
        primary.add("K")
        secondary.add("K")
        current += 1
        return current

    # Default G → K
    primary.add("K")
    secondary.add("K")
    current += 1
    return current


def _handle_gh(word: str, current: int, primary: _Metaphone, secondary: _Metaphone) -> int:
    """Handle 'GH' digraph."""
    # GH at end or before consonant
    if word[current + 2] not in VOWELS and word[current + 2] != " ":
        if current > 0:
            if word[current - 2 : current] in ("OU", "AU"):
                primary.add("K")
                secondary.add("K")
            current += 2
            return current
        current += 2
        return current

    # GH at start → G (K)
    if current == 0:
        next2 = word[current + 2]
        if next2 in ("E", "I", "Y"):
            primary.add("J")
            secondary.add("J")
        elif next2 == " ":
            primary.add("K")
            secondary.add("K")
        else:
            primary.add("K")
            secondary.add("K")
        current += 2
        return current

    # Vowel before GH → silent
    current += 2

    # Exception: B.GH, H.GH → K
    if current >= 2:
        before = word[current - 3]
        if before in ("B", "H", "D"):
            primary.add("K")
            secondary.add("K")
        elif before == "G":
            primary.add("K")
            secondary.add("K")

    return current


def _handle_h(word: str, current: int, primary: _Metaphone, secondary: _Metaphone) -> int:
    """H → silent between vowels, otherwise silent."""
    # Skip if between vowels or after vowel at end
    if (current > 0 and word[current - 1] in VOWELS) and (
        word[current + 1] in VOWELS or word[current + 1] == " "
    ):
        current += 1
        return current
    current += 1
    return current


def _handle_j(word: str, current: int, primary: _Metaphone, secondary: _Metaphone) -> int:
    """J → J or H."""
    # J at start or after vowel → J, secondary A (Spanish)
    if word[current + 1] == "J":
        primary.add("J")
        secondary.add("J")
        current += 2
        return current
    # JOSE → H at start
    if current == 0 and word[current : current + 4] == "JOSE":
        primary.add("H")
        secondary.add("H")
        current += 4
        return current
    # SAN JACINTO → H
    if current == 0 and word[current : current + 3] == "JAC":
        primary.add("H")
        secondary.add("H")
        current += 3
        return current
    # Spanish J → H
    if current > 0 and word[current - 1] in VOWELS and not slavo_germanic_surrounding(word, current):
        if word[current + 1] in VOWELS:
            primary.add("J")
            secondary.add("H")
            current += 1
            return current
    # General → J
    if current > 0 or word[current + 1] in VOWELS:
        primary.add("J")
        secondary.add("J")
        current += 1
        return current
    primary.add("J")
    secondary.add("J")
    current += 1
    return current


def _handle_l(word: str, current: int, primary: _Metaphone, secondary: _Metaphone) -> int:
    """LL → L if at end or before consonant."""
    if word[current + 1] == "L":
        next2 = word[current + 2]
        if next2 == " " or next2 not in VOWELS:
            primary.add("L")
            secondary.add("L")
            current += 2
            return current
        # LL + vowel → L
        primary.add("L")
        secondary.add("L")
        current += 2
        return current
    primary.add("L")
    secondary.add("L")
    current += 1
    return current


def _handle_p(word: str, current: int, primary: _Metaphone, secondary: _Metaphone) -> int:
    """PH → F, PB → P."""
    if word[current + 1] == "H":
        primary.add("F")
        secondary.add("F")
        current += 2
        return current
    if word[current + 1] == "B":
        primary.add("P")
        secondary.add("P")
        current += 2
        return current
    if word[current + 1] == "P":
        primary.add("P")
        secondary.add("P")
        current += 2
        return current
    primary.add("P")
    secondary.add("P")
    current += 1
    return current


def _handle_r(word: str, current: int, primary: _Metaphone, secondary: _Metaphone, slavo_germanic: bool) -> int:
    """R → R or silent in some contexts."""
    # RR → R
    if word[current + 1] == "R":
        primary.add("R")
        secondary.add("R")
        current += 2
        return current
    # Final R silent in French-like endings
    if current == len(word.strip()) - 1 and current > 1:
        before = word[current - 2 : current]
        if before in ("IE", "UE", "OE", "AE", "EE"):
            # Keep R in primary only
            primary.add("R")
            current += 1
            return current
    primary.add("R")
    secondary.add("R")
    current += 1
    return current


def _handle_s(word: str, current: int, primary: _Metaphone, secondary: _Metaphone, slavo_germanic: bool) -> int:
    """S → S or X depending on context."""
    # SIO, SIA → X or S
    if word[current + 1 : current + 3] in ("IO", "IA"):
        if slavo_germanic:
            primary.add("S")
            secondary.add("S")
        else:
            primary.add("X")
            secondary.add("X")
        current += 3
        return current

    # SH → X
    if word[current + 1] == "H":
        primary.add("X")
        secondary.add("X")
        current += 2
        return current

    # SZ → X or S
    if word[current + 1] == "Z":
        primary.add("X")
        secondary.add("S")
        current += 2
        return current

    # SC → S or SK
    if word[current + 1] == "C":
        if word[current + 2] in ("I", "E", "Y"):
            primary.add("S")
            secondary.add("S")
            current += 3
            return current
        primary.add("S")
        secondary.add("K")
        current += 2
        return current

    # SS → S
    if word[current + 1] == "S":
        primary.add("S")
        secondary.add("S")
        current += 2
        return current

    # Default S
    if current == 0:
        primary.add("S")
        secondary.add("S")
        current += 1
        return current
    primary.add("S")
    secondary.add("S")
    current += 1
    return current


def _handle_t(word: str, current: int, primary: _Metaphone, secondary: _Metaphone) -> int:
    """T → T or X depending on context."""
    # TIO, TIA → X
    if word[current + 1 : current + 3] in ("IO", "IA"):
        primary.add("X")
        secondary.add("X")
        current += 3
        return current

    # TCH → X
    if word[current + 1] == "C" and word[current + 2] == "H":
        primary.add("X")
        secondary.add("X")
        current += 3
        return current

    # TH → T or 0
    if word[current + 1] == "H":
        if word[current + 2 : current + 4] in ("OM", "AM"):
            primary.add("T")
            secondary.add("T")
        elif current == 0 or word[current - 2 : current] in ("T", "D"):
            primary.add("T")
            secondary.add("T")
        else:
            primary.add("0")
            secondary.add("T")
        current += 2
        return current

    # TT → T
    if word[current + 1] == "T":
        primary.add("T")
        secondary.add("T")
        current += 2
        return current

    primary.add("T")
    secondary.add("T")
    current += 1
    return current


def _handle_w(word: str, current: int, primary: _Metaphone, secondary: _Metaphone) -> int:
    """W → silent or W."""
    # WR → R
    if word[current + 1] == "R":
        primary.add("R")
        secondary.add("R")
        current += 2
        return current

    # W at start with vowel → A
    if current == 0:
        if word[current + 1] in VOWELS:
            primary.add("A")
            secondary.add("F")
            current += 1
            return current

    # W as part of vowel diagraph → silent
    if word[current - 2 : current] in ("EW", "OW", "AW") and word[current + 1] in VOWELS:
        current += 1
        return current

    # Default: silent
    current += 1
    return current


def _handle_x(word: str, current: int, primary: _Metaphone, secondary: _Metaphone) -> int:
    """X → KS."""
    # X at start → S
    if current == 0:
        primary.add("S")
        secondary.add("S")
        current += 1
        return current
    # X after vowel AU or OU → KS
    if current > 0 and word[current - 1] in VOWELS:
        primary.add("K")
        secondary.add("K")
        primary.add("S")
        secondary.add("S")
        current += 1
        return current
    # X → KS
    primary.add("K")
    secondary.add("K")
    primary.add("S")
    secondary.add("S")
    current += 1
    return current


def _handle_z(word: str, current: int, primary: _Metaphone, secondary: _Metaphone, slavo_germanic: bool) -> int:
    """Z → S or TS."""
    # Z at end → S
    if word[current + 1] == " ":
        primary.add("S")
        secondary.add("S")
        current += 1
        return current

    # ZO, ZA, ZI → S
    if word[current + 1] in ("O", "A", "I"):
        if slavo_germanic:
            primary.add("T")
            secondary.add("T")
            primary.add("S")
            secondary.add("S")
        else:
            primary.add("S")
            secondary.add("S")
        current += 2
        return current

    # ZZ → S
    if word[current + 1] == "Z":
        primary.add("S")
        secondary.add("S")
        current += 2
        return current

    primary.add("S")
    secondary.add("S")
    current += 1
    return current


def _has_vowel(word: str, start: int, end: int) -> bool:
    """Check if substring contains a vowel."""
    for i in range(max(start, 0), min(end, len(word))):
        if word[i] in VOWELS:
            return True
    return False


def slavo_germanic_surrounding(word: str, current: int) -> bool:
    """Check surrounding context for Slavo-Germanic patterns."""
    if current > 0 and word[current - 1] in ("C", "G", "K", "Q", "S", "X", "Z"):
        return True
    if current > 1 and word[current - 2] == "S" and word[current - 1] == "K":
        return True
    return False
