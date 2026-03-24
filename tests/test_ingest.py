"""Tests for CSV ingestion, text normalization, and SHA-256 dedup."""
from __future__ import annotations

import hashlib
import unicodedata
import re

import pytest

from cxr_mvp.ingest import (
    normalize_report,
    report_hash,
    extract_dicom_filename,
    ingest_csv,
)
from cxr_mvp.models import ExamRecord, UniqueReport


class TestNormalizeReport:
    def test_strips_whitespace(self):
        assert normalize_report("  hello  ") == "hello"

    def test_collapses_internal_whitespace(self):
        assert normalize_report("hello   world") == "hello world"

    def test_preserves_case(self):
        assert normalize_report("Área Cardíaca") == "Área Cardíaca"

    def test_nfc_normalization(self):
        # Composed vs decomposed Portuguese accent
        composed = "Área"  # NFC
        decomposed = unicodedata.normalize("NFD", composed)
        assert normalize_report(composed) == normalize_report(decomposed)

    def test_empty_string(self):
        assert normalize_report("") == ""


class TestReportHash:
    def test_deterministic(self):
        h1 = report_hash("Área cardíaca normal")
        h2 = report_hash("Área cardíaca normal")
        assert h1 == h2

    def test_whitespace_insensitive(self):
        h1 = report_hash("hello   world")
        h2 = report_hash("hello world")
        assert h1 == h2

    def test_different_text_different_hash(self):
        h1 = report_hash("normal")
        h2 = report_hash("abnormal")
        assert h1 != h2

    def test_returns_hex_string(self):
        h = report_hash("test")
        assert len(h) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in h)


class TestExtractDicomFilename:
    def test_extracts_filename_from_url(self):
        url = "http://clirea.ptmdocs.com.br/prd/10794085-PA.dcm"
        assert extract_dicom_filename(url) == "10794085-PA.dcm"

    def test_handles_trailing_slash(self):
        url = "http://example.com/files/"
        result = extract_dicom_filename(url)
        assert isinstance(result, str)


class TestIngestCsv:
    def test_returns_exam_records_and_unique_reports(self, sample_csv_file):
        exams, reports, errors = ingest_csv(sample_csv_file)
        assert isinstance(exams, list)
        assert isinstance(reports, list)
        assert all(isinstance(e, ExamRecord) for e in exams)
        assert all(isinstance(r, UniqueReport) for r in reports)

    def test_dedup_by_exam_id(self, sample_csv_file):
        """Two rows with same exam_id (PA + LAT) -> one ExamRecord with 2 DICOMs."""
        exams, _, _ = ingest_csv(sample_csv_file)
        exam_10794085 = [e for e in exams if e.exam_id == "10794085"]
        assert len(exam_10794085) == 1
        assert len(exam_10794085[0].dicom_filenames) == 2

    def test_dedup_by_report_hash(self, sample_csv_file):
        """Two exams sharing identical text -> one UniqueReport (exam_count=1 since
        the two rows are the same exam_id with 2 DICOM views)."""
        _, reports, _ = ingest_csv(sample_csv_file)
        # We have 2 distinct report texts (10794085 and 10794086)
        assert len(reports) == 2

    def test_rejects_garbage_reports(self, sample_csv_file):
        """Empty report (<10 chars) -> rejected."""
        _, _, errors = ingest_csv(sample_csv_file)
        assert len(errors) >= 1
        assert any("report_too_short" in str(e) for e in errors)

    def test_report_hash_on_exam_record(self, sample_csv_file):
        exams, _, _ = ingest_csv(sample_csv_file)
        for exam in exams:
            assert exam.report_hash is not None
            assert len(exam.report_hash) == 64

    def test_original_label_preserved(self, sample_csv_file):
        exams, _, _ = ingest_csv(sample_csv_file)
        labels = {e.exam_id: e.original_label for e in exams}
        assert labels["10794085"] == 1
        assert labels["10794086"] == 2

    def test_handles_utf8_bom(self, sample_csv_file):
        """CSV written with BOM — should parse without issues."""
        exams, _, _ = ingest_csv(sample_csv_file)
        assert len(exams) >= 2
