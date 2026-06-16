"""Consult API — intelligent query engine for drug naming data."""

from __future__ import annotations
import csv
import json
import re
from pathlib import Path
from typing import Any
from collections import defaultdict
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
_DATA_DIR = Path(__file__).parent.parent / "data"


# ═══ Shared: Chinese char → English syllable mapping (phonetically filtered) ═══

# Pinyin approximations for phonetic matching
_CHAR_PINYIN: dict[str, str] = {}
_py_raw = {
    '巴':'ba','贝':'bei','博':'bo','布':'bu','百':'bai','保':'bao','必':'bi','宾':'bin','波':'bo','白':'bai','班':'ban','邦':'bang','包':'bao','北':'bei','本':'ben','比':'bi','边':'bian','标':'biao','别':'bie','冰':'bing','伯':'bo','步':'bu','半':'ban',
    '帕':'pa','普':'pu','培':'pei','泊':'po','佩':'pei','皮':'pi','平':'ping','潘':'pan','彭':'peng','排':'pai','盘':'pan','旁':'pang','泡':'pao','配':'pei','盆':'pen','批':'pi','偏':'pian','漂':'piao','品':'pin','凭':'ping','破':'po','扑':'pu',
    '达':'da','德':'de','地':'di','度':'du','多':'duo','迪':'di','丹':'dan','登':'deng','丁':'ding','大':'da','代':'dai','带':'dai','单':'dan','但':'dan','党':'dang','导':'dao','到':'dao','道':'dao','得':'de','灯':'deng','等':'deng','低':'di','底':'di','第':'di','点':'dian','电':'dian','调':'diao','定':'ding','东':'dong','动':'dong','都':'dou','独':'du','读':'du','杜':'du','端':'duan','段':'duan','对':'dui','队':'dui','吨':'dun','盾':'dun','夺':'duo',
    '替':'ti','妥':'tuo','托':'tuo','他':'ta','特':'te','图':'tu','泰':'tai','坦':'tan','腾':'teng','天':'tian','通':'tong','塔':'ta','台':'tai','太':'tai','谈':'tan','弹':'tan','探':'tan','唐':'tang','堂':'tang','糖':'tang','躺':'tang','趟':'tang','讨':'tao','套':'tao','疼':'teng','提':'ti','题':'ti','体':'ti','田':'tian','甜':'tian','填':'tian','挑':'tiao','条':'tiao','跳':'tiao','铁':'tie','厅':'ting','听':'ting','庭':'ting','停':'ting','挺':'ting','同':'tong','铜':'tong','统':'tong','头':'tou','投':'tou','透':'tou','突':'tu','涂':'tu','土':'tu','团':'tuan','推':'tui','退':'tui','吞':'tun','屯':'tun','脱':'tuo','驼':'tuo',
    '格':'ge','加':'jia','戈':'ge','古':'gu','高':'gao','甘':'gan','盖':'gai','关':'guan','广':'guang','国':'guo','改':'gai','干':'gan','刚':'gang','钢':'gang','港':'gang','搞':'gao','告':'gao','哥':'ge','歌':'ge','革':'ge','各':'ge','个':'ge','给':'gei','根':'gen','跟':'gen','更':'geng','工':'gong','公':'gong','功':'gong','共':'gong','供':'gong','狗':'gou','够':'gou','构':'gou','购':'gou','估':'gu','姑':'gu','孤':'gu','谷':'gu','股':'gu','骨':'gu','故':'gu','顾':'gu','瓜':'gua','挂':'gua','怪':'guai','官':'guan','观':'guan','管':'guan','馆':'guan','冠':'guan','惯':'guan','灌':'guan','光':'guang','归':'gui','规':'gui','鬼':'gui','贵':'gui','滚':'gun','锅':'guo','过':'guo',
    '美':'mei','瑞':'rui','拉':'la','利':'li','米':'mi','莫':'mo','诺':'nuo','洛':'luo','那':'na','沙':'sha','索':'suo','维':'wei','西':'xi','卡':'ka','罗':'luo','依':'yi','奥':'ao','艾':'ai','司':'si','林':'lin','安':'an','尼':'ni','非':'fei','阿':'a','马':'ma','赛':'sai','莱':'lai','麦':'mai','福':'fu','乐':'le','生':'sheng','力':'li','万':'wan','奇':'qi','舒':'shu','宁':'ning','康':'kang','欣':'xin','悦':'yue','明':'ming','朗':'lang','阳':'yang','光':'guang','辉':'hui','盛':'sheng','隆':'long',
}
_CHAR_PINYIN = _py_raw

