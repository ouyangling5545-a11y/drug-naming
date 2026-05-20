# Molecular Structure Drawing for Stem Matching — Design Spec

**Goal:** Integrate a chemical structure editor (Ketcher) into Tab B「智能推荐」so users can draw molecular structures, auto-detect scaffolds and functional groups via RDKit, and feed structural features alongside target/mechanism info for more accurate INN stem matching.

**Architecture:** Ketcher iframe in browser → SMILES export → frontend quick preview (atom/ring count) + backend RDKit full analysis (Murcko scaffold, functional groups, ring systems, heteroatoms, chiral centers) → structural features fed into existing `StemMatcher` to enhance stem recommendations.

**Tech Stack:** Ketcher (open-source JS, EPAM), RDKit (Python cheminformatics), existing FastAPI + Vue.js SPA

---

## Architecture

```
Ketcher(前端 iframe)                    Python 后端
   │                                        │
   ├─ 用户绘制结构                           │
   ├─ molfile/SMILES 导出 (Ketcher API)      │
   ├─ 前端即时预览:                          │
   │   · 分子式 (Ketcher内置)                │
   │   · 原子计数/环数                       │
   │   · SMILES 字符串                       │
   │                                        │
   └─ [点击推荐] ───POST /api/structure/analyze──→
                  {smiles, target_class, mechanism,
                   chemical_class, indication}
                                            │
                                            ├─ RDKit 解析:
                                            │   · Murcko 骨架 → 骨架类型
                                            │   · 官能团检测 (SMARTS)
                                            │   · 环系识别 (单环/稠环/螺环)
                                            │   · 杂原子位置特征
                                            │   · 手性中心计数
                                            │
                                            ├─ 结构特征 + 靶点信息
                                            │   → 增强版 StemMatcher
                                            │
                  ←────── 返回 ──────────────┤
        {scaffold_type, functional_groups,
         ring_systems, heteroatom_info,
         recommended_stems}
```

## UI Layout (Tab B「智能推荐」)

```
┌─ 分子结构绘制 (新增) ──────────────────────────────────┐
│  ┌────────────────────────────────────────────────────┐ │
│  │              Ketcher iframe (~500x400px)           │ │
│  └────────────────────────────────────────────────────┘ │
│  SMILES: CC1=CC=C(C=C1)NC2=NC=NC3=CC=CC=C32            │
│  预览: C₂₀H₁₅ClN₄ | 喹唑啉骨架 | 含N杂环 | 1×-Cl     │
└──────────────────────────────────────────────────────────┘

┌─ 靶点信息 (现有表单，保留) ────────────────────────────┐
│  靶点: [EGFR ▼]  机制: [抑制剂 ▼]                      │
│  化学类别: [小分子 ▼]  适应症: [NSCLC]                 │
└──────────────────────────────────────────────────────────┘

[🔍 智能推荐词干]

┌─ 推荐结果 ────────────────────────────────────────────┐
│  ✅ -tinib  (EGFR+喹唑啉 → 匹配)                       │
│  ...                                                   │
└──────────────────────────────────────────────────────────┘
```

## Files

| Operation | File | Description |
|-----------|------|-------------|
| Create | `engines/structure_parser.py` | RDKit-based structure analysis engine |
| Modify | `engines/stem_matcher.py` | Accept structural features as additional input dimension |
| Create | `api/structure.py` | `/api/structure/analyze` endpoint |
| Modify | `static/index.html` | Tab B: integrate Ketcher iframe, SMILES display, frontend preview |
| Modify | `pyproject.toml` or `requirements.txt` | Add `rdkit` dependency |

## Data Flow

1. User draws structure in Ketcher iframe
2. Frontend calls Ketcher API `getSmiles()` + `getMolfile()` on demand
3. Frontend shows: molecular formula (from Ketcher), atom count, ring count (JS-level quick analysis)
4. On「智能推荐词干」click:
   - POST `/api/structure/analyze` with `{smiles, target_class, mechanism, chemical_class, indication}`
   - Backend runs RDKit analysis
   - Results merged into existing `PharmacologicalProperties` (fills `chemical_scaffold` field)
   - Enhanced `StemMatcher.match()` receives both target info AND scaffold/functional groups
   - Returns stem recommendations with match rationale

## Engine: `structure_parser.py`

```python
class StructureParser:
    def parse(self, smiles: str) -> StructureFeatures:
        """Full RDKit analysis of a molecular structure."""
        ...

class StructureFeatures:
    scaffold_type: str           # "quinazoline", "triazine", etc.
    murcko_smiles: str           # Murcko scaffold SMILES
    functional_groups: list[str]  # ["phenyl", "chloro", "methoxy", ...]
    ring_systems: list[RingInfo] # [{type: "fused", count: 2, atoms: [N,C...]}]
    heteroatoms: dict[str, int]  # {"N": 3, "O": 1, "Cl": 1}
    chiral_centers: int
    molecular_formula: str
    molecular_weight: float
```

## Stem Matching Enhancement

The structural features feed into the existing `StemMatcher.match()` method:

- `scaffold_type` → matches against scaffold-specific rules already in `KNOWN_RULES`
- `functional_groups` → disambiguates cases where same target has different stems based on chemistry
- `ring_systems` → helps identify complex polycyclic drugs

The existing `PharmacologicalProperties.chemical_scaffold` field, currently filled manually, will be auto-populated from the structure analysis.

## Dependencies

- **Frontend:** Ketcher v2.x (CDN: `https://unpkg.com/ketcher/dist/ketcher.standalone.js`)
- **Backend:** `rdkit` (pip install)

## Testing

- Unit tests for `StructureParser` with known SMILES → expected scaffolds
- Integration test: POST `/api/structure/analyze` with EGFR inhibitor structure → returns `-tinib` in recommended stems
- Manual test: Draw gefitinib-like structure, verify scaffold=quinazoline detected

## Out of Scope

- Full physicochemical property calculation (LogP, RO5, etc.)
- Structure similarity search against reference databases
- 3D conformer generation
- Reaction/retrosynthesis planning
