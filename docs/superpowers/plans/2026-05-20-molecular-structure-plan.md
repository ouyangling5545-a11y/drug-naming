# Molecular Structure Drawing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate Ketcher chemical structure editor into Tab B「智能推荐」, parse drawn structures via RDKit, and feed structural features (scaffold type, functional groups, ring systems) into the existing stem matcher for more accurate INN stem recommendations.

**Architecture:** Ketcher iframe → SMILES export → POST /api/structure/analyze → RDKit Murcko scaffold + SMARTS functional group detection → enhanced StemMatcher with scaffold-aware rules. Frontend shows Ketcher above the existing form; structural features auto-populate the chemical_scaffold field.

**Tech Stack:** Ketcher 2.x (CDN), RDKit (pip), existing FastAPI + Vue.js SPA

---

## File Structure

| File | Role |
|------|------|
| `engines/structure_parser.py` (create) | RDKit analysis: scaffold, functional groups, rings, heteroatoms, chirality |
| `engines/stem_matcher.py` (modify) | Accept `StructureFeatures` in `match()`, add scaffold→stem rules to KNOWN_RULES |
| `api/structure.py` (create) | POST `/api/structure/analyze` endpoint |
| `api/router.py` (modify) | Register structure router |
| `static/index.html` (modify) | Tab B: Ketcher iframe + SMILES preview + wire to recommend button |
| `pyproject.toml` (modify) | Add `rdkit` dependency |

---

### Task 1: Add RDKit dependency

**Files:**
- Modify: `pyproject.toml:10-18`

- [ ] **Step 1: Add rdkit to dependencies**

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "jellyfish>=1.0.0",
    "pypinyin>=0.50.0",
    "eval_type_backport>=0.2.0",
    "rdkit>=2023.9.0",
]
```

- [ ] **Step 2: Install rdkit and verify**

Run: `pip install rdkit>=2023.9.0`
Then: `python3 -c "from rdkit import Chem; print('RDKit', Chem.rdkitVersion)"`
Expected: `RDKit 2024.09.1` or similar.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add rdkit dependency for molecular structure parsing"
```

---

### Task 2: Create structure_parser.py engine

**Files:**
- Create: `src/drug_naming/engines/structure_parser.py`
- Test: `src/drug_naming/tests/test_engines.py` (append)

- [ ] **Step 1: Write the test file additions**

Append to `src/drug_naming/tests/test_engines.py`:

```python
# ── Structure Parser ──

class TestStructureParser:
    def setup_method(self):
        from drug_naming.engines.structure_parser import StructureParser
        self.parser = StructureParser()

    def test_quinazoline_scaffold(self):
        """Gefitinib-like quinazoline structure should be detected."""
        # 4-anilinoquinazoline core
        smiles = "COC1=C(C=C2C(=C1)N=CN=C2NC3=CC=C(C=C3)Cl)OCCCN4CCOCC4"
        result = self.parser.parse(smiles)
        assert result.scaffold_type == "quinazoline"
        assert "phenyl" in result.functional_groups
        assert "chloro" in result.functional_groups

    def test_pyridine_scaffold(self):
        """Imatinib-like structure with pyridine/pyrimidine."""
        smiles = "CC1=C(C=C(C=C1)NC(=O)C2=CC=C(C=C2)CN3CCN(CC3)C)NC4=NC=CC(=N4)C5=CN=CC=C5"
        result = self.parser.parse(smiles)
        assert result.scaffold_type in ("pyridine", "pyrimidine", "phenyl")

    def test_triazine_scaffold(self):
        """Lamotrigine-like 1,2,4-triazine."""
        smiles = "NC1=NC(N)=NN=C1C2=C(Cl)C=CC=C2Cl"
        result = self.parser.parse(smiles)
        assert result.scaffold_type == "triazine"

    def test_no_structure(self):
        """Empty SMILES should return empty features."""
        result = self.parser.parse("")
        assert result.scaffold_type == ""
        assert result.functional_groups == []
        assert result.ring_systems == []

    def test_invalid_smiles(self):
        """Invalid SMILES should not crash."""
        result = self.parser.parse("not_a_valid_smiles")
        assert result.scaffold_type == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest src/drug_naming/tests/test_engines.py::TestStructureParser -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Create structure_parser.py**

Create `src/drug_naming/engines/structure_parser.py`:

```python
from __future__ import annotations
from dataclasses import dataclass, field

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors, Lipinski
    from rdkit.Chem.Scaffolds import MurckoScaffold
    HAS_RDKIT = True
