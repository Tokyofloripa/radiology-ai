"""Tests for Portuguese medical text rule checks."""
from __future__ import annotations

import pytest

from cxr_mvp.pt_rules import (
    check_negation_consistency,
    check_hedging_consistency,
    check_chronicity,
    check_extraction,
)


class TestNegationConsistency:
    def test_positive_with_negation_warns(self):
        warning = check_negation_consistency(
            "effusion", "Positive", "sem sinais de derrame pleural"
        )
        assert warning is not None
        assert "negation" in warning.lower()

    def test_positive_without_negation_ok(self):
        warning = check_negation_consistency(
            "effusion", "Positive", "Derrame pleural à esquerda"
        )
        assert warning is None

    def test_negative_with_negation_ok(self):
        warning = check_negation_consistency(
            "effusion", "Negative", "sem sinais de derrame pleural"
        )
        assert warning is None

    def test_absent_skipped(self):
        warning = check_negation_consistency("effusion", "Absent", None)
        assert warning is None

    def test_preservado_pattern(self):
        warning = check_negation_consistency(
            "cardiomegaly", "Positive", "Mediastino de contornos preservados"
        )
        assert warning is not None

    def test_dentro_da_normalidade(self):
        warning = check_negation_consistency(
            "cardiomegaly", "Positive", "Área cardíaca dentro da normalidade"
        )
        assert warning is not None


class TestHedgingConsistency:
    def test_positive_with_hedging_warns(self):
        warning = check_hedging_consistency(
            "pneumonia", "Positive", "não se pode excluir processo pneumônico"
        )
        assert warning is not None
        assert "hedging" in warning.lower() or "uncertain" in warning.lower()

    def test_uncertain_with_hedging_ok(self):
        warning = check_hedging_consistency(
            "pneumonia", "Uncertain", "não se pode excluir processo pneumônico"
        )
        assert warning is None

    def test_positive_without_hedging_ok(self):
        warning = check_hedging_consistency(
            "pneumonia", "Positive", "Pneumonia em base direita"
        )
        assert warning is None

    def test_possivel_pattern(self):
        warning = check_hedging_consistency(
            "consolidation", "Positive", "Possível consolidação em base"
        )
        assert warning is not None

    def test_a_esclarecer_pattern(self):
        warning = check_hedging_consistency(
            "mass", "Positive", "lesão a esclarecer"
        )
        assert warning is not None


class TestChronicity:
    def test_sequela_detected(self):
        result = check_chronicity("Sequela de processo infeccioso prévio")
        assert result is True

    def test_cronico_detected(self):
        result = check_chronicity("Processo crônico em bases")
        assert result is True

    def test_acute_not_flagged(self):
        result = check_chronicity("Consolidação em base direita")
        assert result is False

    def test_none_evidence(self):
        result = check_chronicity(None)
        assert result is False


class TestCheckExtraction:
    def test_returns_warnings_for_issues(self):
        findings = {
            "effusion": {"status": "Positive", "evidence": "sem sinais de derrame"},
            "pneumonia": {"status": "Positive", "evidence": "não se pode excluir pneumonia"},
            "cardiomegaly": {"status": "Negative", "evidence": "Área cardíaca normal"},
        }
        warnings = check_extraction(findings)
        assert len(warnings) >= 2  # negation + hedging

    def test_clean_extraction_no_warnings(self):
        findings = {
            "effusion": {"status": "Positive", "evidence": "Derrame pleural à esquerda"},
            "cardiomegaly": {"status": "Negative", "evidence": "Área cardíaca normal"},
        }
        warnings = check_extraction(findings)
        assert len(warnings) == 0

    def test_warning_structure(self):
        findings = {
            "effusion": {"status": "Positive", "evidence": "sem sinais de derrame"},
        }
        warnings = check_extraction(findings)
        assert len(warnings) == 1
        assert "finding" in warnings[0]
        assert "rule" in warnings[0]
        assert warnings[0]["finding"] == "effusion"
