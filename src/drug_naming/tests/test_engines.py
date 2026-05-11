"""Tests for core naming engines."""

import pytest
from drug_naming.models.molecule import (
    PharmacologicalProperties,
    TargetClass,
    Mechanism,
    ChemicalClass,
)
from drug_naming.models.poca import POCAWeights, POCARequest
from drug_naming.models.naming import NameGenerationRequest
from drug_naming.engines._double_metaphone import double_metaphone
from drug_naming.engines.phonetic import PhoneticEncoder
from drug_naming.engines.orthographic import OrthographicAnalyzer
from drug_naming.engines.compositional import CompositionalAnalyzer
from drug_naming.engines.poca_scorer import POCAScoringEngine
from drug_naming.engines.name_generator import NameGenerationEngine
from drug_naming.engines.chinese_name import ChineseNameEngine
from drug_naming.engines.brand_name import BrandNameEngine
from drug_naming.models.brand import BrandScreenRequest


# ── Double Metaphone ──

class TestDoubleMetaphone:
    def test_empty_string(self):
        assert double_metaphone("") == ("", "")

    def test_same_name(self):
        p1, s1 = double_metaphone("imatinib")
        p2, s2 = double_metaphone("imatinib")
        assert p1 == p2
        assert s1 == s2

    def test_different_names(self):
        p1, _ = double_metaphone("aspirin")
        p2, _ = double_metaphone("omeprazole")
        assert p1 != p2

    def test_known_cases(self):
        # KN initial drops K
        p, _ = double_metaphone("knight")
        assert p == "NT"
        # WR drops W
        p, _ = double_metaphone("write")
        assert p[0] == "R"


# ── Phonetic Encoder ──

class TestPhoneticEncoder:
    def setup_method(self):
        self.encoder = PhoneticEncoder()

    def test_soundex_same(self):
        assert self.encoder.soundex("imatinib") == self.encoder.soundex("imatinib")

    def test_syllable_count(self):
        assert self.encoder.syllable_count("imatinib") >= 3  # i-ma-ti-nib
        assert self.encoder.syllable_count("aspirin") >= 2

    def test_same_word_max_score(self):
        detail, score = self.encoder.compute_phonetics("imatinib", "imatinib")
        assert score > 0.8  # Same word should be very high

    def test_different_words_low_score(self):
        detail, score = self.encoder.compute_phonetics("aspirin", "omeprazole")
        assert score < 0.5


# ── Orthographic Analyzer ──

class TestOrthographicAnalyzer:
    def setup_method(self):
        self.analyzer = OrthographicAnalyzer()

    def test_levenshtein_same(self):
        dist, norm = self.analyzer.levenshtein_normalized("imatinib", "imatinib")
        assert dist == 0
        assert norm == 0.0

    def test_levenshtein_different(self):
        dist, norm = self.analyzer.levenshtein_normalized("imatinib", "erlotinib")
        assert dist > 0
        assert 0.0 < norm <= 1.0

    def test_bigram_overlap_same(self):
        assert self.analyzer.bigram_overlap("imatinib", "imatinib") == 1.0

    def test_bigram_overlap_different(self):
        score = self.analyzer.bigram_overlap("abc", "xyz")
        assert score == 0.0

    def test_common_prefix_suffix(self):
        prefix, pfx_len, suffix, sfx_len = self.analyzer.common_prefix_suffix("imatinib", "imatinib")
        assert prefix == "imatinib"
        assert suffix == "imatinib"


# ── Compositional Analyzer ──

class TestCompositionalAnalyzer:
    def setup_method(self):
        self.analyzer = CompositionalAnalyzer(known_stems=["tinib", "mab", "vastatin"])

    def test_shared_stems(self):
        detail, score = self.analyzer.compute_compositional("imatinib", "erlotinib")
        assert "tinib" in detail.shared_stems

    def test_no_shared_stems(self):
        detail, score = self.analyzer.compute_compositional("aspirin", "omeprazole")
        assert len(detail.shared_stems) == 0

    def test_same_name_max(self):
        detail, score = self.analyzer.compute_compositional("imatinib", "imatinib")
        assert score > 0.8


# ── POCA Scorer ──

