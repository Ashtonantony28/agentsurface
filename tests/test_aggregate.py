"""Tests for aggregate() and framework scoring functions.

Pure function tests — no network, no HTTP fixtures needed.
"""

import pytest

from agentsurface.aggregate import aggregate
from agentsurface.framework import (
    DIMENSIONS,
    compute_dimension_score,
    compute_grade,
    compute_overall_score,
)
from agentsurface.models import (
    DimensionScore,
    Grade,
    Provenance,
    Signal,
    SignalStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pass_signal(id: str = "s.pass", weight: float = 0.5) -> Signal:
    return Signal(id=id, label="Pass", weight=weight, status=SignalStatus.PASS, score=1.0)


def _fail_signal(id: str = "s.fail", weight: float = 0.5) -> Signal:
    return Signal(id=id, label="Fail", weight=weight, status=SignalStatus.FAIL, score=0.0)


def _partial_signal(id: str = "s.partial", weight: float = 0.5) -> Signal:
    return Signal(id=id, label="Partial", weight=weight, status=SignalStatus.PARTIAL, score=0.5)


def _skip_signal(id: str = "s.skip", weight: float = 0.5) -> Signal:
    return Signal(id=id, label="Skip", weight=weight, status=SignalStatus.SKIP, score=0.0)


def _make_dimension_score(dim_id: str, score: float, weight: float) -> DimensionScore:
    grade = compute_grade(score)
    return DimensionScore(
        dimension_id=dim_id,
        dimension_name=dim_id,
        weight=weight,
        score=score,
        grade=grade,
        signals=[_pass_signal()],
    )


def _make_provenance() -> Provenance:
    return Provenance(
        scanned_at="2026-05-30T00:00:00Z",
        urls_fetched=[],
        test_mode=True,
    )


# ---------------------------------------------------------------------------
# compute_grade boundaries
# ---------------------------------------------------------------------------


def test_compute_grade_boundaries():
    # A band: 90–100
    assert compute_grade(100) == Grade.A_PLUS
    assert compute_grade(90) == Grade.A_MINUS   # bottom of A band → A-
    # B band: 75–89
    assert compute_grade(89) == Grade.B_PLUS    # top of B band → B+
    # C band: 60–74 — score=75 is B not C; score=74 is C+
    # B lower_third = 75 + 14/3 ≈ 79.667; 75 < 79.667 → B-
    assert compute_grade(75) == Grade.B_MINUS
    # C upper_third = 60 + 28/3 ≈ 69.333; 74 >= 69.333 → C+
    assert compute_grade(74) == Grade.C_PLUS
    # C lower_third = 60 + 14/3 ≈ 64.667; 60 < 64.667 → C-
    assert compute_grade(60) == Grade.C_MINUS
    # D band: 40–59
    # D upper_third = 40 + 38/3 ≈ 52.667; 59 >= 52.667 → D+
    assert compute_grade(59) == Grade.D_PLUS
    # D lower_third = 40 + 19/3 ≈ 46.333; 40 < 46.333 → D-
    assert compute_grade(40) == Grade.D_MINUS
    # Below 40 → F
    assert compute_grade(39) == Grade.F
    assert compute_grade(0) == Grade.F


def test_compute_grade_invalid():
    with pytest.raises(ValueError):
        compute_grade(-1)
    with pytest.raises(ValueError):
        compute_grade(101)


def test_compute_grade_plus_minus():
    # B band: 75–89, width=14
    # lower_third = 75 + 14/3 ≈ 79.667
    # upper_third = 75 + 28/3 ≈ 84.333
    # middle: [79.667, 84.333)
    assert compute_grade(82) == Grade.B        # middle of B band
    assert compute_grade(88.5) == Grade.B_PLUS  # top third (>= 84.333)
    assert compute_grade(76) == Grade.B_MINUS   # bottom third (< 79.667)


# ---------------------------------------------------------------------------
# compute_dimension_score
# ---------------------------------------------------------------------------


def test_compute_dimension_score_all_pass():
    signals = [_pass_signal("s1", 0.3), _pass_signal("s2", 0.7)]
    assert compute_dimension_score(signals) == 100.0


def test_compute_dimension_score_all_fail():
    signals = [_fail_signal("s1", 0.3), _fail_signal("s2", 0.7)]
    assert compute_dimension_score(signals) == 0.0


def test_compute_dimension_score_skip_excluded():
    # One PASS with weight 0.5 and one SKIP with weight 0.5.
    # Only the PASS is active; score should be 100.0, not dragged down by SKIP.
    signals = [_pass_signal("s1", 0.5), _skip_signal("s2", 0.5)]
    assert compute_dimension_score(signals) == 100.0


def test_compute_dimension_score_partial():
    # All PARTIAL signals → 50.0 (PARTIAL = 0.5 score)
    signals = [_partial_signal("s1", 0.4), _partial_signal("s2", 0.6)]
    assert compute_dimension_score(signals) == 50.0


# ---------------------------------------------------------------------------
# compute_overall_score
# ---------------------------------------------------------------------------


def test_compute_overall_score_weighted():
    # Two dimensions: score=80 weight=0.6, score=50 weight=0.4
    # Expected: (80*0.6 + 50*0.4) / (0.6+0.4) = (48 + 20) / 1.0 = 68.0
    result = compute_overall_score([(80.0, 0.6), (50.0, 0.4)])
    assert result == 68.0


# ---------------------------------------------------------------------------
# aggregate()
# ---------------------------------------------------------------------------


def test_aggregate_returns_report():
    dims = [
        _make_dimension_score(DIMENSIONS[0].id, 85.0, DIMENSIONS[0].weight),
        _make_dimension_score(DIMENSIONS[1].id, 70.0, DIMENSIONS[1].weight),
        _make_dimension_score(DIMENSIONS[2].id, 90.0, DIMENSIONS[2].weight),
        _make_dimension_score(DIMENSIONS[3].id, 60.0, DIMENSIONS[3].weight),
        _make_dimension_score(DIMENSIONS[4].id, 75.0, DIMENSIONS[4].weight),
        _make_dimension_score(DIMENSIONS[5].id, 50.0, DIMENSIONS[5].weight),
    ]
    provenance = _make_provenance()
    report = aggregate(
        slug="testapi",
        name="Test API",
        category="devtools_observability",
        dimension_scores=dims,
        provenance=provenance,
    )

    assert report.slug == "testapi"
    assert report.name == "Test API"
    assert report.category == "devtools_observability"
    assert 0.0 <= report.overall_score <= 100.0
    assert report.grade in {g.value for g in Grade}
    assert len(report.dimensions) == 6
    assert report.provenance is provenance


def test_aggregate_empty_dimensions():
    provenance = _make_provenance()
    report = aggregate(
        slug="emptyapi",
        name="Empty API",
        category="payments",
        dimension_scores=[],
        provenance=provenance,
    )
    assert report.overall_score == 0.0
    assert report.grade == Grade.F
