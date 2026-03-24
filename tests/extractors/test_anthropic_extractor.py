"""Tests for AnthropicExtractor — response parsing, validation, checkpoint.
No actual API calls — tests use mock responses."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cxr_mvp.extractors.anthropic_extractor import (
    AnthropicExtractor,
    parse_llm_response,
    validate_extraction,
)


VALID_RESPONSE = json.dumps({
    "classification": "normal",
    "findings": {
        "atelectasis": {"status": "Absent", "confidence": "high", "evidence": None},
        "cardiomegaly": {"status": "Negative", "confidence": "high", "evidence": "Área cardíaca dentro dos limites"},
        "consolidation": {"status": "Absent", "confidence": "high", "evidence": None},
        "edema": {"status": "Absent", "confidence": "high", "evidence": None},
        "effusion": {"status": "Absent", "confidence": "high", "evidence": None},
        "emphysema": {"status": "Absent", "confidence": "high", "evidence": None},
        "fibrosis": {"status": "Absent", "confidence": "high", "evidence": None},
        "fracture": {"status": "Absent", "confidence": "high", "evidence": None},
        "hernia": {"status": "Absent", "confidence": "high", "evidence": None},
        "infiltration": {"status": "Absent", "confidence": "high", "evidence": None},
        "lung_lesion": {"status": "Absent", "confidence": "high", "evidence": None},
        "lung_opacity": {"status": "Absent", "confidence": "high", "evidence": None},
        "mass": {"status": "Absent", "confidence": "high", "evidence": None},
        "nodule": {"status": "Absent", "confidence": "high", "evidence": None},
        "pleural_thickening": {"status": "Absent", "confidence": "high", "evidence": None},
        "pneumonia": {"status": "Absent", "confidence": "high", "evidence": None},
        "pneumothorax": {"status": "Absent", "confidence": "high", "evidence": None},
        "enlarged_cardiomediastinum": {"status": "Absent", "confidence": "high", "evidence": None},
    },
})


class TestParseLlmResponse:
    def test_parses_clean_json(self):
        data = parse_llm_response(VALID_RESPONSE)
        assert data["classification"] == "normal"

    def test_strips_markdown_fences(self):
        fenced = f"```json\n{VALID_RESPONSE}\n```"
        data = parse_llm_response(fenced)
        assert data["classification"] == "normal"

    def test_strips_bare_backticks(self):
        fenced = f"```\n{VALID_RESPONSE}\n```"
        data = parse_llm_response(fenced)
        assert data["classification"] == "normal"

    def test_raises_on_malformed_json(self):
        with pytest.raises(json.JSONDecodeError):
            parse_llm_response("not json at all")

    def test_raises_on_empty_string(self):
        with pytest.raises(json.JSONDecodeError):
            parse_llm_response("")


class TestValidateExtraction:
    def test_valid_response(self):
        data = json.loads(VALID_RESPONSE)
        expected = list(data["findings"].keys())  # all 18
        result, error = validate_extraction(data, "abc123", "prompthash", "sonnet", expected)
        assert error is None
        assert result is not None
        assert result.report_hash == "abc123"
        assert result.classification == "normal"
        assert result.extraction_model == "sonnet"

    def test_missing_findings_rejected(self):
        expected = ["cardiomegaly", "effusion", "pneumothorax"]  # explicit list
        data = {"classification": "normal", "findings": {"cardiomegaly": {"status": "Absent"}}}
        result, error = validate_extraction(data, "abc", "ph", "sonnet", expected)
        assert result is None
        assert "missing_findings" in error

    def test_invalid_classification_rejected(self):
        data = json.loads(VALID_RESPONSE)
        data["classification"] = "maybe"
        result, error = validate_extraction(data, "abc", "ph", "sonnet", [])
        assert result is None
        assert "invalid_classification" in error

    def test_portuguese_status_normalized(self):
        data = json.loads(VALID_RESPONSE)
        data["findings"]["cardiomegaly"]["status"] = "positivo"
        result, error = validate_extraction(data, "abc", "ph", "sonnet", [])
        assert error is None
        # Pydantic normalizes "positivo" -> "Positive"


class TestAnthropicExtractorInit:
    def test_creates_with_config(self):
        ext = AnthropicExtractor(
            config_name="sonnet",
            model_id="claude-sonnet-4-6-20250514",
            mode="sync",
        )
        assert ext.name() == "sonnet"
        assert ext.version() == "claude-sonnet-4-6-20250514"
        assert ext.supports_batch() is True  # Anthropic always supports batch

    def test_name_from_config(self):
        ext = AnthropicExtractor(config_name="opus", model_id="claude-opus-4-6-20250514")
        assert ext.name() == "opus"


MOCK_LLM_RESPONSE = json.dumps({
    "classification": "normal",
    "findings": {"cardiomegaly": {"status": "Negative", "confidence": "high", "evidence": "Normal"}},
    "other_findings": [],
    "study_quality": "adequate",
    "study_quality_flags": [],
})


VALID_RESPONSE_V2 = json.dumps({
    "classification": "abnormal",
    "findings": {
        "pneumothorax": {"status": "Absent", "confidence": "high", "evidence": None},
        "cardiomegaly": {"status": "Positive", "confidence": "high", "evidence": "Cardiomegalia"},
    },
    "other_findings": [
        {"name": "bronchiectasis", "original_term": "bronquiectasias",
         "status": "Positive", "confidence": "high",
         "evidence": "Bronquiectasias em lobos inferiores",
         "suggested_category": "pulmonary"},
    ],
    "study_quality": "suboptimal",
    "study_quality_flags": ["bedside", "rotation"],
})


class TestValidateExtractionV2:
    def test_parses_other_findings(self):
        data = json.loads(VALID_RESPONSE_V2)
        result, error = validate_extraction(data, "abc", "ph", "sonnet", [])
        assert error is None
        assert len(result.other_findings) == 1
        assert result.other_findings[0]["name"] == "bronchiectasis"

    def test_parses_study_quality(self):
        data = json.loads(VALID_RESPONSE_V2)
        result, error = validate_extraction(data, "abc", "ph", "sonnet", [])
        assert error is None
        assert result.study_quality == "suboptimal"
        assert "bedside" in result.study_quality_flags

    def test_missing_other_findings_defaults_empty(self):
        data = {"classification": "normal", "findings": {}}
        result, error = validate_extraction(data, "abc", "ph", "sonnet", [])
        assert error is None
        assert result.other_findings == []
        assert result.study_quality == "adequate"

    def test_malformed_other_finding_captured(self):
        data = {"classification": "normal", "findings": {},
                "other_findings": [{"name": "test"}]}  # missing required fields
        result, error = validate_extraction(data, "abc", "ph", "sonnet", [])
        assert error is None
        # Malformed entry captured, not dropped
        assert len(result.other_findings) == 1


class TestCheckpointResume:
    def test_skips_completed_hashes(self, tmp_path):
        output_dir = str(tmp_path)
        ext = AnthropicExtractor(config_name="test", model_id="test-model", mode="sync")

        # Pre-populate checkpoint file
        checkpoint_path = tmp_path / "extractions_test.jsonl"
        checkpoint_path.write_text(
            json.dumps({"report_hash": "already_done", "classification": "normal",
                        "findings": {}, "extraction_model": "test",
                        "prompt_hash": "ph", "timestamp": "t"}) + "\n"
        )

        done = ext._load_completed_hashes(output_dir)
        assert "already_done" in done


class TestExtractAsync:
    def test_processes_reports_concurrently(self, tmp_path, monkeypatch):
        """Verify async extraction produces results for all reports."""
        from cxr_mvp.models import UniqueReport

        # Run from tmp_path so config/findings_cxr.yaml is not found
        # (avoids expected_findings validation against incomplete mock)
        monkeypatch.chdir(tmp_path)

        reports = [
            UniqueReport(report_hash=f"hash_{i}", report_text=f"Report {i}",
                         exam_count=1, sample_exam_id=f"E{i}")
            for i in range(5)
        ]

        ext = AnthropicExtractor(config_name="test", model_id="test-model", mode="sync")

        # Mock the async Anthropic client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=MOCK_LLM_RESPONSE)]

        with patch("cxr_mvp.extractors.anthropic_extractor.AsyncAnthropic") as MockClient:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_client

            results = asyncio.run(
                ext.extract_async(reports, "Test {REPORT_TEXT}", str(tmp_path), concurrency=3)
            )

        assert len(results) == 5
        assert all(r.classification == "normal" for r in results)

    def test_respects_checkpoint(self, tmp_path):
        """Reports already in checkpoint file are skipped."""
        from cxr_mvp.models import UniqueReport

        # Pre-populate checkpoint
        checkpoint = tmp_path / "extractions_test.jsonl"
        checkpoint.write_text(
            json.dumps({"report_hash": "hash_0", "classification": "normal",
                        "findings": {}, "other_findings": [],
                        "extraction_model": "test", "prompt_hash": "ph",
                        "timestamp": "t", "study_quality": "adequate",
                        "study_quality_flags": []}) + "\n"
        )

        reports = [
            UniqueReport(report_hash="hash_0", report_text="Already done",
                         exam_count=1, sample_exam_id="E0"),
            UniqueReport(report_hash="hash_1", report_text="New report",
                         exam_count=1, sample_exam_id="E1"),
        ]

        ext = AnthropicExtractor(config_name="test", model_id="test-model", mode="sync")

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=MOCK_LLM_RESPONSE)]

        with patch("cxr_mvp.extractors.anthropic_extractor.AsyncAnthropic") as MockClient:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_client

            results = asyncio.run(
                ext.extract_async(reports, "Test {REPORT_TEXT}", str(tmp_path), concurrency=3)
            )

        # Only hash_1 was extracted (hash_0 skipped via checkpoint)
        assert mock_client.messages.create.call_count == 1

    def test_concurrency_limits_parallel_calls(self, tmp_path):
        """Semaphore limits concurrent API calls."""
        from cxr_mvp.models import UniqueReport
        import time

        reports = [
            UniqueReport(report_hash=f"hash_{i}", report_text=f"Report {i}",
                         exam_count=1, sample_exam_id=f"E{i}")
            for i in range(10)
        ]

        ext = AnthropicExtractor(config_name="test", model_id="test-model", mode="sync")

        call_times = []

        async def slow_create(**kwargs):
            call_times.append(time.monotonic())
            await asyncio.sleep(0.05)
            mock_resp = MagicMock()
            mock_resp.content = [MagicMock(text=MOCK_LLM_RESPONSE)]
            return mock_resp

        with patch("cxr_mvp.extractors.anthropic_extractor.AsyncAnthropic") as MockClient:
            mock_client = AsyncMock()
            mock_client.messages.create = slow_create
            MockClient.return_value = mock_client

            asyncio.run(
                ext.extract_async(reports, "Test {REPORT_TEXT}", str(tmp_path), concurrency=3)
            )

        assert len(call_times) == 10


class TestExtractAsyncRetry:
    def test_retries_on_transient_error(self, tmp_path, monkeypatch):
        """Transient errors are retried up to 3 times."""
        from cxr_mvp.models import UniqueReport
        from cxr_mvp.config import load_findings_config
        load_findings_config.cache_clear()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())

        reports = [
            UniqueReport(report_hash="hash_retry", report_text="Retry test",
                         exam_count=1, sample_exam_id="E0"),
        ]
        ext = AnthropicExtractor(config_name="test", model_id="test-model", mode="sync")

        call_count = 0
        async def flaky_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Connection reset")
            mock_resp = MagicMock()
            mock_resp.content = [MagicMock(text=MOCK_LLM_RESPONSE)]
            return mock_resp

        with patch("cxr_mvp.extractors.anthropic_extractor.AsyncAnthropic") as MockClient:
            mock_client = AsyncMock()
            mock_client.messages.create = flaky_create
            MockClient.return_value = mock_client

            results = asyncio.run(
                ext.extract_async(reports, "Test {REPORT_TEXT}", str(tmp_path), concurrency=1)
            )

        assert len(results) == 1  # succeeded after retries
        assert call_count == 3  # failed twice, succeeded on third

    def test_gives_up_after_max_retries(self, tmp_path, monkeypatch):
        """After max retries, error is logged and report is skipped."""
        from cxr_mvp.models import UniqueReport
        from cxr_mvp.config import load_findings_config
        load_findings_config.cache_clear()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())

        reports = [
            UniqueReport(report_hash="hash_fail", report_text="Always fail",
                         exam_count=1, sample_exam_id="E0"),
        ]
        ext = AnthropicExtractor(config_name="test", model_id="test-model", mode="sync")

        async def always_fail(**kwargs):
            raise Exception("Permanent failure")

        with patch("cxr_mvp.extractors.anthropic_extractor.AsyncAnthropic") as MockClient:
            mock_client = AsyncMock()
            mock_client.messages.create = always_fail
            MockClient.return_value = mock_client

            results = asyncio.run(
                ext.extract_async(reports, "Test {REPORT_TEXT}", str(tmp_path), concurrency=1)
            )

        assert len(results) == 0  # gave up
        # Error should be logged
        errors_path = tmp_path / "extraction_errors_test.jsonl"
        assert errors_path.exists()
        with open(errors_path) as f:
            errors = [json.loads(l) for l in f]
        assert len(errors) == 1
        assert "Permanent failure" in errors[0]["error"]