except ImportError:
    HAS_RDKIT = False


@dataclass
class StructureFeatures:
    scaffold_type: str = ""
    murcko_smiles: str = ""
    functional_groups: list[str] = field(default_factory=list)
    ring_systems: list[dict] = field(default_factory=list)
    heteroatoms: dict[str, int] = field(default_factory=dict)
    chiral_centers: int = 0
    molecular_formula: str = ""
    molecular_weight: float = 0.0


# ── Scaffold SMARTS patterns ─────────────────────────────────────────────────
# Order matters — longer/more specific patterns first to avoid misclassification

_SCAFFOLD_SMARTS: list[tuple[str, str]] = [
    # Heterocyclic scaffolds (drug-like)
    ("quinazoline",     "c1ccc2ncnc2c1"),          # 喹唑啉 → EGFR TKI
    ("quinoline",       "c1ccc2ncccc2c1"),         # 喹啉
    ("isoquinoline",    "c1ccc2cnccc2c1"),         # 异喹啉
    ("pyrimidine",      "c1cncnc1"),               # 嘧啶
    ("pyridine",        "c1ccccn1"),               # 吡啶
    ("triazine",        "c1ncncn1"),               # 1,3,5-三嗪 / 1,2,4-三嗪
    ("pyrrole",         "c1ccc[nH]1"),             # 吡咯
    ("imidazole",       "c1c[nH]cn1"),             # 咪唑
    ("pyrazole",        "c1cn[nH]c1"),             # 吡唑
    ("thiazole",        "c1cscn1"),                # 噻唑
    ("oxazole",         "c1cocn1"),                # 噁唑
    ("indole",          "c1ccc2[nH]ccc2c1"),       # 吲哚
    ("benzimidazole",   "c1ccc2[nH]cnc2c1"),       # 苯并咪唑
    ("purine",          "c1nc2ncnc2[nH]1"),        # 嘌呤
    ("pteridine",       "c1nc2ncncc2nc1"),         # 蝶啶
    ("benzodiazepine",  "c1ccc2c(c1)CNCCN2"),      # 苯二氮䓬
    ("dihydropyridine", "C1C=CNC=C1"),             # 二氢吡啶
    ("hydantoin",       "O=C1CNC(=O)N1"),          # 乙内酰脲
    ("barbiturate",     "O=C1CC(=O)NC(=O)N1"),     # 巴比妥
    ("morpholine",      "C1COCCN1"),               # 吗啉
    ("piperazine",      "C1CNCCN1"),               # 哌嗪
    ("piperidine",      "C1CCNCC1"),               # 哌啶
    # Carbocyclic scaffolds
    ("naphthalene",     "c1ccc2ccccc2c1"),         # 萘
    ("phenyl",          "c1ccccc1"),               # 苯环
    # Acyclic linkers
    ("amide",           "[NX3][CX3](=[OX1])"),     # 酰胺
    ("ester",           "[CX3](=[OX1])[OX2]"),     # 酯
    ("sulfonamide",     "[SX4](=[OX1])(=[OX1])[NX3]"), # 磺酰胺
    ("urea",            "[NX3][CX3](=[OX1])[NX3]"),# 脲
    ("carbamate",       "[OX2][CX3](=[OX1])[NX3]"),# 氨基甲酸酯
]


# ── Functional group SMARTS ──────────────────────────────────────────────────

