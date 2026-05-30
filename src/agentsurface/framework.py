"""Pure scoring functions for AgentSurface.

No I/O, no network calls. All functions are deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentsurface.models import Grade, Signal, SignalStatus


@dataclass(frozen=True)
class DimensionDef:
    id: str
    name: str
    weight: float


DIMENSIONS: list[DimensionDef] = [
    DimensionDef(id="openapi_quality",    name="OpenAPI Quality",    weight=0.20),
    DimensionDef(id="docs_accessibility", name="Docs Accessibility", weight=0.20),
    DimensionDef(id="sdk_ergonomics",     name="SDK Ergonomics",     weight=0.15),
    DimensionDef(id="error_ux",           name="Error UX",           weight=0.15),
    DimensionDef(id="auth_ergonomics",    name="Auth Ergonomics",    weight=0.15),
    DimensionDef(id="discovery_surface",  name="Discovery Surface",  weight=0.15),
]


def compute_grade(score: float) -> Grade:
    """Map a 0–100 score to a Grade with +/- modifier."""
    if score < 0 or score > 100:
        raise ValueError(f"score must be in 0–100; got {score}")

    # Define bands: (letter, low_inclusive, high_inclusive)
    bands = [
        ("A", 90.0, 100.0),
        ("B", 75.0,  89.0),
        ("C", 60.0,  74.0),
        ("D", 40.0,  59.0),
    ]

    for letter, low, high in bands:
        if low <= score <= high:
            width = high - low
            lower_third = low + width / 3
            upper_third = low + 2 * width / 3
            if score >= upper_third:
                modifier = "+"
            elif score >= lower_third:
                modifier = ""
            else:
                modifier = "-"
            return Grade(f"{letter}{modifier}")

    # 0–39 → F
    return Grade.F


def signal_score_to_float(status: SignalStatus) -> float:
    """PASS → 1.0, PARTIAL → 0.5, FAIL/SKIP → 0.0"""
    if status == SignalStatus.PASS:
        return 1.0
    if status == SignalStatus.PARTIAL:
        return 0.5
    return 0.0


def compute_dimension_score(signals: list[Signal]) -> float:
    """
    Weighted average of signal scores * 100.
    Signals with status SKIP are excluded from the weighted average
    (their weight is redistributed to remaining signals).
    Returns 0.0 if all signals are SKIP.
    """
    active = [s for s in signals if s.status != SignalStatus.SKIP]
    if not active:
        return 0.0

    total_weight = sum(s.weight for s in active)
    if total_weight == 0.0:
        return 0.0

    weighted_sum = sum(signal_score_to_float(s.status) * s.weight for s in active)
    return (weighted_sum / total_weight) * 100.0


def compute_overall_score(dimension_scores: list[tuple[float, float]]) -> float:
    """
    Takes list of (score, weight) tuples.
    Returns weighted average, rounded to 1 decimal place.
    """
    total_weight = sum(w for _, w in dimension_scores)
    if total_weight == 0.0:
        return 0.0

    weighted_sum = sum(score * weight for score, weight in dimension_scores)
    return round(weighted_sum / total_weight, 1)
