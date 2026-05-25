"""Sound-based Chinese transliteration for English drug names.

Produces Chinese character sequences that phonetically approximate
the English INN name, distinct from the combinatorial semantic-based
Chinese name generation in chinese_name.py.
"""

# Mapping of common English drug-name syllables to Chinese pharmaceutical characters.
# Ordered roughly longest-first so greedy matching picks specific stems over generic syllables.
SYLLABLE_TO_CHAR: list[tuple[str, str]] = [
    # Drug stem transliterations (long, highly specific)
    ("gliflozin", "格列净"),
    ("vastatin", "伐他汀"),
    ("gliptin", "格列汀"),
    ("ciclib", "西利"),
    ("parib", "帕利"),
    ("lisib", "利西"),
    ("tinib", "替尼"),
    ("sartan", "沙坦"),
    ("prazole", "拉唑"),
    ("coxib", "考昔"),
    ("milast", "司特"),
    ("lukast", "鲁司特"),
    ("setron", "司琼"),
    ("dipine", "地平"),
    ("navir", "那韦"),
    ("cillin", "西林"),
    ("cycline", "环素"),
    ("conazole", "康唑"),
    ("mycin", "霉素"),
    ("micin", "米星"),
    ("mab", "单抗"),
    ("grel", "格雷"),
    ("afil", "那非"),
    ("olol", "洛尔"),
    ("pril", "普利"),
    ("cept", "塞普"),
    ("platin", "铂"),
    ("fibrate", "贝特"),
    # Multi-character syllables
    ("stra", "司曲"), ("stro", "司曲"), ("stri", "司曲"),
    ("spra", "司普"), ("spro", "司普"),
    ("pho", "福"), ("phe", "非"), ("phi", "非"), ("pha", "法"),
    ("cha", "查"), ("che", "彻"), ("chi", "奇"), ("cho", "科"),
    ("sha", "沙"), ("she", "舍"), ("shi", "希"), ("sho", "肖"),
    ("tha", "沙"), ("the", "司"), ("thi", "西"), ("tho", "索"),
    ("wha", "瓦"), ("whe", "韦"), ("whi", "威"),
    ("bra", "布"), ("bre", "布"), ("bri", "布"), ("bro", "布罗"),
    ("cra", "克"), ("cre", "克"), ("cri", "克"), ("cro", "克罗"),
    ("dra", "德"), ("dre", "德"), ("dri", "德"), ("dro", "德罗"),
    ("fra", "夫"), ("fre", "夫"), ("fri", "夫"), ("fro", "夫罗"),
    ("gra", "格"), ("gre", "格"), ("gri", "格"), ("gro", "格罗"),
    ("pra", "普"), ("pre", "普"), ("pri", "普"), ("pro", "普罗"),
    ("tra", "曲"), ("tre", "曲"), ("tri", "曲"), ("tro", "曲"),
    # Additional common Chinese character syllables (reverse-lookup friendly)
    ("hao", "好"), ("hou", "侯"), ("gin", "近"), ("jin", "近"),
    ("xin", "新"), ("ning", "宁"), ("ping", "平"), ("tong", "通"),
    ("kang", "康"), ("jing", "静"), ("qing", "清"), ("ming", "明"),
    ("long", "隆"), ("hong", "宏"), ("sheng", "生"), ("cheng", "成"),
    ("dong", "东"), ("lian", "联"), ("rui", "瑞"), ("zhu", "珠"),
    # Two-letter consonant clusters
    ("bl", "布"), ("br", "布"), ("cl", "克"), ("cr", "克"),
    ("dr", "德"), ("fl", "夫"), ("fr", "夫"), ("gl", "格"),
    ("gr", "格"), ("pl", "普"), ("pr", "普"), ("tr", "曲"),
    ("sl", "司"), ("sm", "司"), ("sn", "司"), ("sp", "司"),
    ("st", "司"), ("sw", "司"), ("sk", "司"),
    # Single consonants + vowel (most common)
    ("ba", "巴"), ("be", "贝"), ("bi", "比"), ("bo", "博"), ("bu", "布"),
    ("ca", "卡"), ("ce", "塞"), ("ci", "西"), ("co", "科"), ("cu", "库"),
    ("da", "达"), ("de", "德"), ("di", "地"), ("do", "多"), ("du", "度"),
    ("fa", "法"), ("fe", "非"), ("fi", "非"), ("fo", "福"), ("fu", "氟"),
    ("ga", "加"), ("ge", "格"), ("gi", "吉"), ("go", "戈"), ("gu", "古"),
    ("ha", "哈"), ("he", "赫"), ("hi", "希"), ("ho", "霍"), ("hu", "胡"),
    ("ja", "贾"), ("je", "杰"), ("ji", "吉"), ("jo", "乔"), ("ju", "朱"),
    ("ka", "卡"), ("ke", "克"), ("ki", "基"), ("ko", "科"), ("ku", "库"),
    ("la", "拉"), ("le", "乐"), ("li", "利"), ("lo", "洛"), ("lu", "鲁"),
    ("ma", "马"), ("me", "美"), ("mi", "米"), ("mo", "莫"), ("mu", "姆"),
    ("na", "那"), ("ne", "奈"), ("ni", "尼"), ("no", "诺"), ("nu", "努"),
    ("pa", "帕"), ("pe", "培"), ("pi", "匹"), ("po", "泊"), ("pu", "普"),
    ("qua", "夸"), ("que", "奎"), ("qui", "奎"),
    ("ra", "拉"), ("re", "瑞"), ("ri", "利"), ("ro", "罗"), ("ru", "鲁"),
    ("sa", "沙"), ("se", "司"), ("si", "司"), ("so", "索"), ("su", "苏"),
    ("ta", "他"), ("te", "特"), ("ti", "替"), ("to", "托"), ("tu", "图"),
    ("va", "伐"), ("ve", "维"), ("vi", "维"), ("vo", "伏"), ("vu", "武"),
    ("wa", "瓦"), ("we", "韦"), ("wi", "威"), ("wo", "沃"), ("wu", "武"),
    ("ya", "亚"), ("ye", "耶"), ("yi", "伊"), ("yo", "约"), ("yu", "尤"),
    ("za", "扎"), ("ze", "泽"), ("zi", "齐"), ("zo", "佐"), ("zu", "足"),
    # Vowels at word start
    ("a", "阿"), ("e", "厄"), ("i", "伊"), ("o", "奥"), ("u", "乌"),
    # Terminal single letters (rarely reached)
    # Terminal / standalone consonants
    ("b", "布"), ("c", "克"), ("d", "德"), ("f", "夫"), ("g", "格"),
    ("h", ""), ("j", ""), ("k", "克"), ("l", "尔"), ("m", "姆"),
    ("n", "恩"), ("p", "普"), ("q", "克"), ("r", "尔"), ("s", "司"),
    ("t", "特"), ("v", "夫"), ("w", "夫"), ("x", "司"), ("y", "伊"),
    ("z", "兹"),
]