_FG_SMARTS: list[tuple[str, str]] = [
    ("chloro",      "[Cl]"),
    ("fluoro",      "[F]"),
    ("bromo",       "[Br]"),
    ("iodo",        "[I]"),
    ("hydroxyl",    "[OX2H]"),
    ("methoxy",     "[OX2]([CX4])[CX4H]"),
    ("ethoxy",      "[OX2]([CX4])[CX4H2][CX4H3]"),
    ("trifluoromethyl", "[CX4](F)(F)F"),
    ("methyl",      "[CX4H3]"),
    ("ethyl",       "[CX4H2][CX4H3]"),
    ("isopropyl",   "[CX4H]([CX4H3])[CX4H3]"),
    ("tert-butyl",  "[CX4]([CX4H3])([CX4H3])[CX4H3]"),
    ("acetyl",      "[CX3](=[OX1])[CX4H3]"),
    ("nitro",       "[$([NX3](=O)=O),$([NX3+](=O)[O-])]"),
    ("amino",       "[NX3;H2,H1;!$(NC=O)]"),
    ("methylamino", "[NX3H1]([CX4H3])"),
    ("dimethylamino", "[NX3]([CX4H3])[CX4H3]"),
    ("cyano",       "[CX2]#N"),
    ("carboxyl",    "[CX3](=[OX1])[OX2H1]"),
    ("sulfonyl",    "[SX4](=[OX1])(=[OX1])"),
    ("thioether",   "[SX2]([CX4])[CX4]"),
    ("ether",       "[OD2]([CX4])[CX4]"),
    ("ketone",      "[#6][CX3](=[OX1])[#6]"),
    ("aldehyde",    "[CX3H1](=[OX1])"),
    ("alkene",      "[CX3]=[CX3]"),
    ("alkyne",      "[CX2]#[CX2]"),
]


def _detect_scaffold(mol: Chem.Mol) -> tuple[str, str]:
    """Identify the dominant heterocyclic/carbocyclic scaffold."""
    for name, smarts in _SCAFFOLD_SMARTS:
        pattern = Chem.MolFromSmarts(smarts)
        if pattern and mol.HasSubstructMatch(pattern):
            return name, smarts
    return "", ""


def _detect_functional_groups(mol: Chem.Mol) -> list[str]:
    """Detect functional groups via SMARTS matching."""
    found = []
    for name, smarts in _FG_SMARTS:
        pattern = Chem.MolFromSmarts(smarts)
        if pattern and mol.HasSubstructMatch(pattern):
            found.append(name)
    return found


def _analyze_ring_systems(mol: Chem.Mol) -> list[dict]:
    """Classify ring systems: monocyclic, fused, bridged, spiro."""
    ri = mol.GetRingInfo()
    rings = ri.AtomRings()
    if not rings:
        return []

    # Build ring adjacency graph
    n_rings = len(rings)
    adjacent = [[False] * n_rings for _ in range(n_rings)]
    for i in range(n_rings):
        set_i = set(rings[i])
        for j in range(i + 1, n_rings):
            set_j = set(rings[j])
            shared = len(set_i & set_j)
            if shared >= 2:  # fused
                adjacent[i][j] = adjacent[j][i] = True

    # Find connected components of ring systems
    visited = [False] * n_rings
    results = []

    for i in range(n_rings):
        if visited[i]:
            continue
        # BFS to find all rings in this system
        stack = [i]
        visited[i] = True
        system_atoms = set(rings[i])
        n_system_rings = 1

        while stack:
            r = stack.pop()
            for j in range(n_rings):
                if not visited[j] and adjacent[r][j]:
                    visited[j] = True
                    stack.append(j)
                    system_atoms |= set(rings[j])
                    n_system_rings += 1

        if n_system_rings == 1:
            rtype = "monocyclic"
        elif n_system_rings == 2:
            rtype = "bicyclic_fused"
        elif n_system_rings == 3:
            rtype = "tricyclic_fused"
        else:
            rtype = "polycyclic_fused"

        # Count heteroatoms in ring
        hetero_count = sum(1 for idx in system_atoms
                          if mol.GetAtomWithIdx(idx).GetAtomicNum() not in (6, 1))

        results.append({
            "type": rtype,
            "ring_count": n_system_rings,
            "atom_count": len(system_atoms),
            "heteroatom_count": hetero_count,
        })

    return results


def _count_chiral_centers(mol: Chem.Mol) -> int:
    """Count tetrahedral chiral centers."""
    count = 0
    for atom in mol.GetAtoms():
        if atom.GetChiralTag() in (
            Chem.ChiralType.CHI_TETRAHEDRAL_CW,
            Chem.ChiralType.CHI_TETRAHEDRAL_CCW,
        ):
            count += 1
    return count


