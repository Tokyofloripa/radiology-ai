"""Inter-model comparison and agreement scoring.

Merges N extraction output files, computes agreement, flags disagreements.
Produces agreement_report.json, disagreements.jsonl, selected_extractions.jsonl."""
from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path

from cxr_mvp.models import get_finding_status


def arbitrate_finding(
    status_a: str,
    status_b: str,
    finding_type: str | None = None,
) -> tuple[str, bool]:
    """Resolve disagreement between two model statuses.

    Returns (resolved_status, needs_review).

    Rules:
    - Agreement -> accept, no review
    - Positive vs Uncertain on etiologic finding -> Uncertain (conservative)
    - Positive vs Uncertain on descriptive finding -> review needed
    - Absent vs Positive -> major disagreement, review
    - Negative vs Absent -> minor, accept the more specific (Negative)
    - Not_Assessable vs anything -> Not_Assessable (conservative)
    """
    # Normalize order for symmetric comparison
    pair = frozenset([status_a, status_b])

    # Agreement
    if status_a == status_b:
        return status_a, False

    # Not_Assessable always wins (conservative)
    if "Not_Assessable" in pair:
        return "Not_Assessable", False

    # Negative vs Absent — minor, both mean "not present"
    if pair == frozenset(["Negative", "Absent"]):
        return "Negative", False

    # Positive vs Uncertain
    if pair == frozenset(["Positive", "Uncertain"]):
        if finding_type == "etiologic":
            return "Uncertain", False  # conservative for diagnoses
        return "Uncertain", True  # needs review for descriptive

    # Absent vs Positive — major disagreement
    if "Absent" in pair and "Positive" in pair:
        return "Positive", True  # keep positive but flag for review

    # Absent vs Uncertain
    if "Absent" in pair and "Uncertain" in pair:
        return "Uncertain", True

    # Negative vs Positive — disagreement
    if pair == frozenset(["Negative", "Positive"]):
        return "Positive", True  # keep positive but flag

    # Negative vs Uncertain
    if pair == frozenset(["Negative", "Uncertain"]):
        return "Uncertain", False  # conservative

    # Default: flag for review
    return status_a, True


def _apply_hierarchy_rollup(
    findings: dict, hierarchy: dict[str, str | None]
) -> dict:
    """Roll up child findings to parent level.

    If consolidation=Positive and lung_opacity=Absent, roll up to
    lung_opacity=Positive (child implies parent).

    Args:
        findings: {finding_name: {status, ...}} dict
        hierarchy: {finding_name: parent_name_or_None} from config
    """
    rolled = dict(findings)  # shallow copy
    for child_name, parent_name in hierarchy.items():
        if parent_name is None:
            continue
        child_data = findings.get(child_name, {})
        child_status = get_finding_status(child_data)
        if child_status in ("Positive", "Uncertain"):
            parent_data = rolled.get(parent_name, {})
            parent_status = get_finding_status(parent_data)
            if parent_status in ("Absent", "Negative"):
                # Roll up: child positive implies parent positive
                rolled[parent_name] = {
                    **(parent_data if isinstance(parent_data, dict) else {}),
                    "status": child_status,
                    "_rolled_up_from": child_name,
                }
    return rolled


def _load_extractions(output_dir: str) -> dict[str, dict[str, dict]]:
    """Load all extractions_{model}.jsonl files. Returns {model: {hash: record}}."""
    models: dict[str, dict[str, dict]] = {}
    for path in Path(output_dir).glob("extractions_*.jsonl"):
        model_name = path.stem.replace("extractions_", "")
        # Skip backup files
        if "backup" in model_name or "_v1_" in model_name:
            continue
        records: dict[str, dict] = {}
        with open(path) as f:
            for line in f:
                try:
                    data = json.loads(line)
                    records[data["report_hash"]] = data
                except (json.JSONDecodeError, KeyError):
                    continue
        if records:
            models[model_name] = records
    return models