CHINESE_DRUG_FORBIDDEN: frozenset[str] = frozenset({
    "神", "仙", "灵", "宝", "圣", "王", "皇", "霸", "绝", "奇",
    "最", "第", "首", "冠", "金", "银", "钻",
})


def transliterate_to_chinese(english_name: str) -> str:
    """Convert an English drug name to Chinese via greedy longest-match syllable mapping.

    Scans left-to-right, matching the longest syllable from the table at each position.
    Characters that cannot be matched are passed through unchanged.
    """
    name = english_name.strip().lower()
    result = ""
    pos = 0
    while pos < len(name):
        matched = False
        for syllable, char in SYLLABLE_TO_CHAR:
            if name.startswith(syllable, pos):
                result += char
                pos += len(syllable)
                matched = True
                break
        if not matched:
            result += name[pos]
            pos += 1
    return result


def check_chinese_transliteration_taboo(transliteration: str) -> list[str]:
    """Check for forbidden characters in a Chinese transliteration."""
    flags = []
    for ch in transliteration:
        if ch in CHINESE_DRUG_FORBIDDEN:
            flags.append(f"forbidden_character:{ch}")
    return flags


# ── Chinese → Latin reverse index for prefix matching ─────────────────────
# Used by the recommendation engine to find Latin prefixes whose Chinese
# transliteration matches a user-specified hint character.

_CN_TO_LATIN = None  # type: dict[str, list[str]] | None → Optional[dict] for py3.9 compat; re-assigned lazily by get_cn_latin_index()


def _build_cn_latin_index() -> dict[str, list[str]]:
    """Build Chinese character → Latin syllable reverse index."""
    from collections import defaultdict
    idx: dict[str, list[str]] = defaultdict(list)
    for syllable, char in SYLLABLE_TO_CHAR:
        for c in char:
            idx[c].append(syllable)
    return dict(idx)


def get_cn_latin_index() -> dict[str, list[str]]:
    """Lazily build and return the Chinese→Latin reverse index."""
    global _CN_TO_LATIN
    if _CN_TO_LATIN is None:
        _CN_TO_LATIN = _build_cn_latin_index()
    return _CN_TO_LATIN


def latin_prefixes_for_chinese(hint: str) -> list[str]:
    """Return Latin prefix candidates whose Chinese transliteration matches `hint`.

    Three-tier lookup:
    1. Data-driven mapping from 12K English-Chinese INN name pairs (most accurate)
    2. Reverse index from SYLLABLE_TO_CHAR transliteration table
    3. PFX_ALTERNATES from poca module

    Example: hint="吉" → returns ["gi", "ge", "gem", ...] from INN data
             hint="曲" → returns ["tri", "tra", "tre", ...] from INN data
    """
    results: list[str] = []

    # Tier 1: Data-driven mapping (from INN corpus)
    try:
        from ..data.cn_eng_prefixes import CN_TO_ENG_PREFIXES
    except ImportError:
        CN_TO_ENG_PREFIXES = {}

    for ch in hint:
        for pfx in CN_TO_ENG_PREFIXES.get(ch, []):
            if pfx not in results:
                results.append(pfx)

    # Tier 2: Existing reverse index (SYLLABLE_TO_CHAR → CN_TO_LATIN)
    idx = get_cn_latin_index()
    for ch in hint:
        for syl in idx.get(ch, []):
            if len(syl) <= 4 and syl not in results:
                results.append(syl)

    # Tier 3: PFX alternates for richer coverage
    try:
        from ..api.poca import _PFX_ALTERNATES as pfx_alt
    except ImportError:
        pfx_alt = {}
    for syl, chars in pfx_alt.items():
        for ch in hint:
            if ch in chars and syl not in results:
                results.append(syl)

    # Tier 4: Pinyin fallback for characters not in any mapping
    if not results:
        try:
            from pypinyin import pinyin, Style
            for ch in hint:
                py_list = pinyin(ch, style=Style.NORMAL)
                for p in py_list:
                    py_syl = p[0]
                    if py_syl and len(py_syl) >= 1 and py_syl not in results:
                        results.append(py_syl)
        except ImportError:
            pass

    return results