class StructureParser:
    """RDKit-based molecular structure analysis engine.

    Parses a SMILES string and returns structured features:
    scaffold type, functional groups, ring system analysis,
    heteroatom counts, and chiral center count.
    """

    def parse(self, smiles: str) -> StructureFeatures:
        if not smiles or not HAS_RDKIT:
            return StructureFeatures()

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return StructureFeatures()

        try:
            # Add hydrogens for better chirality detection
            mol = Chem.AddHs(mol)
        except Exception:
            pass

        scaffold_type, _ = _detect_scaffold(mol)

        # Murcko scaffold
        try:
            murcko = MurckoScaffold.GetScaffoldForMol(mol)
            murcko_smiles = Chem.MolToSmiles(murcko) if murcko else ""
        except Exception:
            murcko_smiles = ""

        functional_groups = _detect_functional_groups(mol)
        ring_systems = _analyze_ring_systems(mol)

        # Heteroatom count
        heteroatoms = {}
        for atom in mol.GetAtoms():
            num = atom.GetAtomicNum()
            if num > 1:
                sym = atom.GetSymbol()
                heteroatoms[sym] = heteroatoms.get(sym, 0) + 1

        chiral_centers = _count_chiral_centers(mol)
        mol_formula = Chem.rdMolDescriptors.CalcMolFormula(mol)
        mol_weight = Descriptors.MolWt(mol)

        return StructureFeatures(
            scaffold_type=scaffold_type,
            murcko_smiles=murcko_smiles,
            functional_groups=functional_groups,
            ring_systems=ring_systems,
            heteroatoms={k: v for k, v in sorted(heteroatoms.items()) if k not in ("C", "H")},
            chiral_centers=chiral_centers,
            molecular_formula=mol_formula,
            molecular_weight=round(mol_weight, 1),
        )
```

- [ ] **Step 4: Run structure tests**

Run: `pytest src/drug_naming/tests/test_engines.py::TestStructureParser -v`
Expected: 5 PASS (scaffold detection + functional groups + edge cases)

- [ ] **Step 5: Commit**

```bash
git add src/drug_naming/engines/structure_parser.py src/drug_naming/tests/test_engines.py
git commit -m "feat: add RDKit-based molecular structure parser"
```

---

### Task 3: Enhance stem_matcher.py with scaffold rules

**Files:**
- Modify: `src/drug_naming/engines/stem_matcher.py:23-29` (add scaffold rules)
- Modify: `src/drug_naming/engines/stem_matcher.py:152-158` (accept StructureFeatures in match())

- [ ] **Step 1: Add scaffold→stem rules to KNOWN_RULES**

After the existing `KNOWN_RULES` list (before line 129 `]`), add scaffold-aware rules:

```python
    # ── Scaffold-based stem disambiguation (enhanced by structure drawing) ──
    # When scaffold is detected from drawn structure, these rules provide
    # higher-confidence stem matching than target+mechanism alone.
    (("egfr", "inhibitor", "small_molecule", "quinazoline"),
     [("-tinib", "target_class_stem")]),
    (("egfr", "inhibitor", "small_molecule", "pyrimidine"),
     [("-tinib", "target_class_stem")]),
    (("alk", "inhibitor", "small_molecule", "pyrimidine"),
     [("-tinib", "target_class_stem")]),
    (("nav", "blocker", "small_molecule", "triazine"),
     [("-trigine", "target_class_stem")]),
    (("nav", "blocker", "small_molecule", "amide"),
     [("-caine", "chemical_class_stem")]),
    (("nav", "blocker", "small_molecule", "ester"),
     [("-caine", "chemical_class_stem")]),
    (("calcium_channel", "blocker", "small_molecule", "dihydropyridine"),
     [("-dipine", "target_class_stem")]),
    (("gaba_receptor", "agonist", "small_molecule", "benzodiazepine"),
     [("-zepam", "chemical_class_stem")]),
    (("ppar", "agonist", "small_molecule", "phenyl"),
     [("-glitazar", "target_class_stem")]),
    (("cox", "inhibitor", "small_molecule", "pyrazole"),
     [("-coxib", "target_class_stem")]),
    (("sglt2", "inhibitor", "small_molecule", "phenyl"),
     [("-gliflozin", "target_class_stem")]),
    (("hcv_protease", "inhibitor", "small_molecule", "amide"),
     [("-previr", "target_class_stem")]),
]
```

- [ ] **Step 2: Modify StemMatchingEngine.match() to accept structure_features**

Change the `match()` method signature and body to accept optional structure features. Replace lines 152-158:

```python
    def match(
        self,
        properties: PharmacologicalProperties,
        top_k: int | None = None,
        min_score: float | None = None,
        structure_features: "StructureFeatures | None" = None,
    ) -> list[StemMatch]:
        top_k = top_k or self.config.max_results
        min_score = min_score or self.config.min_score

        tc = getattr(properties.target_class, 'value', properties.target_class)
        mc = getattr(properties.mechanism, 'value', properties.mechanism)
        cc = getattr(properties.chemical_class, 'value', properties.chemical_class)
        ind = getattr(properties, 'indication', '') or ''
        scaffold = getattr(properties, 'chemical_scaffold', '') or ''
        area = getattr(properties, 'therapeutic_area', '') or ''

        # Merge structure-detected scaffold into scaffold field if not manually set
        if structure_features and structure_features.scaffold_type and not scaffold:
            scaffold = structure_features.scaffold_type
