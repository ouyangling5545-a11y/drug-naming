"""One-shot script: build Chinese→English prefix mapping from INN data.

Extracts Chinese character → English prefix candidate mappings from
~12,400 English-Chinese INN name pairs via proportional window alignment.
Includes stem-level mappings from stems.csv for additional coverage.

Usage:
    python tools/build_cn_eng_map.py

Output:
    src/drug_naming/data/cn_eng_prefixes.py
"""
import csv, json, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

CSV_PATH = ROOT / "src/drug_naming/data/inn_reference.csv"
OUT_PATH = ROOT / "src/drug_naming/data/cn_eng_prefixes.py"
VOWELS = set("aeiou")


def main():
    # ── 1. Load English-Chinese pairs ──
    pairs = []
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            eng = row["english"].strip().lower()
            cn = row["chinese"].strip()
            if eng and cn and len(cn) >= 2 and len(eng) >= 3:
                pairs.append((eng, cn))
    print(f"Loaded {len(pairs)} English-Chinese pairs")

    # ── 2. Helper ──
    def extract_prefixes(sub):
        results = []
        for j in range(len(sub)):
            for l in [2, 3, 4, 5]:
                if j + l <= len(sub):
                    ngram = sub[j:j + l]
                    if ngram[0] in VOWELS:
                        continue
                    if any(ch in VOWELS for ch in ngram):
                        results.append(ngram)
        return results

    # ── 3. Window-based extraction ──
    cn_to_raw = defaultdict(list)
    for eng, cn in pairs:
        n = len(cn)
        m = len(eng)
        if n == 0:
            continue
        for i, char in enumerate(cn):
            start = max(0, int(i * m / n) - 1)
            end = min(m, int((i + 1) * m / n) + 1) if i < n - 1 else m
            for pfx in extract_prefixes(eng[start:end]):
                cn_to_raw[char].append(pfx)

    # ── 4. Stem data ──
    try:
        from drug_naming.data.stems import get_all
        for s in get_all():
            stem = s.stem.strip("-")
            cn = s.chinese
            if stem and cn:
                for l in [2, 3, 4, 5]:
                    if len(stem) >= l:
                        pfx = stem[:l]
                        if any(v in VOWELS for v in pfx) and pfx[0] not in VOWELS:
                            for ch in cn:
                                cn_to_raw[ch].append(pfx)
        print("Loaded stem mappings")
    except Exception as e:
        print(f"Stem warning: {e}")

    # ── 5. Aggregate: freq >= 1, top 20 per char ──
    char_mappings = {}
    for char, prefixes in cn_to_raw.items():
        freq = defaultdict(int)
        for pfx in prefixes:
            clean = pfx.lower().strip("-")
            # Reject non-alpha chars (spaces, digits, punctuation from window boundaries)
            if not clean.isalpha():
                continue
            if 2 <= len(clean) <= 5 and any(ch in VOWELS for ch in clean) and clean[0] not in VOWELS:
                freq[clean] += 1

        ranked = [(e, c) for e, c in sorted(freq.items(), key=lambda x: -x[1])]
        if ranked:
            char_mappings[char] = [e for e, c in ranked[:20]]

    # ── 6. Write Python module ──
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write('"""Data-driven Chinese character → English prefix mapping.\n')
        f.write(f'Auto-extracted from {len(pairs):,} English-Chinese INN name pairs.\n')
        f.write(f'Covers {len(char_mappings)} Chinese characters with {sum(len(v) for v in char_mappings.values())} prefix entries.\n')
        f.write('Regenerate via: python tools/build_cn_eng_map.py\n')
        f.write('"""\n\n')
        f.write('from __future__ import annotations\n')
        f.write('\n')
        f.write('# Chinese character → list of English prefix candidates (ranked by frequency)\n')
        f.write('CN_TO_ENG_PREFIXES: dict[str, list[str]] = {\n')
        for char in sorted(char_mappings.keys()):
            prefixes = char_mappings[char]
            pfxs_str = json.dumps(prefixes, ensure_ascii=False)
            f.write(f'    {json.dumps(char, ensure_ascii=False)}: {pfxs_str},\n')
        f.write('}\n')

    total = sum(len(v) for v in char_mappings.values())
    print(f"\nWritten {len(char_mappings)} characters, {total} prefix entries")
    print(f"Output: {OUT_PATH}")

    # Quality spot-check
    for ch in ["吉", "迈", "西", "韦", "康", "近", "宁", "新", "清", "珠"]:
        if ch in char_mappings:
            print(f"  {ch} → {char_mappings[ch][:6]}")
        else:
            print(f"  {ch} → MISSING")


if __name__ == "__main__":
    main()
