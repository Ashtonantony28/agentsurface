"""Pydantic v2 data models for AgentSurface scoring reports.

These models represent the full data pipeline output: individual signal checks
roll up into dimension scores, which roll up into a final Report with an
overall score and letter grade.
"""

from __future__ import annotations

import json
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator


class SignalStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    SKIP = "skip"  # signal not applicable for this target


class Grade(str, Enum):
    A_PLUS = "A+"
    A = "A"
    A_MINUS = "A-"
    B_PLUS = "B+"
    B = "B"
    B_MINUS = "B-"
    C_PLUS = "C+"
    C = "C"
    C_MINUS = "C-"
    D_PLUS = "D+"
    D = "D"
    D_MINUS = "D-"
    F = "F"


class Signal(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str                        # e.g. "openapi.spec_discoverable"
    label: str                     # human-readable short label
    # weight within its dimension (sum of all weights in dimension = 1.0)
    weight: float
    status: SignalStatus
    score: float                   # 0.0, 0.5, or 1.0 matching status
    evidence_url: str | None = None
    notes: str | None = None

    @field_validator("score")
    @classmethod
    def score_must_be_valid(cls, v: float) -> float:
        if v not in (0.0, 0.5, 1.0):
            raise ValueError(f"Signal.score must be 0.0, 0.5, or 1.0; got {v}")
        return v

    @field_validator("weight")
    @classmethod
    def weight_must_be_positive_fraction(cls, v: float) -> float:
        if not (0.0 < v <= 1.0):
            raise ValueError(f"Signal.weight must be > 0 and <= 1.0; got {v}")
        return v


class DimensionScore(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    dimension_id: str              # e.g. "openapi_quality"
    dimension_name: str
    weight: float                  # this dimension's weight in the overall index
    score: float                   # 0–100, weighted average of signal scores * 100
    grade: Grade
    signals: list[Signal]

    @field_validator("score")
    @classmethod
    def score_must_be_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 100.0):
            raise ValueError(f"DimensionScore.score must be 0–100; got {v}")
        return v

    @field_validator("weight")
    @classmethod
    def weight_must_be_positive_fraction(cls, v: float) -> float:
        if not (0.0 < v <= 1.0):
            raise ValueError(f"DimensionScore.weight must be > 0 and <= 1.0; got {v}")
        return v


class Provenance(BaseModel):
    model_config = ConfigDict()

    scanned_at: str                # ISO-8601 UTC datetime string
    urls_fetched: list[str]
    scanner_version: str = "0.1.0"
    test_mode: bool = False        # True when running under pytest (fixed timestamps)


class Report(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    slug: str
    name: str
    category: str
    overall_score: float           # 0–100, rounded to 1 decimal
    grade: Grade
    dimensions: list[DimensionScore]
    provenance: Provenance

    @field_validator("overall_score")
    @classmethod
    def overall_score_must_be_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 100.0):
            raise ValueError(f"Report.overall_score must be 0–100; got {v}")
        return round(v, 1)

    def to_json(self) -> str:
        """Deterministic JSON: sorted keys, 2-space indent."""
        raw = json.loads(self.model_dump_json())
        # Round all float scores to 1 decimal place for deterministic output
        raw = _round_floats(raw)
        return json.dumps(raw, indent=2, sort_keys=True)


def _round_floats(obj: object) -> object:
    """Recursively round floats to 1 decimal place for deterministic serialization."""
    if isinstance(obj, float):
        return round(obj, 1)
    if isinstance(obj, dict):
        return {k: _round_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(item) for item in obj]
    return obj