```

Add import at top of file, after existing imports:

```python
from __future__ import annotations
from typing import Protocol, TYPE_CHECKING
from ..models.molecule import PharmacologicalProperties
from ..models.stem import INNStem, StemMatch, StemCategory, StemMatchingConfig
from ..data.targets import find_target, TargetMeta

if TYPE_CHECKING:
    from .structure_parser import StructureFeatures
```

- [ ] **Step 3: Run all existing tests to ensure no regression**

Run: `pytest src/drug_naming/tests/test_engines.py -v`
Expected: All 35+ existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add src/drug_naming/engines/stem_matcher.py
git commit -m "feat: add scaffold-aware rules and structure_features support to stem matcher"
```

---

### Task 4: Create /api/structure/analyze endpoint

**Files:**
- Create: `src/drug_naming/api/structure.py`
- Modify: `src/drug_naming/api/router.py:8,16`

- [ ] **Step 1: Create api/structure.py**

```python
from __future__ import annotations
from pydantic import BaseModel
from fastapi import APIRouter

router = APIRouter()


class StructureAnalyzeRequest(BaseModel):
    smiles: str
    target_class: str = ""
    mechanism: str = ""
    chemical_class: str = "small_molecule"
    indication: str = ""


class StructureAnalyzeResponse(BaseModel):
    scaffold_type: str
    murcko_smiles: str
    functional_groups: list[str]
    ring_systems: list[dict]
    heteroatoms: dict[str, int]
    chiral_centers: int
    molecular_formula: str
    molecular_weight: float


@router.post("/analyze", response_model=StructureAnalyzeResponse)
def analyze_structure(body: StructureAnalyzeRequest) -> StructureAnalyzeResponse:
    """Analyze a molecular structure (SMILES) and return structural features."""
    from ..engines.structure_parser import StructureParser

    parser = StructureParser()
    features = parser.parse(body.smiles)

    return StructureAnalyzeResponse(
        scaffold_type=features.scaffold_type,
        murcko_smiles=features.murcko_smiles,
        functional_groups=features.functional_groups,
        ring_systems=features.ring_systems,
        heteroatoms=features.heteroatoms,
        chiral_centers=features.chiral_centers,
        molecular_formula=features.molecular_formula,
        molecular_weight=features.molecular_weight,
    )
```

- [ ] **Step 2: Register in router.py**

Add after line 8 (`from .projects import router as projects_router`):

```python
from .structure import router as structure_router
```

Add after line 16:

```python
api_router.include_router(structure_router, prefix="/structure", tags=["Structure"])
```

- [ ] **Step 3: Test the endpoint manually**

Start server: `cd src && python3 -m uvicorn drug_naming.main:app --port 8000`

Run: `curl -s -X POST http://localhost:8000/api/structure/analyze \
  -H "Content-Type: application/json" \
  -d '{"smiles": "COC1=C(C=C2C(=C1)N=CN=C2NC3=CC=C(C=C3)Cl)OCCCN4CCOCC4"}' | python3 -m json.tool`

