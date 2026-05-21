"""Hierarchical target database for intelligent drug naming recommendations.

Each target node carries metadata used to auto-fill mechanism, chemical class,
indication, and to suggest relevant INN stems.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class TargetMeta:
    """Metadata for a specific drug target."""
    value: str
    label: str           # English gene/protein name
    label_cn: str         # Chinese name
    category: str = ""    # parent category for grouping (inherited from parent if empty)
    mechanisms: list[str] = field(default_factory=list)
    chemical_class: str = "small_molecule"
    indication: str = ""
    known_stems: list[str] = field(default_factory=list)
    substructure: str = ""  # typical chemical scaffold
    scaffold_options: list[str] = field(default_factory=list)  # possible scaffolds
    therapeutic_area: str = ""  # ATC therapeutic area
    children: list[TargetMeta] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "v": self.value,
            "label": self.label,
            "cn": self.label_cn,
            "cat": self.category,
            "mechanisms": self.mechanisms,
            "chemClass": self.chemical_class,
            "indication": self.indication,
            "stems": self.known_stems,
            "substructure": self.substructure,
            "scaffoldOptions": self.scaffold_options,
            "therapeuticArea": self.therapeutic_area,
        }
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


# ── Target Hierarchy ──────────────────────────────────────────────────────────

TARGET_TREE: list[TargetMeta] = [
    # ═══════════════════════════════════════════════════════════════════════════
    # KINASE
    # ═══════════════════════════════════════════════════════════════════════════
    TargetMeta(value="kinase", label="Kinase", label_cn="激酶", category="kinase", children=[
        TargetMeta(
            value="egfr",
            label="EGFR",
            label_cn="表皮生长因子受体",
            mechanisms=["inhibitor", "inhibitor (共价)", "inhibitor (ATP竞争性)"],
            indication="非小细胞肺癌",
            known_stems=["-tinib", "-metinib"],
            substructure="quinazoline / pyrimidine",
            children=[
                TargetMeta(value="egfr_t790m", label="EGFR (T790M)", label_cn="EGFR T790M耐药突变",
                           mechanisms=["inhibitor (共价)"], indication="非小细胞肺癌（二线）",
                           known_stems=["-tinib", "-metinib"], substructure="pyrimidine"),
                TargetMeta(value="egfr_exon19del", label="EGFR (exon19del)", label_cn="EGFR 19外显子缺失",
                           mechanisms=["inhibitor (ATP竞争性)"], indication="非小细胞肺癌（一线）",
                           known_stems=["-tinib"], substructure="quinazoline"),
                TargetMeta(value="egfr_l858r", label="EGFR (L858R)", label_cn="EGFR L858R突变",
                           mechanisms=["inhibitor (ATP竞争性)"], indication="非小细胞肺癌（一线）",
                           known_stems=["-tinib"], substructure="quinazoline"),
            ]
        ),
        TargetMeta(
            value="her2",
            label="HER2 (ERBB2)",
            label_cn="人表皮生长因子受体2",
            mechanisms=["inhibitor", "antibody", "antibody-drug conjugate"],
            indication="乳腺癌 / 胃癌",
            known_stems=["-tinib", "-mab", "-tuximab"],
            substructure="quinazoline",
        ),
        TargetMeta(
            value="braf",
            label="BRAF (V600E)",
            label_cn="BRAF V600E突变",
            mechanisms=["inhibitor"],
            indication="黑色素瘤 / 结直肠癌",
            known_stems=["-rafenib"],
            substructure="sulfonamide",
        ),
        TargetMeta(
            value="alk",
            label="ALK / ROS1",
            label_cn="间变性淋巴瘤激酶",
            mechanisms=["inhibitor", "inhibitor (ATP竞争性)"],
            indication="非小细胞肺癌",
            known_stems=["-tinib"],
            substructure="pyrimidine / benzodiazepine",
        ),
        TargetMeta(
            value="btk",
            label="BTK",
            label_cn="布鲁顿酪氨酸激酶",
            mechanisms=["inhibitor (共价)", "inhibitor"],
            indication="B细胞淋巴瘤 / CLL",
            known_stems=["-brutinib", "-tinib"],
            substructure="pyrimidine",
        ),
        TargetMeta(
            value="jak",
            label="JAK1 / JAK2",
            label_cn="Janus激酶",
            mechanisms=["inhibitor"],
            indication="骨髓纤维化 / 类风湿关节炎",
            known_stems=["-citinib", "-tinib"],
            substructure="pyrrolopyrimidine",
        ),
        TargetMeta(
            value="cdk46",
            label="CDK4/6",
            label_cn="周期蛋白依赖性激酶4/6",
            mechanisms=["inhibitor"],
            indication="乳腺癌（HR+/HER2-）",
            known_stems=["-ciclib"],
            substructure="pyridopyrimidine",
        ),
        TargetMeta(
            value="pi3k",
            label="PI3K",
            label_cn="磷脂酰肌醇3-激酶",
            mechanisms=["inhibitor"],
            indication="乳腺癌 / 淋巴瘤",
            known_stems=["-lisib"],
            substructure="thiazolidinedione",
        ),
        TargetMeta(
            value="mek",
            label="MEK",
            label_cn="MAPK/ERK激酶",
            mechanisms=["inhibitor"],
            indication="黑色素瘤",
            known_stems=["-metinib"],
            substructure="hydroxamate",
        ),
        TargetMeta(
            value="bcr_abl",
            label="BCR-ABL",
            label_cn="BCR-ABL融合蛋白",
            mechanisms=["inhibitor", "inhibitor (ATP竞争性)"],
            indication="慢性髓系白血病",
            known_stems=["-tinib"],
            substructure="pyrimidine / benzamide",
        ),
        TargetMeta(
            value="vegfr",
            label="VEGFR",
            label_cn="血管内皮生长因子受体",
            mechanisms=["inhibitor"],
            indication="肾细胞癌 / 肝细胞癌",
            known_stems=["-tinib", "-anib"],
            substructure="quinoline / indolinone",
        ),
        TargetMeta(
            value="fgfr",
            label="FGFR",
            label_cn="成纤维细胞生长因子受体",
            mechanisms=["inhibitor"],
            indication="胆管癌 / 尿路上皮癌",
            known_stems=["-tinib"],
            substructure="pyrimidine",
        ),
        TargetMeta(
            value="flt3",
            label="FLT3",
            label_cn="FMS样酪氨酸激酶3",
            mechanisms=["inhibitor"],
            indication="急性髓系白血病",
            known_stems=["-tinib"],
            substructure="pyrimidine",
        ),
        TargetMeta(
            value="mtor",
            label="mTOR",
            label_cn="哺乳动物雷帕霉素靶蛋白",
            mechanisms=["inhibitor"],
            indication="肾细胞癌 / 乳腺癌 / 胰腺神经内分泌瘤",
            known_stems=["-rolimus"],
            substructure="macrocyclic lactone",
        ),
        TargetMeta(
            value="met",
            label="c-MET",
            label_cn="间质上皮转化因子",
            mechanisms=["inhibitor"],
            indication="非小细胞肺癌 / 肝细胞癌",
            known_stems=["-tinib"],
            substructure="quinoline / pyridine",
        ),
        TargetMeta(
            value="ret",
            label="RET",
            label_cn="转染重排激酶",
            mechanisms=["inhibitor"],
            indication="甲状腺癌 / 非小细胞肺癌（RET融合）",
            known_stems=["-tinib"],
            substructure="pyrazolopyridine",
        ),
        TargetMeta(
            value="kit_pdgfr",
            label="KIT / PDGFR",
            label_cn="干细胞因子受体/血小板衍生生长因子受体",
            mechanisms=["inhibitor"],
            indication="胃肠道间质瘤 / 肉瘤",
            known_stems=["-tinib"],
            substructure="indolinone",
        ),
        TargetMeta(
            value="kras_g12c",
            label="KRAS G12C",
            label_cn="KRAS G12C突变",
            mechanisms=["inhibitor (共价)"],
            indication="非小细胞肺癌 / 结直肠癌",
            known_stems=["-rasib"],
            substructure="tetrahydropyridopyrimidine",
        ),
    ]),

    # ═══════════════════════════════════════════════════════════════════════════
    # GPCR
    # ═══════════════════════════════════════════════════════════════════════════
    TargetMeta(value="gpcr", label="GPCR", label_cn="G蛋白偶联受体", category="gpcr", children=[
        TargetMeta(
            value="opioid_mu",
            label="μ-Opioid Receptor",
            label_cn="μ-阿片受体",
            mechanisms=["agonist", "antagonist", "partial agonist"],
            indication="疼痛",
            known_stems=["-eridine", "-fentanil"],
            substructure="piperidine",
        ),
        TargetMeta(
            value="dopamine_d2",
            label="Dopamine D2",
            label_cn="多巴胺D2受体",
            mechanisms=["antagonist", "partial agonist"],
            indication="精神分裂症 / 双相障碍",
            known_stems=["-pride", "-ridone"],
            substructure="benzamide",
        ),
        TargetMeta(
            value="serotonin_5ht2a",
            label="5-HT2A",
            label_cn="5-羟色胺2A受体",
            mechanisms=["antagonist", "inverse agonist"],
            indication="精神分裂症 / 失眠",
            known_stems=["-serin", "-anserin"],
            substructure="piperazine",
        ),
        TargetMeta(
            value="chemokine_cxcr4",
            label="CXCR4",
            label_cn="CXC趋化因子受体4",
            mechanisms=["antagonist"],
            indication="多发性骨髓瘤 / 干细胞动员",
            known_stems=["-rixafor"],
            substructure="cyclam",
        ),
        TargetMeta(
            value="angiotensin_at1",
            label="Angiotensin AT1",
            label_cn="血管紧张素AT1受体",
            mechanisms=["antagonist", "blocker"],
            indication="高血压 / 心力衰竭",
            known_stems=["-sartan"],
            substructure="biphenyl-tetrazole",
        ),
        TargetMeta(
            value="glp1r",
            label="GLP-1 Receptor",
            label_cn="胰高血糖素样肽1受体",
            mechanisms=["agonist"],
            indication="2型糖尿病 / 肥胖",
            known_stems=["-glutide", "-tide"],
            substructure="peptide / fatty acid conjugate",
        ),
        TargetMeta(
            value="gnrh",
            label="GnRH Receptor",
            label_cn="促性腺激素释放激素受体",
            mechanisms=["agonist", "antagonist"],
            indication="前列腺癌 / 子宫内膜异位症",
            known_stems=["-relix"],
            substructure="peptide",
        ),
        TargetMeta(
            value="endothelin",
            label="Endothelin Receptor (ETA/ETB)",
            label_cn="内皮素受体",
            mechanisms=["antagonist"],
            indication="肺动脉高压",
            known_stems=["-sentan"],
            substructure="sulfonamide",
        ),
        TargetMeta(
            value="s1p_receptor",
            label="S1P1 / S1P5 Receptor",
            label_cn="鞘氨醇1-磷酸受体",
            mechanisms=["modulator"],
            indication="多发性硬化症",
            known_stems=["-imod"],
            substructure="aminoindan",
        ),
        TargetMeta(
            value="cgrp",
            label="CGRP / CGRP Receptor",
            label_cn="降钙素基因相关肽及其受体",
            mechanisms=["antagonist", "antibody"],
            indication="偏头痛（预防）",
            known_stems=["-gepant"],
            substructure="monoclonal antibody / piperidine",
        ),
    ]),

    # ═══════════════════════════════════════════════════════════════════════════
    # ION CHANNELS
    # ═══════════════════════════════════════════════════════════════════════════
    TargetMeta(value="ion_channel", label="Ion Channel", label_cn="离子通道", category="ion_channel", children=[
        TargetMeta(
            value="nav",
            label="NaV (Sodium Channel)",
            label_cn="电压门控钠通道",
            mechanisms=["blocker", "inhibitor"],
            indication="疼痛 / 癫痫 / 心律失常",
            known_stems=["-caine", "-trigine", "-amide"],
            substructure="amide / ester",
            scaffold_options=["amide/ester", "triazine", "benzodiazepine", "hydantoin", "dibenzazepine"],
            therapeutic_area="neurology",
        ),
        TargetMeta(
            value="cav",
            label="CaV (Calcium Channel)",
            label_cn="电压门控钙通道",
            mechanisms=["blocker"],
            indication="高血压 / 心绞痛",
            known_stems=["-dipine"],
            substructure="dihydropyridine",
        ),
        TargetMeta(
            value="kv",
            label="KV (Potassium Channel)",
            label_cn="电压门控钾通道",
            mechanisms=["blocker", "activator"],
            indication="心律失常 / 糖尿病",
            known_stems=["-kalant", "-kalim"],
            substructure="benzopyran",
        ),
        TargetMeta(
            value="gaba_a",
            label="GABA_A Receptor",
            label_cn="GABA_A受体",
            mechanisms=["modulator", "agonist"],
            indication="焦虑 / 失眠 / 癫痫",
            known_stems=["-zepam", "-zolam", "-zepate"],
            substructure="benzodiazepine",
        ),
        TargetMeta(
            value="k_atp",
            label="K_ATP (SUR1/Kir6.2)",
            label_cn="ATP敏感性钾通道",
            mechanisms=["blocker", "activator"],
            indication="2型糖尿病 / 高胰岛素血症",
            known_stems=["-ide"],
            substructure="sulfonylurea",
        ),
    ]),

    # ═══════════════════════════════════════════════════════════════════════════
    # PROTEASE
    # ═══════════════════════════════════════════════════════════════════════════
    TargetMeta(value="protease", label="Protease", label_cn="蛋白酶", category="protease", children=[
        TargetMeta(
            value="hiv_protease",
            label="HIV Protease",
            label_cn="HIV蛋白酶",
            mechanisms=["inhibitor"],
            indication="HIV/AIDS",
            known_stems=["-navir"],
            substructure="hydroxyethylene",
        ),
        TargetMeta(
            value="hcv_ns3_4a",
            label="HCV NS3/4A",
            label_cn="丙肝病毒NS3/4A蛋白酶",
            mechanisms=["inhibitor"],
            indication="丙型肝炎",
            known_stems=["-previr"],
            substructure="macrocyclic",
        ),
        TargetMeta(
            value="dpp4",
            label="DPP-4",
            label_cn="二肽基肽酶-4",
            mechanisms=["inhibitor"],
            indication="2型糖尿病",
            known_stems=["-gliptin"],
            substructure="pyrimidine",
        ),
        TargetMeta(
            value="factor_xa",
            label="Factor Xa",
            label_cn="凝血因子Xa",
            mechanisms=["inhibitor"],
            indication="抗凝 / 房颤",
            known_stems=["-xaban"],
            substructure="benzamide",
        ),
        TargetMeta(
            value="thrombin",
            label="Thrombin",
            label_cn="凝血酶",
            mechanisms=["inhibitor"],
            indication="抗凝",
            known_stems=["-gatran"],
            substructure="pyridine",
        ),
        TargetMeta(
            value="renin",
            label="Renin",
            label_cn="肾素",
            mechanisms=["inhibitor"],
            indication="高血压",
            known_stems=["-kiren"],
            substructure="piperidine",
        ),
    ]),

    # ═══════════════════════════════════════════════════════════════════════════
    # NUCLEAR RECEPTOR
    # ═══════════════════════════════════════════════════════════════════════════
    TargetMeta(value="nuclear_receptor", label="Nuclear Receptor", label_cn="核受体", category="nuclear_receptor", children=[
        TargetMeta(
            value="ar",
            label="Androgen Receptor",
            label_cn="雄激素受体",
            mechanisms=["antagonist", "degrader"],
            indication="前列腺癌",
            known_stems=["-lutamide", "-amide"],
            substructure="benzamide",
        ),
        TargetMeta(
            value="er",
            label="Estrogen Receptor",
            label_cn="雌激素受体",
            mechanisms=["antagonist", "degrader", "modulator"],
            indication="乳腺癌",
            known_stems=["-oxifene", "-mifene", "-estrant"],
            substructure="triphenylethylene",
        ),
        TargetMeta(
            value="ppar",
            label="PPAR",
            label_cn="过氧化物酶体增殖物激活受体",
            mechanisms=["agonist"],
            indication="2型糖尿病 / 高脂血症",
            known_stems=["-glitazone", "-fibrate"],
            substructure="thiazolidinedione",
        ),
        TargetMeta(
            value="gr",
            label="Glucocorticoid Receptor",
            label_cn="糖皮质激素受体",
            mechanisms=["agonist", "antagonist"],
            indication="炎症 / 自身免疫病",
            known_stems=["-olone", "-cort", "-pred"],
            substructure="steroid",
        ),
        TargetMeta(
            value="mineralocorticoid",
            label="Mineralocorticoid Receptor",
            label_cn="盐皮质激素受体",
            mechanisms=["antagonist"],
            indication="高血压 / 心力衰竭",
            known_stems=["-enone"],
            substructure="steroid",
        ),
        TargetMeta(
            value="fxr",
            label="FXR (Farnesoid X Receptor)",
            label_cn="法尼酯X受体",
            mechanisms=["agonist"],
            indication="原发性胆汁性胆管炎 / NASH",
            known_stems=["-cholic"],
            substructure="bile acid",
        ),
    ]),

    # ═══════════════════════════════════════════════════════════════════════════
    # TRANSPORTER
    # ═══════════════════════════════════════════════════════════════════════════
    TargetMeta(value="transporter", label="Transporter", label_cn="转运体", category="transporter", children=[
        TargetMeta(
            value="sglt2",
            label="SGLT2",
            label_cn="钠-葡萄糖协同转运蛋白2",
            mechanisms=["inhibitor"],
            indication="2型糖尿病 / 心力衰竭 / CKD",
            known_stems=["-gliflozin"],
            substructure="C-glucoside",
        ),
        TargetMeta(
            value="ssri",
            label="SERT (5-HT Transporter)",
            label_cn="5-羟色胺转运体",
            mechanisms=["inhibitor"],
            indication="抑郁症 / 焦虑症",
            known_stems=["-oxetine", "-traline", "-alopram"],
            substructure="aryl ether",
        ),
        TargetMeta(
            value="net_dat",
            label="NET / DAT",
            label_cn="去甲肾上腺素/多巴胺转运体",
            mechanisms=["inhibitor"],
            indication="ADHD / 抑郁症",
            known_stems=["-oxetine", "-faxine"],
            substructure="aryl ether",
        ),
    ]),

    # ═══════════════════════════════════════════════════════════════════════════
    # IMMUNE CHECKPOINT / CYTOKINE
    # ═══════════════════════════════════════════════════════════════════════════
    TargetMeta(value="cytokine", label="Cytokine / Immune", label_cn="细胞因子/免疫", category="cytokine", children=[
        TargetMeta(
            value="pd1",
            label="PD-1",
            label_cn="程序性死亡受体1",
            mechanisms=["antibody", "inhibitor"],
            indication="多癌种（广谱）",
            known_stems=["-mab", "-limab", "-pimab"],
            substructure="monoclonal antibody",
        ),
        TargetMeta(
            value="pdl1",
            label="PD-L1",
            label_cn="程序性死亡配体1",
            mechanisms=["antibody"],
            indication="多癌种（广谱）",
            known_stems=["-mab", "-limab"],
            substructure="monoclonal antibody",
        ),
        TargetMeta(
            value="ctla4",
            label="CTLA-4",
            label_cn="细胞毒性T淋巴细胞相关蛋白4",
            mechanisms=["antibody"],
            indication="黑色素瘤 / 肾细胞癌",
            known_stems=["-mab", "-limab"],
            substructure="monoclonal antibody",
        ),
        TargetMeta(
            value="tnf_alpha",
            label="TNF-α",
            label_cn="肿瘤坏死因子α",
            mechanisms=["antibody", "inhibitor", "fusion_protein"],
            indication="类风湿关节炎 / 炎症性肠病",
            known_stems=["-mab", "-cept"],
            substructure="monoclonal antibody / fusion protein",
        ),
        TargetMeta(
            value="il17",
            label="IL-17",
            label_cn="白细胞介素17",
            mechanisms=["antibody"],
            indication="银屑病 / 银屑病关节炎",
            known_stems=["-mab", "-kumab"],
            substructure="monoclonal antibody",
        ),
        TargetMeta(
            value="il23",
            label="IL-23",
            label_cn="白细胞介素23",
            mechanisms=["antibody"],
            indication="银屑病 / 克罗恩病",
            known_stems=["-mab", "-kumab"],
            substructure="monoclonal antibody",
        ),
        TargetMeta(
            value="il4r",
            label="IL-4Rα",
            label_cn="白细胞介素4受体α",
            mechanisms=["antibody"],
            indication="特应性皮炎 / 哮喘",
            known_stems=["-mab", "-lumab"],
            substructure="monoclonal antibody",
        ),
    ]),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROWTH FACTOR
    # ═══════════════════════════════════════════════════════════════════════════
    TargetMeta(value="growth_factor", label="Growth Factor", label_cn="生长因子", category="growth_factor", children=[
        TargetMeta(
            value="vegf",
            label="VEGF",
            label_cn="血管内皮生长因子",
            mechanisms=["antibody", "fusion_protein", "inhibitor"],
            indication="湿性AMD / 糖尿病黄斑水肿 / 肿瘤",
            known_stems=["-mab", "-cept", "-tinib", "-anib"],
            substructure="monoclonal antibody",
        ),
        TargetMeta(
            value="ngf",
            label="NGF",
            label_cn="神经生长因子",
            mechanisms=["antibody"],
            indication="骨关节炎疼痛",
            known_stems=["-mab", "-nemab"],
            substructure="monoclonal antibody",
        ),
    ]),

    # ═══════════════════════════════════════════════════════════════════════════
    # BACTERIAL TARGET
    # ═══════════════════════════════════════════════════════════════════════════
    TargetMeta(value="bacterial_target", label="Bacterial Target", label_cn="细菌靶点", category="bacterial_target", children=[
        TargetMeta(
            value="pencillin_binding",
            label="Penicillin-Binding Protein",
            label_cn="青霉素结合蛋白",
            mechanisms=["inhibitor"],
            indication="细菌感染（广谱）",
            known_stems=["-cillin", "-penem", "-cef"],
            substructure="β-lactam",
        ),
        TargetMeta(
            value="bacterial_ribosome_50s",
            label="Bacterial Ribosome 50S",
            label_cn="细菌核糖体50S亚基",
            mechanisms=["inhibitor"],
            indication="细菌感染",
            known_stems=["-mycin", "-micin"],
            substructure="macrolide / aminoglycoside",
        ),
        TargetMeta(
            value="bacterial_ribosome_30s",
            label="Bacterial Ribosome 30S",
            label_cn="细菌核糖体30S亚基",
            mechanisms=["inhibitor"],
            indication="细菌感染",
            known_stems=["-cycline"],
            substructure="tetracycline",
        ),
        TargetMeta(
            value="bacterial_dna_gyrase",
            label="DNA Gyrase / Topoisomerase IV",
            label_cn="DNA旋转酶/拓扑异构酶IV",
            mechanisms=["inhibitor"],
            indication="细菌感染",
            known_stems=["-floxacin", "-oxacin"],
            substructure="quinolone",
        ),
    ]),

    # ═══════════════════════════════════════════════════════════════════════════
    # VIRAL TARGET
    # ═══════════════════════════════════════════════════════════════════════════
    TargetMeta(value="viral_target", label="Viral Target", label_cn="病毒靶点", category="viral_target", children=[
        TargetMeta(
            value="hcv_ns5b",
            label="HCV NS5B Polymerase",
            label_cn="丙肝病毒NS5B聚合酶",
            mechanisms=["inhibitor"],
            indication="丙型肝炎",
            known_stems=["-buvir"],
            substructure="uridine analogue",
        ),
        TargetMeta(
            value="hcv_ns5a",
            label="HCV NS5A",
            label_cn="丙肝病毒NS5A蛋白",
            mechanisms=["inhibitor"],
            indication="丙型肝炎",
            known_stems=["-asvir"],
            substructure="pyrrolidine",
        ),
        TargetMeta(
            value="hiv_rt",
            label="HIV Reverse Transcriptase",
            label_cn="HIV逆转录酶",
            mechanisms=["inhibitor"],
            indication="HIV/AIDS",
            known_stems=["-vudine", "-virdine", "-virenz"],
            substructure="nucleoside / non-nucleoside",
        ),
        TargetMeta(
            value="hiv_integrase",
            label="HIV Integrase",
            label_cn="HIV整合酶",
            mechanisms=["inhibitor"],
            indication="HIV/AIDS",
            known_stems=["-gravir"],
            substructure="diketo acid",
        ),
        TargetMeta(
            value="influenza_neuraminidase",
            label="Influenza Neuraminidase",
            label_cn="流感病毒神经氨酸酶",
            mechanisms=["inhibitor"],
            indication="流感",
            known_stems=["-amivir"],
            substructure="sialic acid analogue",
        ),
    ]),

    # ═══════════════════════════════════════════════════════════════════════════
    # FUNGAL TARGET
    # ═══════════════════════════════════════════════════════════════════════════
    TargetMeta(value="fungal_target", label="Fungal Target", label_cn="真菌靶点", category="fungal_target", children=[
        TargetMeta(
            value="fungal_cyp51",
            label="Fungal CYP51 (14α-Demethylase)",
            label_cn="真菌CYP51",
            mechanisms=["inhibitor"],
            indication="真菌感染",
            known_stems=["-conazole", "-fungin"],
            substructure="azole / echinocandin",
        ),
    ]),

    # ═══════════════════════════════════════════════════════════════════════════
    # ENZYME
    # ═══════════════════════════════════════════════════════════════════════════
    TargetMeta(value="enzyme", label="Enzyme", label_cn="酶", category="enzyme", children=[
        TargetMeta(
            value="cox",
            label="COX-1 / COX-2",
            label_cn="环氧合酶",
            mechanisms=["inhibitor", "selective_inhibitor"],
            indication="疼痛 / 炎症",
            known_stems=["-coxib"],
            substructure="sulfonamide / sulfone",
        ),
        TargetMeta(
            value="pde5",
            label="PDE5",
            label_cn="磷酸二酯酶5",
            mechanisms=["inhibitor"],
            indication="勃起功能障碍 / 肺动脉高压",
            known_stems=["-afil"],
            substructure="pyrazolopyrimidine",
        ),
        TargetMeta(
            value="hmg_coa_reductase",
            label="HMG-CoA Reductase",
            label_cn="HMG-CoA还原酶",
            mechanisms=["inhibitor"],
            indication="高胆固醇血症",
            known_stems=["-statin"],
            substructure="heptanoic acid / pyrrole",
        ),
        TargetMeta(
            value="ace",
            label="ACE",
            label_cn="血管紧张素转换酶",
            mechanisms=["inhibitor"],
            indication="高血压 / 心力衰竭 / 糖尿病肾病",
            known_stems=["-pril", "-prilat"],
            substructure="proline",
        ),
        TargetMeta(
            value="parp",
            label="PARP1 / PARP2",
            label_cn="聚ADP核糖聚合酶",
            mechanisms=["inhibitor"],
            indication="卵巢癌 / 乳腺癌（BRCA突变）",
            known_stems=["-parib"],
            substructure="benzamide",
        ),
        TargetMeta(
            value="proteasome",
            label="Proteasome",
            label_cn="蛋白酶体",
            mechanisms=["inhibitor"],
            indication="多发性骨髓瘤 / 套细胞淋巴瘤",
            known_stems=["-zomib"],
            substructure="boronic acid / peptide epoxyketone",
        ),
        TargetMeta(
            value="idh",
            label="IDH1 / IDH2",
            label_cn="异柠檬酸脱氢酶",
            mechanisms=["inhibitor"],
            indication="急性髓系白血病 / 胆管癌",
            known_stems=["-idenib"],
            substructure="pyridine",
        ),
        TargetMeta(
            value="ezh2",
            label="EZH2",
            label_cn="Zeste同源物增强子2",
            mechanisms=["inhibitor"],
            indication="上皮样肉瘤 / 滤泡性淋巴瘤",
            known_stems=["-stat"],
            substructure="pyridone",
        ),
        TargetMeta(
            value="hdac",
            label="HDAC",
            label_cn="组蛋白去乙酰化酶",
            mechanisms=["inhibitor"],
            indication="皮肤T细胞淋巴瘤 / 外周T细胞淋巴瘤",
            known_stems=["-stat"],
            substructure="hydroxamic acid / benzamide",
        ),
        TargetMeta(
            value="xanthine_oxidase",
            label="Xanthine Oxidase",
            label_cn="黄嘌呤氧化酶",
            mechanisms=["inhibitor"],
            indication="痛风 / 高尿酸血症",
            known_stems=["-xostat"],
            substructure="purine analogue",
        ),
        TargetMeta(
            value="aromatase",
            label="Aromatase (CYP19A1)",
            label_cn="芳香化酶",
            mechanisms=["inhibitor"],
            indication="乳腺癌（HR+）",
            known_stems=["-azole"],
            substructure="triazole",
        ),
    ]),

    # ═══════════════════════════════════════════════════════════════════════════
    # OTHER — fallback category
    # ═══════════════════════════════════════════════════════════════════════════
    TargetMeta(value="other", label="Other", label_cn="其他靶点", category="other", children=[
        TargetMeta(
            value="bcl2",
            label="BCL-2",
            label_cn="B细胞淋巴瘤蛋白2",
            mechanisms=["inhibitor"],
            indication="慢性淋巴细胞白血病 / 急性髓系白血病",
            known_stems=["-clax"],
            substructure="sulfonamide",
        ),
        TargetMeta(
            value="hedgehog_smo",
            label="Hedgehog / Smoothened",
            label_cn="Hedgehog信号通路SMO蛋白",
            mechanisms=["inhibitor"],
            indication="基底细胞癌",
            known_stems=["-gib"],
            substructure="benzamide / pyridine",
        ),
        TargetMeta(
            value="pcsk9",
            label="PCSK9",
            label_cn="前蛋白转化酶枯草溶菌素9",
            mechanisms=["antibody"],
            indication="高胆固醇血症（他汀不耐受）",
            known_stems=["-cumab"],
            substructure="monoclonal antibody",
        ),
    ]),
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def flatten_targets(tree: list[TargetMeta] | None = None) -> list[TargetMeta]:
    """Flatten the target tree into a flat list of leaf nodes with metadata."""
    if tree is None:
        tree = TARGET_TREE
    result = []
    for node in tree:
        if node.children:
            result.extend(flatten_targets(node.children))
        elif node.value:  # leaf node with a real target
            result.append(node)
    return result


def find_target(value: str) -> TargetMeta | None:
    """Find a target by value in the tree."""
    def _search(nodes):
        for n in nodes:
            if n.value == value:
                return n
            if n.children:
                r = _search(n.children)
                if r:
                    return r
        return None
    return _search(TARGET_TREE)


def _propagate_category(nodes: list[TargetMeta], parent_cat: str = "") -> None:
    """Fill missing categories from parent, recursively."""
    for n in nodes:
        if not n.category:
            n.category = parent_cat
        if n.children:
            _propagate_category(n.children, n.category)


def get_target_tree() -> list[dict]:
    """Return the full target tree as a list of dicts for the API."""
    _propagate_category(TARGET_TREE)
    return [t.to_dict() for t in TARGET_TREE]
