"""Core data models. Every component reads/writes these typed structures.
Label states aligned with Playbook v3 for seamless production transition."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from pydantic import BaseModel, field_validator


# === Label Vocabulary (Playbook v3 compatible) ===

class LabelState(str, Enum):
    POSITIVE = "Positive"
    NEGATIVE = "Negative"
    UNCERTAIN = "Uncertain"
    ABSENT = "Absent"
    NOT_ASSESSABLE = "Not_Assessable"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# === CSV Ingestion Models ===

@dataclass
class ExamRecord:
    """One exam from the CSV after ingestion and deduplication."""
    exam_id: str
    customer_id: str
    dicom_filenames: list  # PA, lateral, etc. (extracted from URL path)
    report_hash: str       # SHA-256 of normalized report text (join key)
    original_label: int    # 1=normal, 2=abnormal (from CSV, unreliable)
    report_length: int


@dataclass
class UniqueReport:
    """One unique report text for extraction (keyed by report_hash)."""
    report_hash: str
    report_text: str
    exam_count: int        # how many exams share this exact text
    sample_exam_id: str    # one example exam_id for reference


# === Extraction Result (persisted output of Stage 1) ===

@dataclass
class ExtractionResult:
    """One completed extraction, keyed by report_hash (not exam_id).
    Written to extractions_{model_name}.jsonl."""
    report_hash: str
    classification: str           # "normal" | "abnormal"
    findings: dict                # {finding: {status, confidence, evidence}}
    extraction_model: str         # config name: "sonnet", "opus" (not raw model_id)
    prompt_hash: str              # SHA-256 of prompt used
    timestamp: str                # ISO 8601
    other_findings: list = field(default_factory=list)
    study_quality: str = "adequate"
    study_quality_flags: list = field(default_factory=list)
    ontology_version: str = ""
    extraction_schema: str = "v2"


@dataclass
class ValidatedExtraction(ExtractionResult):
    """Post-validation extraction with computed triage fields (Stage 1.5)."""
    priority_level: str = "NONE"
    needs_review: bool = False
    review_reasons: list = field(default_factory=list)
    original_classification: str = ""
    acute_classification: str = "normal"
    rule_warnings: list = field(default_factory=list)


# === Text Extraction Output (Sonnet Batch API) ===

_STATUS_ALIASES: dict[str, str] = {
    "present": "Positive", "absent": "Absent",
    "positive": "Positive", "negative": "Negative",
    "uncertain": "Uncertain", "normal": "Negative",
    "positivo": "Positive", "negativo": "Negative",
    "ausente": "Absent", "incerto": "Uncertain",
}


def _normalize_status_value(v: str) -> str:
    """Normalize LLM status output variations (English, Portuguese, lowercase)."""
    if isinstance(v, str):
        return _STATUS_ALIASES.get(v.lower(), v)
    return v


class FindingLabel(BaseModel):
    """One finding extracted from a Portuguese radiology report."""
    status: LabelState
    confidence: Confidence = Confidence.MEDIUM
    evidence: Optional[str] = None  # exact PT quote from report

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: str) -> str:
        return _normalize_status_value(v)


class OtherFinding(BaseModel):
    """Tier 2 discovered finding from LLM response."""
    name: str
    original_term: str
    status: LabelState
    confidence: Confidence = Confidence.MEDIUM
    evidence: Optional[str] = None
    suggested_category: str = "other"

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: str) -> str:
        return _normalize_status_value(v)


class ReportExtraction(BaseModel):
    """Pydantic validation schema for LLM JSON response. v2."""
    exam_id: Optional[str] = None
    classification: str  # "normal" | "abnormal"
    findings: dict[str, FindingLabel]
    other_findings: list[OtherFinding] = []
    study_quality: str = "adequate"
    study_quality_flags: list[str] = []
    report_language: str = "pt"
    extraction_model: str = "claude-sonnet-4-6"


# === Ground Truth Row ===

@dataclass
class GroundTruthRow:
    """One row in the ground truth dataset (one per exam_id)."""
    exam_id: str
    customer_id: str
    classification: str  # "normal" | "abnormal"
    findings: dict  # {finding_name: {status, confidence, evidence}}

    # Provenance
    dicom_filenames: list = field(default_factory=list)
    report_hash: Optional[str] = None
    original_label: Optional[int] = None  # 1=normal, 2=abnormal (CSV, unreliable)
    extraction_model: Optional[str] = None
    prompt_hash: Optional[str] = None

    # Patient ID — NOT in CSV. Populated from DICOM metadata in Stage 3.
    patient_id: Optional[str] = None

    # Multi-model agreement (populated in Stage 2 from agreement_report.json)
    inter_model_agreement: float = 1.0
    has_disagreement: bool = False
    disagreement_findings: list = field(default_factory=list)
    primary_model: str = ""

    # DICOM metadata — populated in Stage 3
    body_part: str = "CXR"
    view_position: Optional[str] = None
    portable_flag: bool = False
    quality_status: Optional[str] = None
    quality_flags: list = field(default_factory=list)


# === Vision Model Prediction ===

@dataclass
class ModelPrediction:
    """One prediction from a vision backend for one study."""
    exam_id: str
    model_name: str
    model_version: str

    # Binary classification
    binary_label: str  # "normal" | "abnormal"
    binary_score: Optional[float] = None  # 0-1

    # Per-finding predictions
    findings: dict = field(default_factory=dict)
    # {finding_name: {"label": str, "score": float}}

    # Provenance
    inference_timestamp: Optional[str] = None
    config_hash: Optional[str] = None


# === Run Manifest (provenance) ===

@dataclass
class RunManifest:
    """Reproducibility metadata for every pipeline stage."""
    stage: str
    timestamp: str
    code_commit: Optional[str] = None
    input_hash: Optional[str] = None
    config_hash: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    n_processed: int = 0
    n_errors: int = 0
    # Pipeline-specific extensions
    pipeline_version: str = "v6"
    prompt_hash: Optional[str] = None
    extraction_mode: Optional[str] = None  # "sync" | "batch"
    n_exams: int = 0
    n_unique_reports: int = 0
    n_extracted: int = 0
    n_balanced: int = 0


def get_finding_status(data) -> str:
    """Extract status from a finding data dict. Returns 'Absent' if missing."""
    if isinstance(data, dict):
        return data.get("status", "Absent")
    return "Absent"