# Load and build the character→syllable map
_CHAR_MAP: dict[str, list[str]] = {}
_VS_DIR = Path(__file__).parent.parent.parent.parent / "vs"

def _build_char_map():
    global _CHAR_MAP
    if _CHAR_MAP:
        return

    char_raw: dict[str, list[str]] = defaultdict(list)

    # Load from VS mapping data
    map_file = _VS_DIR / "cn_char_to_eng_syllable.csv"
    if map_file.exists():
        with open(map_file) as f:
            for row in csv.DictReader(f):
                char = row['char']
                syls = row['eng_syllables'].split('|')
                py = _CHAR_PINYIN.get(char, '')
                # Phonetic filter: keep only matching syllables
                for s in syls:
                    if len(s) < 2: continue
                    if py and not _phonetic_match(s, py, char):
                        continue
                    char_raw[char].append(s)

    # Supplement from transliteration engine
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from drug_naming.engines.chinese_transliteration import SYLLABLE_TO_CHAR
        for eng_syl, cn_char in SYLLABLE_TO_CHAR:
            eng_lower = eng_syl.lower()
            if len(eng_lower) >= 2 and (cn_char not in char_raw or eng_lower not in char_raw[cn_char]):
                char_raw[cn_char].append(eng_lower)
    except Exception:
        pass

    # Deduplicate, sort
    for c in char_raw:
        unique = list(dict.fromkeys(char_raw[c]))
        unique.sort(key=lambda s: (len(s), s))
        _CHAR_MAP[c] = unique


def _phonetic_match(eng_syl: str, py: str, char: str) -> bool:
    """Check if English syllable phonetically matches the Chinese character's pinyin."""
    s = eng_syl.lower()
    if not py or not s: return False
    # Direct CV match: da matches da, dal, dan, dra
    if s[0] == py[0] and len(s) >= 2:
        return True
    # Consonant cluster: dra≈da
    if len(s) >= 3 and s[1] in 'rlh' and s[0] == py[0]:
        return True
    # Syllable ends with pinyin
    if len(py) >= 2 and s.endswith(py[:2]):
        return True
    return False


# Build on import
_build_char_map()


def _load_projects() -> list[dict]:
    with open(_DATA_DIR / "projects.json") as f:
        return json.load(f)


def _load_stems() -> list[dict]:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from drug_naming.data.stems import STEMS
    return [{
        "stem": s.stem, "position": str(s.position), "category": str(s.category),
        "meaning": s.meaning, "chinese": s.chinese,
        "target_classes": s.target_classes, "mechanisms": s.mechanisms,
        "chemical_classes": s.chemical_classes, "indications": s.indications,
        "examples": s.examples[:5], "who_definition": s.who_definition, "priority": s.priority,
    } for s in STEMS]


