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

# Antibody prefixes extracted from real -mab INN names (789 WHO-listed antibodies).
# These are real prefixes that have passed WHO scrutiny, providing a data-driven
# pool of 2-5 character prefixes for antibody name generation.
# Regenerate with: engines/name_generator.py _extract_antibody_prefixes()
ANTIBODY_PREFIXES_L1: list[str] = [
    "ab", "abago", "abela", "abi", "abri", "acapa", "actox", "adali",
    "aduca", "afase", "afeli", "alem", "aliro", "alnuc", "altu", "ama",
    "anivo", "anruk", "ansu", "apo", "apru", "ascri", "ase", "atezo",
    "atido", "atinu", "ave", "aviza", "axati", "azint", "bapin", "basi",
    "basr", "batoc", "bavi", "bectu", "bedin", "bege", "belan", "beli",
    "benra", "bepra", "berli", "berme", "beva", "bezlo", "bici", "bimag",
    "bime", "birta", "biva", "blese", "blo", "blont", "boco", "brazi",
    "briak", "broda", "brolu", "buro", "camre", "canak", "cap", "capla",
    "car", "caro", "catum", "ce", "cede", "cemip", "cenda", "cetre",
    "cevos", "cilga", "cinpa", "cirev", "claza", "cleno", "cobo",
    "codri", "cofe", "con", "cre", "crote", "crova", "cusa", "dac",
    "dace", "dafso", "dalo", "daxdi", "dectr", "dem", "deno", "depat",
    "detu", "deza", "dilpa", "dinu", "dirid", "disi", "domag", "dona",
    "dovan", "drozi", "dupi", "durva", "duvor", "ecro", "ecu", "edoba",
    "efa", "efung", "elde", "eleza", "elgem", "elipo", "elo", "emac",
    "emapa", "emi", "emibe", "enapo", "enava", "ence", "enli", "eno",
    "enoti", "ensi", "enuzo", "epitu", "epra", "epti", "er", "erenu",
    "ertum", "etara", "etese", "etigi", "eto", "etro", "evina", "evolo",
    "fari", "farle", "fasin", "fazpi", "fel", "fezak", "fian", "fiba",
    "ficla", "firiv", "fleti", "flote", "fonto", "fora", "frema",
    "frexa", "frovo", "frune", "fu", "fulra", "ga", "galca", "galeg",
    "ganco", "gani", "garet", "gatra", "gediv", "gem", "gevo", "gilve",
    "gimsi", "giren", "glofi", "goli", "gonti", "gremu", "gumo",
    "gusel", "iana", "iba", "icato", "icruc", "idac", "idaru", "ifabo",
    "ifina", "igo", "ilada", "ima", "imci", "imde", "imga", "imvo",
    "incla", "inebi", "ineze", "inf", "inoli", "ipili", "iratu", "isa",
    "isca", "iseca", "itepe", "ito", "ivuxo", "ixe", "izeni", "izura",
    "ke", "labe", "lacno", "lacu", "lampa", "lapri", "larca", "lebri",
    "leca", "lenda", "lenzi", "leron", "lesof", "letap", "leto", "levi",
    "lige", "lilo", "lin", "liri", "lodel", "lokiv", "losat", "lumi",
    "lumre", "lupar", "luti", "ma", "mafti", "magro", "mane", "marge",
    "masli", "mecbo", "melri", "mepo", "mibav", "mila", "miri",
    "mirve", "mirzo", "mitu", "modo", "mona", "morol", "mota", "nadec",
    "nami", "nara", "narna", "nata", "navic", "naviv", "naxi", "nebac",
    "nemo", "nesva", "neta", "nima", "nimo", "nirse", "nivo", "nuru",
    "obexe", "obilt", "obinu", "ocara", "ocre", "odesi", "oduli",
    "ofatu", "olara", "olec", "olo", "oma", "ombur", "onar", "ontux",
    "opici", "opuco", "orego", "ortic", "osemi", "oso", "oteli", "oti",
    "otler", "oxe", "oza", "ozora", "pacmi", "pagi", "pali", "panob",
    "parsa", "pasco", "pasot", "patec", "patri", "penpu", "pepi",
    "per", "pera", "pexe", "pidi", "pive", "placu", "plamo", "ploza",
    "pluta", "po", "poga", "porga", "posdi", "poze", "prasi", "preza",
    "pri", "prito", "pritu", "pulo", "qui", "radre", "ranev", "ranib",
    "ravu", "raxib", "refa", "relat", "relfo", "remto", "reoza", "res",
    "ri", "rinuc", "riper", "risan", "riva", "roled", "romil", "romo",
    "ronta", "rosni", "rove", "rozan", "rup", "saci", "sama", "samro",
    "sape", "sari", "sasan", "satra", "satu", "secuk", "setox",
    "setru", "sevi", "sibro", "sil", "sim", "sinti", "sip", "siruk",
    "sola", "soli", "son", "sotev", "sotro", "speso", "stamu", "su",
    "sule", "supta", "sutim", "suvra", "ta", "taba", "tabi", "tado",
    "tamtu", "tarco", "tarex", "tarla", "tavo", "tavol", "tefi",
    "teme", "tene", "tep", "tibu", "tidu", "tiga", "timo", "tirno",
    "tisle", "tiso", "toci", "tora", "tosat", "tove", "tralo", "tras",
    "trega", "tuvi", "ubama", "ubli", "unas", "upano", "upifi", "ure",
    "urtox", "ustek", "utomi", "vadas", "vana", "vanu", "vapa",
    "varis", "varli", "vate", "vedo", "vel", "vepsi", "vesen", "visi",
    "visug", "vofa", "volag", "volo", "vorse", "votu", "vuda", "vuna",
    "xen", "za", "zampi", "zanse", "zelmi", "zolbe",
]