Expected: Response containing `"scaffold_type": "quinazoline"`, `"functional_groups": ["chloro", "methoxy", "ether", ...]`

- [ ] **Step 4: Commit**

```bash
git add src/drug_naming/api/structure.py src/drug_naming/api/router.py
git commit -m "feat: add /api/structure/analyze endpoint for molecular structure parsing"
```

---

### Task 5: Integrate Ketcher iframe in Tab B

**Files:**
- Modify: `src/drug_naming/static/index.html`

- [ ] **Step 1: Add Ketcher iframe above the existing form**

Insert after line 824 (`<div class="panel-left">`) and before `<div class="card">` (line 825):

```html
      <!-- Ketcher Structure Editor -->
      <div class="card" style="padding:10px;">
        <h3 style="margin-bottom:8px;">分子结构绘制 <span style="font-weight:400;font-size:11px;color:var(--color-muted-foreground);">（绘制后自动识别骨架和官能团）</span></h3>
        <iframe ref="ketcherFrame" :src="ketcherUrl" style="width:100%;height:420px;border:1px solid var(--color-border);border-radius:6px;"></iframe>
        <div style="margin-top:8px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
          <button class="btn btn-sm" @click="ketcherGetSmiles" :disabled="!ketcherReady">获取 SMILES</button>
          <button class="btn btn-sm" @click="ketcherClear" :disabled="!ketcherReady">清除画布</button>
          <span v-if="ketcherSmiles" style="font-family:monospace;font-size:11px;color:var(--color-primary);word-break:break-all;flex:1;min-width:200px;">SMILES: {{ ketcherSmiles }}</span>
        </div>
        <div v-if="ketcherPreview" style="margin-top:6px;font-size:11px;color:var(--color-muted-foreground);">
          预览: {{ ketcherPreview }}
        </div>
      </div>
```

- [ ] **Step 2: Add Ketcher JS state and methods**

Insert before the `// ========== Tab B: Smart Recommendation ==========` comment block (before line 1384):

```javascript
    // ========== Ketcher Structure Editor ==========
    const ketcherUrl = 'https://unpkg.com/ketcher@2.24.0/dist/ketcher.standalone.html';
    const ketcherFrame = ref(null);
    const ketcherReady = ref(false);
    const ketcherSmiles = ref('');
    const ketcherPreview = ref('');

    // Listen for Ketcher ready event
    window.addEventListener('message', (e) => {
      if (e.data && e.data.type === 'ketcher_ready') {
        ketcherReady.value = true;
      }
    });

    async function ketcherGetSmiles() {
      if (!ketcherFrame.value) return;
      try {
        const iframe = ketcherFrame.value;
        iframe.contentWindow.postMessage({ type: 'ketcher_get_smiles' }, '*');

        // Ketcher responds via postMessage
        const response = await new Promise((resolve) => {
          const handler = (e) => {
            if (e.data && e.data.type === 'ketcher_smiles') {
              window.removeEventListener('message', handler);
              resolve(e.data.smiles);
            }
          };
          window.addEventListener('message', handler);
          // Timeout after 5s
          setTimeout(() => { window.removeEventListener('message', handler); resolve(''); }, 5000);
        });

        ketcherSmiles.value = response || '';

        // Quick frontend preview: count atoms/rings from SMILES
        if (response) {
          const atomMatch = response.match(/[A-Z][a-z]?/g) || [];
          const heavyAtoms = atomMatch.filter(a => a !== 'H');
          const ringCount = (response.match(/[0-9]/g) || []).length;
          const hasN = heavyAtoms.includes('N') ? '含N杂环' : '';
          const hasO = heavyAtoms.includes('O') ? '含O' : '';
          const hasHalogen = heavyAtoms.some(a => ['F','Cl','Br','I'].includes(a)) ? '含卤素' : '';
          ketcherPreview.value = `C${heavyAtoms.filter(a=>a==='C').length} | ${ringCount}环 | ${[hasN,hasO,hasHalogen].filter(Boolean).join(' | ') || '碳环'}`;
        } else {
          ketcherPreview.value = '';
        }
      } catch (e) {
        console.error('Ketcher getSmiles error:', e);
      }
    }

    function ketcherClear() {
      if (!ketcherFrame.value) return;
      ketcherFrame.value.contentWindow.postMessage({ type: 'ketcher_clear' }, '*');
      ketcherSmiles.value = '';
      ketcherPreview.value = '';
    }
```

