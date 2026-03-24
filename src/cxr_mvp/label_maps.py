"""Named label interpretation maps for downstream consumers.

Encodes explicit strategies for how to map 5-state labels (Positive,
Negative, Uncertain, Absent, Not_Assessable) to binary or task-specific
labels. Prevents ad-hoc interpretation in notebooks.

Usage:
    from cxr_mvp.label_maps import apply_label_map
    binary = apply_label_map(extraction["findings"], "broad")
"""
from __future__ import annotations

from cxr_mvp.models import get_finding_status


def _strict_map(findings: dict) -> dict[str, bool | None]:
    """Positive only. Uncertain/Absent/Negative -> False. Not_Assessable -> None."""
    result = {}
    for name, data in findings.items():
        status = get_finding_status(data)
        if status == "Not_Assessable":
            result[name] = None
        else:
            result[name] = status == "Positive"
    return result


def _broad_map(findings: dict) -> dict[str, bool | None]:
    """Positive or Uncertain -> True. Absent/Negative -> False. Not_Assessable -> None."""
    result = {}
    for name, data in findings.items():
        status = get_finding_status(data)
        if status == "Not_Assessable":
            result[name] = None
        else:
            result[name] = status in ("Positive", "Uncertain")
    return result


_PARENCHYMAL_FINDINGS = ("lung_opacity", "consolidation", "infiltration")


def _parenchymal_opacity_map(findings: dict) -> dict[str, bool | None]:
    """Composite: any parenchymal opacity finding Positive -> True."""
    any_positive = any(
        get_finding_status(findings.get(f, {})) in ("Positive", "Uncertain")
        for f in _PARENCHYMAL_FINDINGS
    )
    return {"parenchymal_opacity_present": any_positive}


LABEL_MAPS: dict[str, callable] = {
    "strict": _strict_map,
    "broad": _broad_map,
    "parenchymal_opacity": _parenchymal_opacity_map,
}


def apply_label_map(findings: dict, map_name: str) -> dict[str, bool | None]:
    """Apply a named label map to extraction findings.

    Args:
        findings: {finding_name: {status, confidence, evidence}} dict
        map_name: one of LABEL_MAPS keys

    Returns:
        {finding_name: True/False/None} for per-finding maps,
        or {composite_name: True/False} for composite maps.

    Raises:
        KeyError: if map_name not in LABEL_MAPS
    """
    if map_name not in LABEL_MAPS:
        raise KeyError(f"Unknown label map: {map_name}. Available: {list(LABEL_MAPS.keys())}")
    return LABEL_MAPS[map_name](findings)
