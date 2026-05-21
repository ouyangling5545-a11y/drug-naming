from __future__ import annotations
from typing import Protocol, TYPE_CHECKING
from ..models.molecule import PharmacologicalProperties
from ..models.stem import INNStem, StemMatch, StemCategory, StemMatchingConfig
from ..data.targets import find_target, TargetMeta

if TYPE_CHECKING:
    from .structure_parser import StructureFeatures


class StemDataProvider(Protocol):
    """Protocol for stem data source — user plugs in their data here."""

    def get_all_stems(self) -> list[INNStem]: ...
    def get_stems_by_category(self, category: StemCategory) -> list[INNStem]: ...


# ── Tier definitions (lower = higher priority, per INN decision logic) ──
# Tier 1: Direct target → known stem mapping (一票决定权)
# Tier 2: Target category + mechanism combo
# Tier 3: Target category only
# Tier 4: Mechanism + chemical class combo
# Tier 5: Mechanism only / chemical only / indication
# Tier 6: Unclassified / fallback

# Known target→mechanism→stem rules that encode INN conventions precisely.
# Format: (target_or_category, mechanism_substring, chem_class_substring, indication_substring_or_*)
#   → [(stem_text, position_category)]
KNOWN_RULES: list[tuple[tuple[str, str, str, str], list[tuple[str, str]]]] = [
    # ── Kinase inhibitors → -tinib / -nib ──
    (("kinase", "inhibitor", "small_molecule", "*"), [("-tinib", "target_class_stem")]),
    (("egfr", "inhibitor", "small_molecule", "*"), [("-tinib", "target_class_stem")]),
    (("her2", "inhibitor", "small_molecule", "*"), [("-tinib", "target_class_stem")]),
    (("btk", "inhibitor", "small_molecule", "*"), [("-tinib", "target_class_stem")]),
    (("alk", "inhibitor", "small_molecule", "*"), [("-tinib", "target_class_stem")]),
    (("ros1", "inhibitor", "small_molecule", "*"), [("-tinib", "target_class_stem")]),
    (("braf", "inhibitor", "small_molecule", "*"), [("-tinib", "target_class_stem")]),
    (("mek", "inhibitor", "small_molecule", "*"), [("-tinib", "target_class_stem")]),
    (("flt3", "inhibitor", "small_molecule", "*"), [("-tinib", "target_class_stem")]),
    (("jak", "inhibitor", "small_molecule", "*"), [("-tinib", "target_class_stem")]),
    (("cdk", "inhibitor", "small_molecule", "*"), [("-ciclib", "target_class_stem")]),
    (("pi3k", "inhibitor", "small_molecule", "*"), [("-lisib", "target_class_stem")]),
    (("mtor", "inhibitor", "small_molecule", "*"), [("-rolimus", "target_class_stem")]),
    (("parp", "inhibitor", "small_molecule", "*"), [("-parib", "target_class_stem")]),

    # ── GPCR antagonists ──
    (("gpcr", "antagonist", "small_molecule", "*"), [("-grel", "target_class_stem")]),
    (("gpcr", "agonist", "small_molecule", "*"), [("-grel", "target_class_stem")]),
    (("serotonin_receptor", "antagonist", "small_molecule", "*"), [("-anserin", "target_class_stem")]),
    (("dopamine_receptor", "antagonist", "small_molecule", "*"), [("-pride", "target_class_stem")]),
    (("angiotensin_receptor", "antagonist", "small_molecule", "*"), [("-sartan", "target_class_stem")]),
    (("endothelin_receptor", "antagonist", "small_molecule", "*"), [("-sentan", "target_class_stem")]),
    (("chemokine_receptor", "antagonist", "small_molecule", "*"), [("-mokine", "target_class_stem")]),

    # ── Ion channel blockers ──
    # NaV + blocker → -caine (局麻/amide/ester), -trigine (抗癫痫/triazine/神经痛)
    # Differentiation dimensions: indication, chemical scaffold, therapeutic_area
    (("nav", "blocker", "small_molecule", "麻醉"), [("-caine", "chemical_class_stem")]),
    (("nav", "blocker", "small_molecule", "局部"), [("-caine", "chemical_class_stem")]),
    (("nav", "blocker", "small_molecule", "疼痛"), [("-caine", "chemical_class_stem")]),
    (("nav", "blocker", "small_molecule", "癫痫"), [("-trigine", "target_class_stem")]),
    (("nav", "blocker", "small_molecule", "神经"), [("-trigine", "target_class_stem")]),
    (("nav", "blocker", "small_molecule", "心律"), [("-caine", "chemical_class_stem")]),
    # Scaffold-based: triazine → -trigine, amide/ester → -caine
    (("nav", "blocker", "small_molecule", "triazine"), [("-trigine", "target_class_stem")]),
    (("nav", "blocker", "small_molecule", "amide"), [("-caine", "chemical_class_stem")]),
    (("nav", "blocker", "small_molecule", "ester"), [("-caine", "chemical_class_stem")]),
    (("nav", "blocker", "small_molecule", "benzodiazepine"), [("-zepam", "chemical_class_stem")]),
    (("nav", "blocker", "small_molecule", "hydantoin"), [("-toin", "chemical_class_stem")]),
    # Therapeutic area based
    (("nav", "blocker", "small_molecule", "anticonvulsant"), [("-trigine", "target_class_stem")]),
    (("nav", "blocker", "small_molecule", "anesthetic"), [("-caine", "chemical_class_stem")]),
    (("nav", "blocker", "small_molecule", "neurology"), [("-trigine", "target_class_stem")]),
    # Generic ion_channel rules
    (("ion_channel", "blocker", "small_molecule", "麻醉"), [("-caine", "chemical_class_stem")]),
    (("ion_channel", "blocker", "small_molecule", "癫痫"), [("-trigine", "target_class_stem")]),
    (("ion_channel", "blocker", "small_molecule", "神经"), [("-trigine", "target_class_stem")]),
    (("ion_channel", "blocker", "small_molecule", "心律"), [("-caine", "chemical_class_stem")]),
    (("ion_channel", "blocker", "small_molecule", "triazine"), [("-trigine", "target_class_stem")]),
    (("ion_channel", "blocker", "small_molecule", "amide"), [("-caine", "chemical_class_stem")]),
    (("calcium_channel", "blocker", "small_molecule", "*"), [("-dipine", "target_class_stem")]),
    (("potassium_channel", "blocker", "small_molecule", "*"), [("-kalant", "target_class_stem")]),
    (("proton_pump", "inhibitor", "small_molecule", "*"), [("-prazole", "target_class_stem")]),

    # ── Nuclear receptors ──
    (("nuclear_receptor", "antagonist", "small_molecule", "*"), [("-tant", "target_class_stem")]),
    (("androgen_receptor", "antagonist", "small_molecule", "*"), [("-lutamide", "target_class_stem")]),
    (("estrogen_receptor", "antagonist", "small_molecule", "*"), [("-mifene", "target_class_stem")]),
    (("estrogen_receptor", "modulator", "small_molecule", "*"), [("-mifene", "target_class_stem")]),
    (("glucocorticoid_receptor", "agonist", "small_molecule", "*"), [("-lone", "target_class_stem")]),
    (("ppar", "agonist", "small_molecule", "*"), [("-glitazar", "target_class_stem")]),

    # ── Protease inhibitors ──
    (("protease", "inhibitor", "small_molecule", "*"), [("-previr", "target_class_stem")]),
    (("hiv_protease", "inhibitor", "small_molecule", "*"), [("-navir", "target_class_stem")]),
    (("hcv_protease", "inhibitor", "small_molecule", "*"), [("-previr", "target_class_stem")]),
    (("factor_xa", "inhibitor", "small_molecule", "*"), [("-xaban", "target_class_stem")]),
    (("thrombin", "inhibitor", "small_molecule", "*"), [("-gatran", "target_class_stem")]),
    (("dpp4", "inhibitor", "small_molecule", "*"), [("-gliptin", "target_class_stem")]),
    (("ace", "inhibitor", "small_molecule", "*"), [("-pril", "target_class_stem")]),
    (("renin", "inhibitor", "small_molecule", "*"), [("-kiren", "target_class_stem")]),
    (("pde5", "inhibitor", "small_molecule", "*"), [("-afil", "target_class_stem")]),

    # ── Transporters ──
    (("sglt2", "inhibitor", "small_molecule", "*"), [("-gliflozin", "target_class_stem")]),
    (("sert", "inhibitor", "small_molecule", "*"), [("-oxetine", "target_class_stem")]),
    (("ssri", "inhibitor", "small_molecule", "*"), [("-oxetine", "target_class_stem")]),

    # ── Antibodies ──
    (("her2", "antibody", "monoclonal_antibody", "*"), [("-mab", "chemical_class_stem")]),
    (("egfr", "antibody", "monoclonal_antibody", "*"), [("-mab", "chemical_class_stem")]),
    (("pd1", "antibody", "monoclonal_antibody", "*"), [("-mab", "chemical_class_stem")]),
    (("pdl1", "antibody", "monoclonal_antibody", "*"), [("-mab", "chemical_class_stem")]),
    (("ctla4", "antibody", "monoclonal_antibody", "*"), [("-mab", "chemical_class_stem")]),
    (("cd20", "antibody", "monoclonal_antibody", "*"), [("-mab", "chemical_class_stem")]),
    (("vegf", "antibody", "monoclonal_antibody", "*"), [("-mab", "chemical_class_stem")]),
    (("tnf_alpha", "antibody", "monoclonal_antibody", "*"), [("-mab", "chemical_class_stem")]),
    (("il17", "antibody", "monoclonal_antibody", "*"), [("-mab", "chemical_class_stem")]),
    (("il23", "antibody", "monoclonal_antibody", "*"), [("-mab", "chemical_class_stem")]),
    (("il6_receptor", "antibody", "monoclonal_antibody", "*"), [("-mab", "chemical_class_stem")]),
    (("ige", "antibody", "monoclonal_antibody", "*"), [("-mab", "chemical_class_stem")]),

    # ── General antibody ──
    (("*", "antibody", "monoclonal_antibody", "*"), [("-mab", "chemical_class_stem")]),
    (("*", "antibody-drug", "antibody_drug_conjugate", "*"), [("-mab", "chemical_class_stem")]),

    # ── Peptides / oligonucleotides ──
    (("*", "*", "peptide", "*"), [("-tide", "chemical_class_stem")]),
    (("*", "*", "oligonucleotide", "*"), [("-rsen", "chemical_class_stem")]),
    (("*", "*", "sirna", "*"), [("-siran", "chemical_class_stem")]),
    (("*", "*", "mrna", "*"), [("-meran", "chemical_class_stem")]),

    # ── Scaffold-based stem disambiguation (enhanced by structure drawing) ──
    # When scaffold is detected from drawn structure, these rules provide
    # higher-confidence stem matching than target+mechanism alone.
    (("egfr", "inhibitor", "small_molecule", "quinazoline"),
     [("-tinib", "target_class_stem")]),
    (("egfr", "inhibitor", "small_molecule", "pyrimidine"),
     [("-tinib", "target_class_stem")]),
    (("alk", "inhibitor", "small_molecule", "pyrimidine"),
     [("-tinib", "target_class_stem")]),
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


class StemMatchingEngine:
    """Maps pharmacological properties to relevant WHO INN stems using a tiered
    decision tree that mirrors the INN Expert Committee's logic:

    Tier 1 — Direct target → known stem  (一票决定权)
    Tier 2 — Target category + mechanism
    Tier 3 — Target category only
    Tier 4 — Mechanism + chemical class
    Tier 5 — Mechanism only / chemical only
    Tier 6 — Unclassified / fallback
    """

    def __init__(
        self,
        data_provider: StemDataProvider,
        config: StemMatchingConfig | None = None,
    ) -> None:
        self.data_provider = data_provider
        self.config = config or StemMatchingConfig()

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
        # Merge structure-detected scaffold into scaffold field if not manually set
        if structure_features and structure_features.scaffold_type and not scaffold:
            scaffold = structure_features.scaffold_type
        area = getattr(properties, 'therapeutic_area', '') or ''

        all_stems = self.data_provider.get_all_stems()
        target_meta = find_target(tc)
        target_category = target_meta.category if target_meta else tc

        tiered: list[StemMatch] = []

        for stem in all_stems:
            tier, score, reasons = self._tiered_score(
                stem, tc, mc, cc, ind, scaffold, area, target_meta, target_category
            )
            if score >= min_score:
                tiered.append(StemMatch(
                    stem=stem,
                    match_score=score,
                    match_reasons=reasons,
                    relevance_weight=float(tier),
                ))

        # Sort: tier (ascending → Tier 1 first), then score (descending), then priority
        tiered.sort(key=lambda m: (m.relevance_weight, -m.match_score, -m.stem.priority))
        return tiered[:top_k]

    def _tiered_score(
        self,
        stem: INNStem,
        tc: str,
        mc: str,
        cc: str,
        ind: str,
        scaffold: str,
        area: str,
        target_meta: TargetMeta | None,
        target_category: str,
    ) -> tuple[int, float, list[str]]:
        """Score a single stem using the INN tiered decision tree.

        Returns (tier, score, reasons). Lower tier = higher priority.
        """
        reasons: list[str] = []

        stem_tc = [t.lower() for t in stem.target_classes]
        stem_mc = [m.lower() for m in stem.mechanisms]
        stem_cc = [c.lower() for c in stem.chemical_classes]
        stem_text = stem.stem.strip("-").lower()

        tc_l = tc.lower()
        mc_l = mc.lower()
        cc_l = cc.lower()
        cat_l = target_category.lower()

        # ── Tier 1a: Context-specific known-rules (highest specificity) ──
        ind_l = ind.lower()
        scaffold_l = scaffold.lower()
        area_l = area.lower()
        default_ind = (target_meta.indication or '').lower() if target_meta else ''
        default_scaffold = (target_meta.substructure or '').lower() if target_meta else ''
        default_area = (target_meta.therapeutic_area or '').lower() if target_meta else ''
        default_ctx = (default_ind + ' ' + default_scaffold + ' ' + default_area).lower()

        # Helper: try match against explicit user input only (sub_tier 0.3)
        def _try_rules(ctx: str, sub_tier: float, source_label: str):
            for (rule_tc, rule_mc, rule_cc, rule_ind), rule_stems in KNOWN_RULES:
                if rule_ind == "*":
                    continue
                if rule_tc != "*" and rule_tc != tc_l and rule_tc != cat_l:
                    continue
                if rule_mc != "*" and rule_mc not in mc_l:
                    continue
                if rule_cc != "*" and rule_cc != cc_l:
                    continue
                if rule_ind not in ctx:
                    continue
                for rule_stem_text, _cat in rule_stems:
                    if stem_text == rule_stem_text.strip("-").lower():
                        reasons.append(f'Tier 1: {source_label} "{rule_ind}" → {rule_stem_text}')
                        if mc_l in stem_mc:
                            reasons.append(f'mechanism "{mc}" confirmed')
                        return (sub_tier, 1.0, reasons)
            return None

        # Pass 1: User-explicit input (scaffold, area, indication) — highest priority
        user_ctx = (scaffold_l + ' ' + area_l + ' ' + ind_l).lower()
        result = _try_rules(user_ctx, 0.3, 'explicit')
        if result:
            return result

        # Pass 2: Target metadata defaults — lower priority
        result = _try_rules(default_ctx, 1.0, 'target default')
        if result:
            return result

        # ── Tier 1b: Direct known-stem match from targets.py ──
        if target_meta:
            for ks in target_meta.known_stems:
                if stem_text == ks.strip("-").lower():
                    reasons.append(f'Tier 1: known stem for "{tc}"')
                    if mc_l in stem_mc:
                        return (1, 0.97, reasons + [f'mechanism "{mc}" confirmed'])
                    return (1, 0.94, reasons)

        # ── Tier 1c: Generic known-rules (indication wildcard) ──
        for (rule_tc, rule_mc, rule_cc, rule_ind), rule_stems in KNOWN_RULES:
            if rule_ind != "*":
                continue  # already checked above
            if rule_tc != "*" and rule_tc != tc_l and rule_tc != cat_l:
                continue
            if rule_mc != "*" and rule_mc not in mc_l:
                continue
            if rule_cc != "*" and rule_cc != cc_l:
                continue
            for rule_stem_text, _cat in rule_stems:
                if stem_text == rule_stem_text.strip("-").lower():
                    reasons.append(f'Tier 1: generic rule ({rule_tc}+{rule_mc}+{rule_cc}) → {rule_stem_text}')
                    return (1, 0.91, reasons)

        # ── Tier 2: Target value directly in stem's target_classes ──
        if tc_l in stem_tc:
            reasons.append(f'Tier 2: target "{tc}" in stem target_classes')
            if mc_l in stem_mc:
                return (2, 0.88, reasons + [f'mechanism "{mc}" confirmed'])
            return (2, 0.80, reasons)

        # ── Tier 3: Target category + mechanism ──
        if cat_l in stem_tc and mc_l in stem_mc:
            reasons.append(f'Tier 3: category "{target_category}" + mechanism "{mc}"')
            return (3, 0.70, reasons)

        # ── Tier 4: Target category only ──
        if cat_l in stem_tc:
            reasons.append(f'Tier 4: category "{target_category}" matched')
            return (4, 0.50, reasons)

        # ── Tier 5: Mechanism + chemical class ──
        if mc_l in stem_mc and cc_l in stem_cc:
            reasons.append(f'Tier 5: mechanism "{mc}" + chemical "{cc}"')
            return (5, 0.30, reasons)

        # ── Tier 6: Mechanism only ──
        if mc_l in stem_mc:
            return (6, 0.18, [f'Tier 6: mechanism "{mc}" only'])

        # ── Tier 6b: Chemical class only ──
        if cc_l in stem_cc:
            return (6, 0.12, [f'Tier 6: chemical "{cc}" only'])

        # ── Tier 7: Indication keyword match (Jaccard) ──
        if stem.indications and properties_indication_match(stem, target_meta):
            return (7, 0.08, ['Tier 7: indication keyword overlap'])

        # ── Tier 8: Fallback — unclassified broad stems ──
        if not stem.target_classes or 'other' in [t.lower() for t in stem.target_classes]:
            return (8, 0.04, ['Tier 8: general/unclassified stem'])

        return (9, 0.0, [])


def properties_indication_match(stem: INNStem, target_meta: TargetMeta | None) -> bool:
    """Check if stem indications overlap with the target's known indication."""
    if not target_meta or not target_meta.indication:
        return False
    target_ind_tokens = set(target_meta.indication.lower().split('/'))
    for si in stem.indications:
        stem_tokens = set(si.lower().split())
        if target_ind_tokens & stem_tokens:
            return True
    return False
