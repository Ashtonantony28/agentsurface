"""Tests for agentsurface pydantic models.

Pure function tests — no network, no HTTP fixtures needed.
"""

import json

import pytest
from pydantic import ValidationError

from agentsurface.models import (
    DimensionScore,
    Grade,
    Provenance,
    Report,
    Signal,
    SignalStatus,
)


def _make_signal(
    id="test.signal",
    label="Test Signal",
    weight=0.5,
    status=SignalStatus.PASS,
    score=1.0,
):
    return Signal(id=id, label=label, weight=weight, status=status, score=score)


def _make_dimension_score(score=80.0):
    return DimensionScore(
        dimension_id="openapi_quality",
        dimension_name="OpenAPI Quality",
        weight=0.20,
        score=score,
        grade=Grade.B,
        signals=[_make_signal()],
    )


def _make_provenance():
    return Provenance(
        scanned_at="2026-05-30T00:00:00Z",
        urls_fetched=["https://example.com"],
    )


def _make_report(overall_score=80.0):
    return Report(
        slug="testapi",
        name="Test API",
        category="devtools_observability",
        overall_score=overall_score,
        grade=Grade.B,
        dimensions=[_make_dimension_score(overall_score)],
        provenance=_make_provenance(),
    )


# ---------------------------------------------------------------------------
# SignalStatus
# ---------------------------------------------------------------------------


def test_signal_status_values():
    assert SignalStatus.PASS == "pass"
    assert SignalStatus.FAIL == "fail"
    assert SignalStatus.PARTIAL == "partial"
    assert SignalStatus.SKIP == "skip"


# ---------------------------------------------------------------------------
# Grade
# ---------------------------------------------------------------------------


def test_grade_values():
    expected = {"A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"}
    actual = {g.value for g in Grade}
    assert actual == expected


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------


def test_signal_valid():
    s = _make_signal()
    assert s.id == "test.signal"
    assert s.label == "Test Signal"
    assert s.weight == 0.5
    assert s.score == 1.0


def test_signal_invalid_score():
    with pytest.raises(ValidationError):
        Signal(id="x", label="x", weight=0.5, status=SignalStatus.PASS, score=0.3)


def test_signal_invalid_weight():
    with pytest.raises(ValidationError):
        Signal(id="x", label="x", weight=0.0, status=SignalStatus.PASS, score=1.0)


# ---------------------------------------------------------------------------
# DimensionScore
# ---------------------------------------------------------------------------


def test_dimension_score_valid():
    ds = _make_dimension_score(75.0)
    assert ds.dimension_id == "openapi_quality"
    assert ds.score == 75.0
    assert ds.weight == 0.20


def test_dimension_score_score_out_of_range():
    with pytest.raises(ValidationError):
        DimensionScore(
            dimension_id="openapi_quality",
            dimension_name="OpenAPI Quality",
            weight=0.20,
            score=150,
            grade=Grade.A,
            signals=[],
        )


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_provenance_defaults():
    p = Provenance(scanned_at="2026-05-30T00:00:00Z", urls_fetched=[])
    assert p.test_mode is False
    assert p.scanner_version == "0.1.0"


# ---------------------------------------------------------------------------
# Report serialization
# ---------------------------------------------------------------------------


def test_report_to_json_deterministic():
    r1 = _make_report(80.0)
    r2 = _make_report(80.0)
    assert r1.to_json() == r2.to_json()


def test_report_to_json_sorted_keys():
    r = _make_report(80.0)
    parsed = json.loads(r.to_json())
    keys = list(parsed.keys())
    assert keys == sorted(keys), f"Top-level keys not sorted: {keys}"


def test_report_overall_score_rounds():
    r = Report(
        slug="testapi",
        name="Test API",
        category="devtools_observability",
        overall_score=80.123456,
        grade=Grade.B,
        dimensions=[_make_dimension_score(80.1)],
        provenance=_make_provenance(),
    )
    assert r.overall_score == round(80.123456, 1)