- [ ] **Step 3: Wire structure analysis into runRecommend()**

Modify the `runRecommend` function (around line 1656) to include structure analysis. Change the `props` construction:

```javascript
    async function runRecommend() {
      recLoading.value = true; recError.value = ''; recStep.value = 0;
      recPocaResults.value = []; recChineseNames.value = [];
      try {
        // If SMILES available, analyze structure first
        let scaffoldValue = recScaffold.value || null;
        if (ketcherSmiles.value && ketcherReady.value) {
          try {
            const structRes = await apiPost('/structure/analyze', {
              smiles: ketcherSmiles.value,
              target_class: recTargetClass.value || 'other',
              mechanism: recMechanism.value || 'other',
              chemical_class: recChemicalClass.value || 'small_molecule',
              indication: recIndication.value || ''
            });
            // Auto-fill scaffold from structure analysis if not manually set
            if (structRes.scaffold_type && !recScaffold.value) {
              scaffoldValue = structRes.scaffold_type;
            }
          } catch (e) {
            console.warn('Structure analysis failed, continuing without:', e);
          }
        }

        const props = {
          target_class: recTargetClass.value || 'other',
          mechanism: recMechanism.value || 'other',
          chemical_class: recChemicalClass.value || 'small_molecule',
          indication: recIndication.value || '',
          chemical_scaffold: scaffoldValue,
          therapeutic_area: recArea.value || null
        };
        // ... rest of existing function unchanged
```

- [ ] **Step 4: Register new functions in the Vue return object**

Find the `return` block near the end of the Vue setup and add the Ketcher state/functions:

```javascript
      ketcherFrame, ketcherSmiles, ketcherPreview, ketcherReady,
      ketcherGetSmiles, ketcherClear,
```

- [ ] **Step 5: Commit**

```bash
git add src/drug_naming/static/index.html
git commit -m "feat: integrate Ketcher structure editor in Tab B"
```

---

### Task 6: End-to-end verification

- [ ] **Step 1: Install rdkit and restart server**

```bash
pip install rdkit>=2023.9.0
pkill -f "uvicorn.*src.drug_naming.main"
cd src && python3 -m uvicorn drug_naming.main:app --host 0.0.0.0 --port 8000 &
```

- [ ] **Step 2: Verify the API endpoint works**

Run:
```bash
curl -s -X POST http://localhost:8000/api/structure/analyze \
  -H "Content-Type: application/json" \
  -d '{"smiles":"COC1=C(C=C2C(=C1)N=CN=C2NC3=CC=C(C=C3)Cl)OCCCN4CCOCC4"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Scaffold:', d['scaffold_type']); print('FGs:', d['functional_groups'])"
```
Expected: `Scaffold: quinazoline` and `FGs: ['chloro', 'methoxy', ...]`

- [ ] **Step 3: Open browser and test full flow**

Open `http://localhost:8000` → Tab B「智能推荐」
1. Ketcher iframe should be visible with drawing tools
2. Draw a quinazoline structure (or use the template)
3. Click「获取 SMILES」→ SMILES string should appear
4. Fill in target: EGFR, mechanism: inhibitor
5. Click「开始推荐」
6. Verify that `-tinib` appears in matched stems with scaffold-enhanced confidence

- [ ] **Step 4: Run full test suite**

```bash
pytest src/drug_naming/tests/ -v
```
Expected: All tests pass.

- [ ] **Step 5: Commit any final fixes**

```bash
git add -A && git commit -m "chore: final integration fixes for structure drawing feature"
```

---

## Verification Checklist

- [ ] `pip install rdkit` succeeds
- [ ] `curl /api/structure/analyze` with gefitinib SMILES returns `scaffold_type: quinazoline`
- [ ] Ketcher iframe loads in Tab B
- [ ] Drawing a structure and clicking「获取 SMILES」shows the SMILES string
- [ ] Clicking「开始推荐」with structure + target info returns enhanced stem matches
- [ ] All existing tests still pass (no regression)
- [ ] Tab B works correctly even when no structure is drawn (backward compatible)