def _load_inn() -> list[dict]:
    with open(_DATA_DIR / "inn_reference.csv", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ── Tokenizer ──────────────────────────────────────────────────

_STOP_CHARS = set("的了是在不和与或带字名中文哪么什么吗呢吧个这也就会能可以及而但为因所被从对向把让用于到请问查找说有没出来去过着")

def _tokenize(text: str) -> list[str]:
    """Extract English words + individual Chinese characters (minus stop chars)."""
    tokens = re.findall(r'[a-zA-Z0-9]+', text.lower())
    for ch in text:
        if '一' <= ch <= '鿿' and ch not in _STOP_CHARS:
            tokens.append(ch)
    return tokens


# ── Models ─────────────────────────────────────────────────────

class ConsultRequest(BaseModel):
    query: str


class ConsultResult(BaseModel):
    type: str
    summary: str
    items: list[dict[str, Any]] = []
    source: str = ""


# ── Search: Projects ───────────────────────────────────────────

def search_projects(query: str) -> list[ConsultResult]:
    projects = _load_projects()
    tokens = _tokenize(query)
    ql = query.lower()
    results = []

    # Collect project-wide hits by scoring
    scored = []
    for p in projects:
        score = 0
        reasons = []
        pn = p["name"].lower()
        # Name match
        for t in tokens:
            if len(t) >= 2 and t in pn:
                score += 5; reasons.append(f"name={t}")
        # Status
        for t in tokens:
            if t == p.get("overall_status", ""):
                score += 3; reasons.append(f"status={t}")
        # Phase
        cp = p.get("current_phase", "")
        for t in tokens:
            if len(t) >= 2 and t in cp.lower():
                score += 2; reasons.append(f"phase={t}")
        # Search milestone results and names
        for ph in p.get("phases", []):
            for m in ph.get("milestones", []):
                r = (m.get("result") or "").lower()
                if r:
                    for t in tokens:
                        if t in r:
                            score += 4; reasons.append(f"result:{m['name']}={m['result']}")
                n = (m.get("name") or "").lower()
                for t in tokens:
                    if len(t) >= 2 and t in n:
                        score += 1; reasons.append(f"milestone={m['name']}")
        if score > 0:
            scored.append((score, reasons, p))
    scored.sort(key=lambda x: -x[0])

    # ── Specific query patterns ──

    # CAS query
    if any(w in ql for w in ("cas", "cas号", "cas号码", "登记号")):
        cas_hits = []
        for _, _, p in scored[:20] if scored else projects:
            cas_val = p.get("cas_number")
            for ph in p.get("phases", []):
                for m in ph.get("milestones", []):
                    if m["id"] == "cas_obtain" and m.get("result"):
                        cas_val = m["result"]
            if cas_val:
                cas_hits.append({"project": p["name"], "project_id": p["id"][:8], "cas_number": cas_val})
        if cas_hits:
            results.append(ConsultResult(type="list", summary=f"找到 {len(cas_hits)} 个有CAS号的项目", items=cas_hits, source="projects → cas_obtain"))

    # Chinese name query
    if any(w in query for w in ("中文名", "通用名", "中文", "名字", "带", "包含", "含有")):
        search_chars = [t for t in tokens if len(t) == 1]
        chin_hits = []
        for p in projects:
            for ph in p.get("phases", []):
                for m in ph.get("milestones", []):
                    if m["id"] == "pharm_approval" and m.get("result"):
                        name = m["result"]
                        if not search_chars or all(c in name for c in search_chars):
                            chin_hits.append({"project": p["name"], "project_id": p["id"][:8], "chinese_name": name, "status": m["status"], "planned_date": (m.get("planned_start") or "")[:10]})
        if chin_hits:
            chars_desc = "包含「" + "".join(search_chars) + "」的" if search_chars else ""
            results.append(ConsultResult(type="list", summary=f"找到 {len(chin_hits)} 个{chars_desc}中文名", items=chin_hits, source="projects → pharm_approval"))

    # INN query
    if any(w in ql for w in ("inn", "rinn", "pinn", "inn名")):
        inn_hits = []
        for p in projects:
            for ph in p.get("phases", []):
                for m in ph.get("milestones", []):
                    if m["id"] in ("inn_rinn", "inn_pinn_published") and m.get("result"):
                        inn_hits.append({"project": p["name"], "project_id": p["id"][:8], "milestone": m["name"], "inn_name": m["result"], "status": m["status"]})
        if inn_hits:
            results.append(ConsultResult(type="list", summary=f"找到 {len(inn_hits)} 个INN名记录", items=inn_hits, source="projects → inn"))

    # Trademark query
    if any(w in query for w in ("商标", "商品名", "品牌")):
        tm_hits = []
        for p in projects:
            for ph in p.get("phases", []):
                for m in ph.get("milestones", []):
                    if m["id"] == "tm_notice" and m.get("result"):
                        tm_hits.append({"project": p["name"], "project_id": p["id"][:8], "trademark": m["result"], "status": m["status"]})
        if tm_hits:
            results.append(ConsultResult(type="list", summary=f"找到 {len(tm_hits)} 个有商品名的项目", items=tm_hits, source="projects → tm_notice"))

    # NDA query
    if any(w in ql for w in ("nda", "nda申报", "nda递交", "申报日期")):
        nda_hits = []
        for p in projects:
            for ph in p.get("phases", []):
                for m in ph.get("milestones", []):
                    if m["id"] == "nda_submit" and m.get("planned_start"):
                        nda_hits.append({"project": p["name"], "project_id": p["id"][:8], "nda_date": m["planned_start"], "nda_顶层": p.get("nda_date", "")})
        if nda_hits:
            results.append(ConsultResult(type="list", summary=f"找到 {len(nda_hits)} 个NDA日期记录", items=nda_hits, source="projects → nda_submit"))

    # Project listing query
    if any(w in query for w in ("有哪些项目", "全部项目", "所有项目", "项目列表")):
        items = [{"project": p["name"], "project_id": p["id"][:8], "status": p.get("overall_status", ""), "current_phase": p.get("current_phase", ""), "nda_date": p.get("nda_date", "")} for p in projects]
        results.append(ConsultResult(type="list", summary=f"共 {len(items)} 个项目", items=items, source="projects"))

    # Broad project match: always include if scored
    if scored and not results:
        items = [{"project": p["name"], "project_id": p["id"][:8], "status": p.get("overall_status", ""), "current_phase": p.get("current_phase", ""), "matched_by": r} for _, r, p in scored[:10]]
        results.append(ConsultResult(type="list", summary=f"模糊匹配到 {len(items)} 个项目", items=items, source="projects"))

    return results


# ── Search: Stems ──────────────────────────────────────────────

def search_stems(query: str) -> list[ConsultResult]:
    stems = _load_stems()
    tokens = _tokenize(query)
    ql = query.lower()

    # Skip stems for clearly project-only queries
    _proj_only = {"cas", "cas号", "cas号码", "中文名", "商标", "商品名", "nda", "进展", "项目", "你好", "谢谢"}
    if any(p in ql for p in _proj_only):
        return []

    # Broad stem scoring — always run
    hits = []
    for s in stems:
        score = 0
        reasons = []
        st = s["stem"].lower().strip("-")
        for t in tokens:
            if len(t) >= 2:
                if t in st: score += 5; reasons.append("stem_match")
                if t in s.get("meaning", "").lower(): score += 3; reasons.append("meaning")
                for tc in s.get("target_classes", []):
                    if t in tc.lower(): score += 4; reasons.append(f"target={tc}")
                for mech in s.get("mechanisms", []):
                    if t in mech.lower(): score += 3; reasons.append(f"mechanism={mech}")
        for t in tokens:
            if len(t) == 1 and t in s.get("chinese", ""): score += 2; reasons.append("chinese_char")
        if score > 0:
            hits.append({**s, "_score": score, "_reasons": reasons})

    hits.sort(key=lambda x: (x["_score"], -len(x.get("stem", ""))), reverse=True)

    results = []
    if hits:
        items = [{"stem": s["stem"], "meaning": s["meaning"], "chinese": s["chinese"], "category": s["category"], "position": s["position"], "examples": s.get("examples", [])[:3], "target_classes": s.get("target_classes", []), "matched_by": s.get("_reasons", [])} for s in hits[:15]]
        results.append(ConsultResult(type="list", summary=f"找到 {len(items)} 个匹配的WHO词干", items=items, source="stems.csv"))
    return results


# ── Search: INN Reference ───────────────────────────────────────

def _get_stem_cn_texts() -> list[str]:
    """Extract Chinese stem texts from stems DB, sorted longest-first for greedy stripping."""
    stems = _load_stems()
    texts = set()
    for s in stems:
        cn = s.get("chinese", "").strip()
        if cn and len(cn) >= 1:
            texts.add(cn)
    return sorted(texts, key=len, reverse=True)


def _strip_stems(cn_name: str, stem_texts: list[str]) -> tuple[str, str]:
    """Return (prefix_part, stem_part) by stripping known Chinese stems."""
    remaining = cn_name
    stripped = ""
    for st in stem_texts:
        if st in remaining:
            remaining = remaining.replace(st, "", 1)
            stripped += st
    return remaining, stripped


def search_inn(query: str) -> list[ConsultResult]:
    """Search INN reference directly by keyword — no stem gating."""
    inn = _load_inn()
    tokens = _tokenize(query)
    ql = query.lower()

    # Chinese characters → search chinese field
    cn_chars = [t for t in tokens if len(t) == 1]
    # English tokens → search english + latin fields
    en_tokens = [t for t in tokens if len(t) >= 2]

    # If no meaningful tokens, skip
    if not cn_chars and not en_tokens:
        return []

    # Load stem texts for prefix-only matching
    stem_cn_texts = _get_stem_cn_texts()

    hits_full = []     # match anywhere in name
    hits_prefix = []   # match ONLY in prefix (excl. stem)
    for row in inn:
        cn = row.get("chinese", "")
        if not cn:
            continue
        lat = row.get("latin", "")
        eng = row.get("english", "")

        match_full = True
        # Chinese: must contain ALL searched characters
        if cn_chars:
            if not all(c in cn for c in cn_chars):
                match_full = False
        # English: match in english or latin field
        if en_tokens and match_full:
            combined = (eng + " " + lat).lower()
            if not any(t in combined for t in en_tokens):
                match_full = False

        if match_full:
            # For Chinese char search: only keep if match is in the PREFIX, not the stem
            if cn_chars:
                prefix, _ = _strip_stems(cn, stem_cn_texts)
                if prefix and any(c in prefix for c in cn_chars):
                    hits_prefix.append({"chinese": cn, "english": eng, "latin": lat, "cas": row.get("cas", "")})
            else:
                # English-only search: match directly in english/latin
                hits_full.append({"chinese": cn, "english": eng, "latin": lat, "cas": row.get("cas", "")})

    results = []
    if cn_chars:
        # Chinese search → only prefix matches (stem matches already shown by search_stems)
        if hits_prefix:
            desc = "前缀含「" + "+".join(cn_chars) + "」的"
            results.append(ConsultResult(
                type="list",
                summary=f"INN前缀匹配到 {len(hits_prefix)} 条{desc}名称（已排除词干含字）",
                items=hits_prefix[:200],
                source="inn_reference.csv",
            ))
    else:
        # English-only search
        if hits_full:
            desc = "含「" + " ".join(en_tokens) + "」的"
            results.append(ConsultResult(
                type="list",
                summary=f"INN库中匹配到 {len(hits_full)} 条{desc}名称",
                items=hits_full[:200],
                source="inn_reference.csv",
            ))

    return results

def _load_regulations() -> list[dict]:
    with open(_DATA_DIR / "regulations.json") as f:
        return json.load(f)


def search_regulations(query: str) -> list[ConsultResult]:
    """Search official drug naming regulations by keyword."""
    regs = _load_regulations()
    tokens = _tokenize(query)
    ql = query.lower()

    reg_patterns = ["法规", "政策", "规定", "制度", "规则", "条例", "条款",
                    "命名原则", "命名规则", "命名规范", "管理规范", "规范", "指南", "标准",
                    "流程", "怎么申请", "如何申请", "怎么办", "要求",
                    "药典委", "CDE", "NMPA", "WHO", "ICH", "核名", "申报", "商品名"]

    # Only search regulations if query hints at regulatory interest
    has_reg_hint = any(p in query for p in reg_patterns)
    # Also match if tokens match regulation keywords
    if not has_reg_hint:
        return []

    results = []
    for reg in regs:
        score = 0
        reasons = []
        # Match title
        for t in tokens:
            if len(t) >= 2 and t in reg.get("title", ""):
                score += 3; reasons.append("title")
        # Match keywords
        for kw in reg.get("keywords", []):
            for t in tokens:
                if len(t) >= 1 and t in kw:
                    score += 2
                    if "keyword" not in reasons: reasons.append("keyword")
        # Match clauses content
        for clause in reg.get("clauses", []):
            for t in tokens:
                if len(t) >= 2 and t in clause:
                    score += 1
                    if "clause" not in reasons: reasons.append("clause")

        if score > 0:
            results.append(ConsultResult(
                type="list",
                summary=f"「{reg['category']}」{reg['title']}",
                items=[{"clause": c} for c in reg["clauses"]],
                source=f"regulations → {reg['id']}",
            ))

    # Sort by most relevant (score from matched reasons, implicit)
    if results:
        # Deduplicate
        seen = set()
        unique = []
        for r in results:
            if r.summary not in seen:
                seen.add(r.summary)
                unique.append(r)
        return unique[:10]

    return []


# ── Route ─────────────────────────────────────────────────────

@router.post("/", response_model=dict)
def consult(body: ConsultRequest):
    query = body.query.strip()
    if not query:
        return {"query": "", "summary": "请输入问题。", "results": []}

    all_results: list[ConsultResult] = []

    # Run all engines
    all_results.extend(search_projects(query))
    stem_results = search_stems(query)
    all_results.extend(stem_results)
    all_results.extend(search_inn(query))
    all_results.extend(search_regulations(query))

    # Build summary
    if not all_results:
        # Universal fallback — always return project overview
        projects = _load_projects()
        overview = [{
            "project": p["name"],
            "status": p.get("overall_status", ""),
            "current_phase": p.get("current_phase", ""),
            "nda_date": p.get("nda_date", ""),
        } for p in projects]
        all_results.append(ConsultResult(
            type="list",
            summary=f"没有找到直接匹配「{query}」的结果。以下是全部 {len(overview)} 个项目的概况，你可以进一步追问：",
            items=overview,
            source="projects",
        ))

    total = sum(len(r.items) for r in all_results)
    parts = [f"• {r.summary}（来源：{r.source}）" for r in all_results]
    summary = "\n".join(parts)

    return {"query": query, "summary": summary, "results": [r.model_dump() for r in all_results]}
