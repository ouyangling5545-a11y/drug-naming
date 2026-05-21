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
