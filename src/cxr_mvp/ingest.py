"""Stage 0: CSV ingestion, text normalization, SHA-256 dedup.

Reads ListaLLM.csv (no header, semicolons, UTF-8 BOM).
Produces ExamRecord list (one per exam_id) and UniqueReport list (one per report_hash).
"""
from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

from cxr_mvp.models import ExamRecord, UniqueReport


def normalize_report(text: str) -> str:
    """Deterministic text normalization for dedup hashing.

    Steps (in order):
    1. Strip leading/trailing whitespace
    2. Collapse internal whitespace to single space
    3. NFC Unicode normalization (canonical PT accents)
    4. No case change
    """
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    text = unicodedata.normalize("NFC", text)
    return text


def report_hash(text: str) -> str:
    """SHA-256 of normalized report text. The dedup + join key."""
    normalized = normalize_report(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def extract_dicom_filename(url: str) -> str:
    """Extract DICOM filename from download URL path."""
    parsed = urlparse(url)
    return parsed.path.split("/")[-1]


def ingest_csv(
    csv_path: str,
    min_report_length: int = 10,
) -> tuple[list[ExamRecord], list[UniqueReport], list[dict]]:
    """Parse ListaLLM.csv, normalize, deduplicate.

    Returns:
        (exam_records, unique_reports, errors)
    """
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=";", quotechar='"')
        rows = list(reader)

    # Group by exam_id (multiple rows = multiple DICOM views)
    exam_groups: dict[str, dict] = defaultdict(
        lambda: {
            "customer_id": None,
            "dicom_filenames": [],
            "report_text": None,
            "original_label": None,
        }
    )

    for row in rows:
        if len(row) < 5:
            continue
        exam_id = row[0].strip()
        customer_id = row[1].strip()
        dicom_url = row[2].strip()
        report_text = row[3]
        label_str = row[4].strip()

        g = exam_groups[exam_id]
        g["customer_id"] = customer_id
        g["dicom_filenames"].append(extract_dicom_filename(dicom_url))
        g["report_text"] = report_text
        g["original_label"] = int(label_str) if label_str.isdigit() else None

    # Build exam registry + unique reports
    exam_records: list[ExamRecord] = []
    unique_map: dict[str, dict] = {}  # report_hash -> accumulator
    errors: list[dict] = []

    for exam_id, g in exam_groups.items():
        text = g["report_text"] or ""
        normalized = normalize_report(text)

        if len(normalized) < min_report_length:
            errors.append({
                "exam_id": exam_id,
                "reason": "report_too_short",
                "report_length": len(normalized),
            })
            continue

        rhash = report_hash(text)

        exam_records.append(ExamRecord(
            exam_id=exam_id,
            customer_id=g["customer_id"],
            dicom_filenames=g["dicom_filenames"],
            report_hash=rhash,
            original_label=g["original_label"],
            report_length=len(normalized),
        ))

        if rhash not in unique_map:
            unique_map[rhash] = {
                "report_hash": rhash,
                "report_text": normalized,
                "exam_count": 0,
                "sample_exam_id": exam_id,
            }
        unique_map[rhash]["exam_count"] += 1

    unique_reports = [
        UniqueReport(**data) for data in unique_map.values()
    ]

    return exam_records, unique_reports, errors
