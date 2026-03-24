"""Portuguese medical text rule checks for post-extraction verification.

Deterministic phrase matching for negation, hedging, and chronicity.
Catches high-impact LLM extraction errors without replacing the LLM."""
from __future__ import annotations

import re

from cxr_mvp.models import get_finding_status

# Negation patterns — if evidence contains these, status should NOT be Positive
NEGATION_PATTERNS = [
    r"sem sinais de",
    r"sem evidência de",
    r"ausência de",
    r"não se observa",
    r"não há",
    r"não se identifica",
    r"dentro dos limites",
    r"dentro da normalidade",
    r"sem alterações",
    r"aspecto normal",
    r"preservado[s]?",
    r"contornos preservados",
    r"de aspecto normal",
]

# Hedging patterns — if evidence contains these, status should be Uncertain not Positive
HEDGING_PATTERNS = [
    r"não se pode excluir",
    r"não se pode afastar",
    r"possível",
    r"provável",
    r"sugestivo de",
    r"a esclarecer",
    r"a critério clínico",
    r"a correlacionar",
    r"não se descarta",
]

# Chronicity patterns — evidence suggests chronic/old finding
CHRONICITY_PATTERNS = [
    r"sequela",
    r"residual",
    r"crônic[oa]",
    r"antig[oa]",
    r"prévi[oa]",
    r"degenerativ[oa]",
    r"consolidad[oa]",
]

_negation_re = re.compile("|".join(NEGATION_PATTERNS), re.IGNORECASE)
_hedging_re = re.compile("|".join(HEDGING_PATTERNS), re.IGNORECASE)
_chronicity_re = re.compile("|".join(CHRONICITY_PATTERNS), re.IGNORECASE)


def check_negation_consistency(
    finding_name: str, status: str, evidence: str | None,
) -> str | None:
    """Return warning if Positive status has negation evidence."""
    if status != "Positive" or not evidence:
        return None
    if _negation_re.search(evidence):
        return f"Negation conflict: '{finding_name}' is Positive but evidence contains negation pattern"
    return None


def check_hedging_consistency(
    finding_name: str, status: str, evidence: str | None,
) -> str | None:
    """Return warning if Positive status has hedging evidence (should be Uncertain)."""
    if status != "Positive" or not evidence:
        return None
    if _hedging_re.search(evidence):
        return f"Hedging conflict: '{finding_name}' is Positive but evidence suggests Uncertain"
    return None


def check_chronicity(evidence: str | None) -> bool:
    """Check if evidence suggests a chronic/old finding."""
    if not evidence:
        return False
    return bool(_chronicity_re.search(evidence))


def check_extraction(findings: dict) -> list[dict]:
    """Run all rule checks on an extraction. Returns list of warnings."""
    warnings = []
    for name, data in findings.items():
        if not isinstance(data, dict):
            continue
        status = get_finding_status(data)
        evidence = data.get("evidence")

        neg = check_negation_consistency(name, status, evidence)
        if neg:
            warnings.append({"finding": name, "rule": "negation", "message": neg})

        hedge = check_hedging_consistency(name, status, evidence)
        if hedge:
            warnings.append({"finding": name, "rule": "hedging", "message": hedge})

    return warnings
