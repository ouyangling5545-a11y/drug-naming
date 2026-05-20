from __future__ import annotations
from .._compat import StrEnum
from pydantic import BaseModel, Field


class TargetClass(StrEnum):
    # Respiratory / anti-infective / analgesic (prioritized)
    COX = "cox"
    OPIOID_RECEPTOR = "opioid_receptor"
    SODIUM_CHANNEL = "sodium_channel"
    HISTAMINE_RECEPTOR = "histamine_receptor"
    LEUKOTRIENE_RECEPTOR = "leukotriene_receptor"
    BETA_ADRENOCEPTOR = "beta_adrenoceptor"
    MUSCARINIC_RECEPTOR = "muscarinic_receptor"
    BACTERIAL_TARGET = "bacterial_target"
    VIRAL_TARGET = "viral_target"
    FUNGAL_TARGET = "fungal_target"
    # General
    KINASE = "kinase"
    GPCR = "gpcr"
    ION_CHANNEL = "ion_channel"
    NUCLEAR_RECEPTOR = "nuclear_receptor"
    PROTEASE = "protease"
    TRANSPORTER = "transporter"
    CYTOKINE = "cytokine"
    GROWTH_FACTOR = "growth_factor"
    IMMUNE_CHECKPOINT = "immune_checkpoint"
    TNF_SUPERFAMILY = "tnf_superfamily"
    COMPLEMENT = "complement"
    INTEGRIN = "integrin"
    OTHER = "other"


class Mechanism(StrEnum):
    INHIBITOR = "inhibitor"
    ACTIVATOR = "activator"
    AGONIST = "agonist"
    ANTAGONIST = "antagonist"
    MODULATOR = "modulator"
    BLOCKER = "blocker"
    ANTIBODY = "antibody"
    FUSION_PROTEIN = "fusion_protein"
    GENE_THERAPY = "gene_therapy"
    ANTISENSE = "antisense"
    VACCINE = "vaccine"
    OTHER = "other"


class ChemicalClass(StrEnum):
    SMALL_MOLECULE = "small_molecule"
    MONOCLONAL_ANTIBODY = "monoclonal_antibody"
    ANTIBODY_FRAGMENT = "antibody_fragment"
    BISPECIFIC_ANTIBODY = "bispecific_antibody"
    ANTIBODY_DRUG_CONJUGATE = "antibody_drug_conjugate"
    FUSION_PROTEIN = "fusion_protein"
    PEPTIDE = "peptide"
    OLIGONUCLEOTIDE = "oligonucleotide"
    MRNA = "mrna"
    SIRNA = "sirna"
    OTHER = "other"


class PharmacologicalProperties(BaseModel):
    target_class: str = Field(description="Target class or specific gene target, e.g. 'egfr', 'kinase', 'her2'")
    mechanism: Mechanism
    chemical_class: ChemicalClass
    indication: str = Field(default="", description="Primary therapeutic indication, e.g. 'non-small cell lung cancer'")
    chemical_scaffold: str | None = Field(
        default=None,
        description="Core chemical scaffold, e.g. 'triazine', 'amide/ester', 'quinazoline'"
    )
    therapeutic_area: str | None = Field(
        default=None,
        description="Therapeutic area / ATC category, e.g. 'anticonvulsant', 'local_anesthetic'"
    )
    chemical_structure_substructure: str | None = Field(
        default=None,
        description="Optional chemical substructure identifier (legacy, prefer chemical_scaffold)"
    )
    additional_targets: list[str] = Field(default_factory=list)
    additional_mechanisms: list[str] = Field(default_factory=list)


class MoleculeInput(BaseModel):
    molecule_id: str = Field(description="Internal identifier for the molecule, e.g. 'CP-001'")
    common_name: str | None = Field(default=None, description="Lab code or common name, e.g. 'compound A'")
    properties: PharmacologicalProperties