class TestPOCAScoringEngine:
    def setup_method(self):
        self.engine = POCAScoringEngine(known_stems=["tinib", "mab"])

    def test_identical_rejected(self):
        result = self.engine.score_pair("imatinib", "imatinib")
        assert result.alert_level == "REJECT"
        assert result.overall_poca_score > 0.85

    def test_similar_stem_pass(self):
        result = self.engine.score_pair("imatinib", "erlotinib")
        # Same stem but different prefixes → should pass or review
        assert result.alert_level in ("PASS", "REVIEW")

    def test_different_drugs_pass(self):
        result = self.engine.score_pair("aspirin", "omeprazole")
        assert result.alert_level == "PASS"
        assert result.overall_poca_score < 0.5

    def test_batch_scoring(self):
        request = POCARequest(
            proposed_name="imatinib",
            reference_names=["erlotinib", "dasatinib", "aspirin"],
        )
        response = self.engine.score_batch(request)
        assert len(response.results) == 3
        assert response.overall_safety_assessment in ("PASS", "REVIEW", "REJECT")

    def test_weight_configuration(self):
        weights = POCAWeights(phonetic_weight=0.5, orthographic_weight=0.3, compositional_weight=0.2)
        self.engine.weights = weights
        result = self.engine.score_pair("imatinib", "imatinib")
        assert result.phonetic_score > 0


# ── Name Generator ──

class TestNameGenerator:
    def setup_method(self):
        self.generator = NameGenerationEngine()
        self.props = PharmacologicalProperties(
            target_class=TargetClass.KINASE,
            mechanism=Mechanism.INHIBITOR,
            chemical_class=ChemicalClass.SMALL_MOLECULE,
            indication="cancer",
        )

    def test_generates_candidates(self):
        from drug_naming.engines.stem_matcher import StemMatchingEngine
        from drug_naming.api.stems import _get_default_provider

        provider = _get_default_provider()
        engine = StemMatchingEngine(provider)
        matches = engine.match(self.props, top_k=3)

        request = NameGenerationRequest(properties=self.props, matched_stems=matches)
        response = self.generator.generate(request)
        assert len(response.candidates) > 0
        assert response.total_generated > 0

    def test_filters_existing_names(self):
        from drug_naming.engines.stem_matcher import StemMatchingEngine
        from drug_naming.api.stems import _get_default_provider

        provider = _get_default_provider()
        engine = StemMatchingEngine(provider)
        matches = engine.match(self.props, top_k=2)

        request = NameGenerationRequest(
            properties=self.props,
            matched_stems=matches,
            existing_names_to_avoid=["imatinib"],
        )
        response = self.generator.generate(request)
        for c in response.candidates:
            assert c.name.lower() != "imatinib"


# ── Chinese Name Engine ──

class TestChineseNameEngine:
    def setup_method(self):
        self.engine = ChineseNameEngine()

    def test_generates_candidates(self):
        from drug_naming.models.chinese import ChineseNameRequest

        request = ChineseNameRequest(
            inn_name="imatinib",
            pharmacological_properties={"target_class": "kinase", "mechanism": "inhibitor"},
            max_candidates=5,
        )
        response = self.engine.suggest(request)
        assert len(response.candidates) > 0
        for c in response.candidates:
            assert len(c.chinese_name) >= 2

    def test_similarity_same(self):
        result = self.engine.check_similarity("替尼", "替尼")
        assert result.overall_similarity > 0.9

    def test_similarity_different(self):
        result = self.engine.check_similarity("替尼", "阿司")
        assert result.overall_similarity < 1.0


# ── Brand Name Engine ──

class TestBrandNameEngine:
    def setup_method(self):
        self.engine = BrandNameEngine(existing_brands=["Gleevec", "Tasigna", "Sprycel"])

    def test_screens_brands(self):
        from drug_naming.models.brand import BrandScreenRequest

        request = BrandScreenRequest(
            proposed_brand_names=["Zelmac", "NovaTab", "Viarux"],
            inn_name="imatinib",
        )
        response = self.engine.screen(request)
        assert len(response.results) == 3
        assert response.top_candidate is not None

    def test_brand_similar_to_inn_flagged(self):
        response = self.engine.screen(
            BrandScreenRequest(proposed_brand_names=["Imatinix"], inn_name="imatinib")
        )
        assert response.results[0].similarity_to_inn > 0

    def test_marketability_scoring(self):
        score = self.engine._marketability_score("Zelmac")
        assert 0.0 <= score <= 1.0
