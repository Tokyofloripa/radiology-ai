"""Post-extraction validation — ghost-abnormal check, critical override, triage priority.

Stage 1.5: reads ExtractionResult, produces ValidatedExtraction.
Core principle: never downgrade. Only upgrade when evidence demands it."""
from __future__ import annotations

from cxr_mvp.config import load_findings_config
from cxr_mvp.models import ExtractionResult, ValidatedExtraction, get_finding_status

# Priority order (highest first)
_PRIORITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "LOW": 1, "NONE": 0}


def _load_priority_map(config_path: str = "config/findings_cxr.yaml") -> dict[str, str]:
    """Build {finding_name: priority} from config."""
    config = load_findings_config(config_path)
    return {name: f.priority for name, f in config.findings.items()}


def compute_priority(
    findings: dict,
    other_findings: list,
    priority_map: dict[str, str] | None = None,
    config_path: str = "config/findings_cxr.yaml",
) -> str:
    """Compute triage priority from highest-priority Positive/Uncertain finding."""
    if priority_map is None:
        priority_map = _load_priority_map(config_path)
    highest = "NONE"

    for name, data in findings.items():
        status = get_finding_status(data)
        if status in ("Positive", "Uncertain"):
            finding_priority = priority_map.get(name, "MODERATE")
            if _PRIORITY_ORDER.get(finding_priority, 0) > _PRIORITY_ORDER.get(highest, 0):
                highest = finding_priority

    # Tier 2 discoveries default to MODERATE
    for f in other_findings:
        status = get_finding_status(f)
        if status in ("Positive", "Uncertain"):
            if _PRIORITY_ORDER.get("MODERATE", 0) > _PRIORITY_ORDER.get(highest, 0):
                highest = "MODERATE"

    return highest


def _has_positive_or_uncertain(findings: dict, other_findings: list) -> bool:
    """Check if any finding (Tier 1 or 2) is Positive or Uncertain."""
    for data in findings.values():
        status = get_finding_status(data)
        if status in ("Positive", "Uncertain"):
            return True
    for f in other_findings:
        status = get_finding_status(f)
        if status in ("Positive", "Uncertain"):
            return True
    return False


def validate_extraction(
    result: ExtractionResult,
    config_path: str = "config/findings_cxr.yaml",
) -> ValidatedExtraction:
    """Apply validation rules to raw extraction. Returns ValidatedExtraction."""
    # Load config once for all rules
    config = None
    try:
        config = load_findings_config(config_path)
    except FileNotFoundError:
        pass

    priority_map = {name: f.priority for name, f in config.findings.items()} if config else None
    priority = compute_priority(result.findings, result.other_findings, priority_map=priority_map)
    has_evidence = _has_positive_or_uncertain(result.findings, result.other_findings)

    classification = result.classification
    review_reasons: list[str] = []
    original_classification = ""

    # Rule 1: Ghost-abnormal flagging
    if classification == "abnormal" and not has_evidence:
        review_reasons.append("no_supporting_findings")

    # Rule 2: Critical-finding override
    if classification == "normal" and priority == "CRITICAL":
        original_classification = classification
        classification = "abnormal"
        review_reasons.append("critical_finding_override")

    # Rule 3: High uncertainty (3+ Uncertain findings)
    uncertainty_count = sum(
        1 for data in result.findings.values()
        if get_finding_status(data) == "Uncertain"
    )
    if uncertainty_count >= 3:
        review_reasons.append("high_uncertainty")

    # Rule 4: Critical finding on suboptimal study
    if result.study_quality == "suboptimal" and priority == "CRITICAL":
        review_reasons.append("critical_on_suboptimal")

    # Rule 5: Device present without position assessment
    if config is not None:
        device_findings = {name for name, f in config.findings.items() if f.type == "device_presence"}
    else:
        device_findings = {"endotracheal_tube", "central_line", "feeding_tube", "chest_drain"}
    has_device = any(
        get_finding_status(result.findings.get(d, {})) == "Positive"
        for d in device_findings
    )
    malposition_status = get_finding_status(result.findings.get("device_malposition", {}))
    if has_device and malposition_status == "Absent":
        review_reasons.append("device_without_position")

    # Rule 6: Hierarchy consistency — child Positive/Uncertain → parent cannot be Absent
    if config is not None:
        for child_name, f_def in config.findings.items():
            if f_def.parent is None:
                continue
            child_status = get_finding_status(result.findings.get(child_name, {}))
            parent_status = get_finding_status(result.findings.get(f_def.parent, {}))
            if child_status in ("Positive", "Uncertain") and parent_status in ("Absent", "Negative"):
                review_reasons.append("hierarchy_inconsistency")
                break  # one inconsistency is enough to flag

    # PT rule checks (negation/hedging consistency)
    from cxr_mvp.pt_rules import check_extraction
    rule_warnings = check_extraction(result.findings)

    needs_review = len(review_reasons) > 0

    # Normal exams have no triage priority regardless of individual findings
    if classification == "normal":
        priority = "NONE"

    # Compute acute classification
    # Only findings with acuity in (acute, context_dependent) AND status Positive/Uncertain
    if config is not None:
        acute_positive = any(
            get_finding_status(result.findings.get(name, {})) in ("Positive", "Uncertain")
            for name, f in config.findings.items()
            if f.acuity in ("acute", "context_dependent")
        )
        acute_classification = "abnormal" if acute_positive else "normal"
    else:
        acute_classification = classification  # fallback: use overall classification

    return ValidatedExtraction(
        report_hash=result.report_hash,
        classification=classification,
        findings=result.findings,
        other_findings=result.other_findings,
        extraction_model=result.extraction_model,
        prompt_hash=result.prompt_hash,
        timestamp=result.timestamp,
        study_quality=result.study_quality,
        study_quality_flags=result.study_quality_flags,
        priority_level=priority,
        needs_review=needs_review,
        review_reasons=review_reasons,
        original_classification=original_classification,
        acute_classification=acute_classification,
        rule_warnings=rule_warnings,
    )
