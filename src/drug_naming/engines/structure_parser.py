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
    ("quinazoline",     "n1cnc2ccccc2c1"),          # 喹唑啉 → EGFR TKI
    ("quinoline",       "c1ccc2ncccc2c1"),         # 喹啉
    ("isoquinoline",    "c1ccc2cnccc2c1"),         # 异喹啉
    ("pyrimidine",      "c1cncnc1"),               # 嘧啶
    ("pyridine",        "c1ccccn1"),               # 吡啶
    ("triazine",        "c1nncnc1"),               # 1,2,4-三嗪
    ("triazine",        "c1ncncn1"),               # 1,3,5-三嗪
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
    ("phenyl",      "c1ccccc1"),
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
