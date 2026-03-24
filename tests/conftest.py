"""Shared fixtures for cxr-mvp tests."""
from __future__ import annotations

import numpy as np
import pytest


# === Portuguese Report Fixtures ===

@pytest.fixture
def sample_report_normal() -> str:
    """Normal CXR report in Portuguese."""
    return (
        "Indicação: Dor torácica.\n"
        "Achados: Área cardíaca dentro dos limites da normalidade. "
        "Campos pulmonares sem opacidades. "
        "Seios costofrênicos livres. "
        "Estruturas ósseas sem alterações.\n"
        "Impressão: Radiografia de tórax sem alterações."
    )


@pytest.fixture
def sample_report_abnormal() -> str:
    """Abnormal CXR report with multiple findings."""
    return (
        "Indicação: Dispneia.\n"
        "Achados: Área cardíaca aumentada. "
        "Velamento do seio costofrênico esquerdo, sugestivo de derrame pleural. "
        "Opacidade em base pulmonar direita, não se pode excluir consolidação. "
        "Demais estruturas sem alterações.\n"
        "Impressão: Cardiomegalia. Derrame pleural à esquerda. "
        "Possível consolidação em base direita, a esclarecer."
    )


@pytest.fixture
def sample_report_negation_heavy() -> str:
    """Report with many negation patterns (edge case for extraction)."""
    return (
        "Achados: Sem sinais de cardiomegalia. "
        "Não se observa derrame pleural. "
        "Ausência de consolidações. "
        "Não há evidências de pneumotórax. "
        "Campos pulmonares dentro da normalidade.\n"
        "Impressão: Exame sem alterações significativas."
    )


@pytest.fixture
def sample_findings_abnormal() -> dict:
    """Ground truth labels for abnormal report."""
    return {
        "cardiomegaly": {"status": "Positive", "confidence": "high"},
        "effusion": {"status": "Positive", "confidence": "medium"},
        "consolidation": {"status": "Uncertain", "confidence": "medium"},
        "atelectasis": {"status": "Absent", "confidence": "high"},
        "pneumothorax": {"status": "Absent", "confidence": "high"},
    }


# === DICOM Fixtures ===

@pytest.fixture
def dummy_pixel_array() -> np.ndarray:
    """Minimal 64x64 float32 array simulating a normalized CXR."""
    rng = np.random.default_rng(42)
    return rng.random((64, 64), dtype=np.float32)


@pytest.fixture
def dummy_dicom_meta() -> dict:
    """Minimal DICOM metadata dict for testing."""
    return {
        "exam_id": "TEST001",
        "patient_id": "PAT001",
        "Modality": "CR",
        "ViewPosition": "PA",
        "BodyPartExamined": "CHEST",
        "Rows": 2048,
        "Columns": 2048,
        "BitsStored": 14,
        "PhotometricInterpretation": "MONOCHROME2",
    }


@pytest.fixture
def dummy_dicom_meta_monochrome1(dummy_dicom_meta) -> dict:
    """DICOM metadata with MONOCHROME1 (needs inversion)."""
    return {**dummy_dicom_meta, "PhotometricInterpretation": "MONOCHROME1"}


# === CSV Ingestion Fixtures ===

@pytest.fixture
def sample_csv_rows() -> list[list[str]]:
    """Raw CSV rows as they come from ListaLLM.csv (no header, semicolons)."""
    return [
        ["10794085", "2779", "http://clirea.ptmdocs.com.br/prd/10794085-PA.dcm",
         "Área cardíaca dentro dos limites. Campos pulmonares sem opacidades.", "1"],
        ["10794085", "2779", "http://clirea.ptmdocs.com.br/prd/10794085-LAT.dcm",
         "Área cardíaca dentro dos limites. Campos pulmonares sem opacidades.", "1"],
        ["10794086", "2780", "http://clirea.ptmdocs.com.br/prd/10794086-PA.dcm",
         "Cardiomegalia. Derrame pleural à esquerda.", "2"],
        ["10794087", "2779", "http://clirea.ptmdocs.com.br/prd/10794087-PA.dcm",
         "", "1"],  # garbage: empty report
    ]


@pytest.fixture
def sample_csv_file(tmp_path, sample_csv_rows) -> str:
    """Write a temporary CSV file matching ListaLLM.csv format."""
    import csv
    csv_path = tmp_path / "test_data.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";", quotechar='"', quoting=csv.QUOTE_MINIMAL)
        for row in sample_csv_rows:
            writer.writerow(row)
    return str(csv_path)