def compare_extractions(output_dir: str) -> dict:
    """Compare N extraction outputs. Write agreement_report.json + disagreements.jsonl."""
    models = _load_extractions(output_dir)
    model_names = sorted(models.keys())

    if len(model_names) < 2:
        # Single model — perfect agreement by definition
        n_reports = len(next(iter(models.values()), {}))
        report = {
            "n_unique_reports": n_reports,
            "n_models": len(model_names),
            "models": model_names,
            "classification_agreement_rate": 1.0,
            "per_finding_agreement_rate": {},
            "mean_finding_agreement": 1.0,
            "n_any_disagreement": 0,
            "disagreement_report_hashes": [],
        }
        with open(Path(output_dir) / "agreement_report.json", "w") as f:
            json.dump(report, f, indent=2)
        Path(output_dir, "disagreements.jsonl").write_text("")
        return report

    # Load hierarchy for roll-up
    try:
        from cxr_mvp.config import load_findings_config
        config = load_findings_config()
        hierarchy = config.hierarchy()
    except (FileNotFoundError, Exception):
        hierarchy = {}

    # Collect all report_hashes present in ALL models
    hash_sets = [set(models[m].keys()) for m in model_names]
    common_hashes = set.intersection(*hash_sets)

    classification_agree = 0
    finding_agree_counts: dict[str, int] = defaultdict(int)
    finding_total_counts: dict[str, int] = defaultdict(int)
    disagreements: list[dict] = []
    n_any_disagreement = 0
    per_report: dict[str, float] = {}

    for rhash in sorted(common_hashes):
        records = {m: models[m][rhash] for m in model_names}

        # Classification agreement
        classifications = {m: r["classification"] for m, r in records.items()}
        class_agree = len(set(classifications.values())) == 1
        if class_agree:
            classification_agree += 1

        # Per-finding agreement
        has_any_disagreement = not class_agree
        disagreement_findings: list[str] = []

        # Apply hierarchy roll-up before comparing
        rolled_records: dict[str, dict] = {}
        for m in model_names:
            rolled_records[m] = _apply_hierarchy_rollup(
                records[m].get("findings", {}), hierarchy
            )

        # Get all finding names across models
        all_findings: set[str] = set()
        for r in records.values():
            all_findings.update(r.get("findings", {}).keys())

        # finding_votes stores RAW statuses (for human-readable output)
        finding_votes: dict[str, dict[str, str]] = {}
        for finding in sorted(all_findings):
            # Raw statuses for output
            raw_statuses = {}
            for m in model_names:
                f_data = records[m].get("findings", {}).get(finding, {})
                raw_statuses[m] = get_finding_status(f_data)
            finding_votes[finding] = raw_statuses

            # Rolled-up statuses for agreement comparison
            rolled_statuses = {}
            for m in model_names:
                f_data = rolled_records[m].get(finding, {})
                rolled_statuses[m] = get_finding_status(f_data)

            finding_total_counts[finding] += 1

            if len(set(rolled_statuses.values())) == 1:
                finding_agree_counts[finding] += 1
            else:
                has_any_disagreement = True
                disagreement_findings.append(finding)

        if has_any_disagreement:
            n_any_disagreement += 1
            disagreements.append({
                "report_hash": rhash,
                "classification_votes": classifications,
                "finding_votes": finding_votes,
                "disagreement_findings": disagreement_findings,
            })

        # Per-report agreement score (for Stage 2 join) — uses rolled-up statuses
        n_comparisons = 1  # classification comparison
        n_agree = 1 if class_agree else 0
        for finding in sorted(all_findings):
            n_comparisons += 1
            rolled_s = {}
            for m in model_names:
                f_data = rolled_records[m].get(finding, {})
                rolled_s[m] = get_finding_status(f_data)
            if len(set(rolled_s.values())) == 1:
                n_agree += 1
        per_report[rhash] = round(n_agree / n_comparisons, 4) if n_comparisons > 0 else 1.0

    n_reports = len(common_hashes)
    per_finding_rate = {
        f: round(finding_agree_counts[f] / finding_total_counts[f], 4)
        if finding_total_counts[f] > 0 else 1.0
        for f in sorted(finding_total_counts.keys())
    }
    mean_finding = (
        sum(per_finding_rate.values()) / len(per_finding_rate)
        if per_finding_rate else 1.0
    )

    report = {
        "n_unique_reports": n_reports,
        "n_models": len(model_names),
        "models": model_names,
        "classification_agreement_rate": round(
            classification_agree / n_reports, 4
        ) if n_reports > 0 else 1.0,
        "per_finding_agreement_rate": per_finding_rate,
        "mean_finding_agreement": round(mean_finding, 4),
        "n_any_disagreement": n_any_disagreement,
        "disagreement_report_hashes": [d["report_hash"] for d in disagreements],
    }

    # Write outputs
    with open(Path(output_dir) / "agreement_report.json", "w") as f:
        json.dump(report, f, indent=2)

    with open(Path(output_dir) / "disagreements.jsonl", "w") as f:
        for d in disagreements:
            f.write(json.dumps(d) + "\n")

    # Write per-report scores for Stage 2 join
    with open(Path(output_dir) / "per_report_agreement.json", "w") as f:
        json.dump(per_report, f, indent=2)

    return report


def select_primary(output_dir: str, primary_model: str | None = None) -> None:
    """Copy primary model's extractions to selected_extractions.jsonl.

    If primary_model is None, reads agreement_report.json for model order
    (first model listed = primary, matching config order from registry).
    Falls back to alphabetical if no agreement report.
    """
    if primary_model is None:
        # Try to get from agreement report (preserves config ordering)
        report_path = Path(output_dir) / "agreement_report.json"
        if report_path.exists():
            with open(report_path) as f:
                report = json.load(f)
            models = report.get("models", [])
            if models:
                primary_model = models[0]
        if primary_model is None:
            files = sorted(Path(output_dir).glob("extractions_*.jsonl"))
            if not files:
                raise FileNotFoundError(f"No extraction files in {output_dir}")
            primary_model = files[0].stem.replace("extractions_", "")

    source = Path(output_dir) / f"extractions_{primary_model}.jsonl"
    if not source.exists():
        raise FileNotFoundError(f"Primary model file not found: {source}")

    dest = Path(output_dir) / "selected_extractions.jsonl"
    shutil.copy2(source, dest)
