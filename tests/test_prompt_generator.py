"""Tests for config-driven prompt generation."""
from __future__ import annotations

import hashlib

import pytest

from cxr_mvp.prompt_generator import generate_prompt, prompt_hash


class TestGeneratePrompt:
    def test_returns_string(self):
        text = generate_prompt()
        assert isinstance(text, str)
        assert len(text) > 1000  # prompt is substantial

    def test_contains_all_40_findings(self):
        text = generate_prompt()
        from cxr_mvp.config import load_findings_config
        config = load_findings_config()
        for name in config.finding_names():
            assert name in text, f"Missing finding: {name}"

    def test_contains_pt_synonyms(self):
        text = generate_prompt()
        assert "pneumotórax" in text
        assert "cardiomegalia" in text
        assert "espondilose" in text
        assert "tubo orotraqueal" in text

    def test_contains_other_findings_instruction(self):
        text = generate_prompt()
        assert "other_findings" in text
        assert "ACHADOS ADICIONAIS" in text

    def test_contains_study_quality_instruction(self):
        text = generate_prompt()
        assert "study_quality" in text
        assert "QUALIDADE DO ESTUDO" in text

    def test_contains_report_text_placeholder(self):
        text = generate_prompt()
        assert "{REPORT_TEXT}" in text

    def test_contains_json_schema(self):
        text = generate_prompt()
        assert '"classification"' in text
        assert '"findings"' in text
        assert '"other_findings"' in text
        assert '"study_quality"' in text

    def test_contains_tier2_naming_instruction(self):
        text = generate_prompt()
        # Should instruct short canonical names
        assert "curto" in text.lower() or "short" in text.lower() or "conciso" in text.lower()

    def test_tier2_excludes_normal_anatomy(self):
        text = generate_prompt()
        assert "anatomia NORMAL" in text or "NORMAL" in text
        assert "ANORMAL" in text or "PATOLÓGICO" in text

    def test_tier2_no_tier1_duplicates(self):
        text = generate_prompt()
        assert "NÃO reporte achados já cobertos" in text

    def test_study_quality_flag_consistency(self):
        text = generate_prompt()
        assert "pelo menos um flag" in text

    def test_deterministic(self):
        t1 = generate_prompt()
        t2 = generate_prompt()
        assert t1 == t2


class TestPromptHash:
    def test_returns_hex_string(self):
        h = prompt_hash()
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        assert prompt_hash() == prompt_hash()
