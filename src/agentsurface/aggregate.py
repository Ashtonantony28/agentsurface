"""Aggregate dimension scores into an overall AgentSurface Report."""
from __future__ import annotations

from agentsurface.framework import compute_grade, compute_overall_score
from agentsurface.models import DimensionScore, Provenance, Report


def aggregate(
    slug: str,
    name: str,
    category: str,
    dimension_scores: list[DimensionScore],
    provenance: Provenance,
) -> Report:
    """
    Combine dimension scores into a Report.

    - Computes weighted overall score using each DimensionScore's .weight and .score
    - Computes overall grade from the overall score
    - Returns a Report with all fields populated
    - Handles empty dimension_scores gracefully (returns score=0.0, grade=F)
    """
    overall_score = compute_overall_score(
        [(ds.score, ds.weight) for ds in dimension_scores]
    )
    grade = compute_grade(overall_score)

    return Report(
        slug=slug,
        name=name,
        category=category,
        overall_score=overall_score,
        grade=grade,
        dimensions=dimension_scores,
        provenance=provenance,
    )
