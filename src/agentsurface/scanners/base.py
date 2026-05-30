"""Base classes and helpers for AgentSurface scanners."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, fields

from agentsurface.models import DimensionScore, Signal, SignalStatus

# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------


@dataclass
class Target:
    """Represents one API entry from seed_apis.yaml."""

    slug: str
    name: str
    category: str
    homepage: str
    docs_url: str
    openapi_url: str | None = None
    github_org: str | None = None
    npm_package: str | None = None
    pypi_package: str | None = None
    mcp_server_url: str | None = None
    api_base_url: str | None = None  # Explicit API base URL (e.g. https://api.stripe.com)
    error_probes: list[str] = field(default_factory=list)  # URLs to probe for error responses

    @classmethod
    def from_dict(cls, d: dict) -> "Target":
        """Create Target from a dict (e.g., loaded from seed_apis.yaml)."""
        # Only pass known fields; ignore extra keys; replace None for missing optional fields
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------------------
# make_signal helper
# ---------------------------------------------------------------------------


def make_signal(
    id: str,
    label: str,
    weight: float,
    status: SignalStatus,
    evidence_url: str | None = None,
    notes: str | None = None,
) -> Signal:
    """Factory for Signal objects; computes score from status automatically."""
    score_map = {
        SignalStatus.PASS: 1.0,
        SignalStatus.PARTIAL: 0.5,
        SignalStatus.FAIL: 0.0,
        SignalStatus.SKIP: 0.0,
    }
    return Signal(
        id=id,
        label=label,
        weight=weight,
        status=status,
        score=score_map[status],
        evidence_url=evidence_url,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Scanner ABC
# ---------------------------------------------------------------------------


class Scanner(ABC):
    """Abstract base class for all dimension scanners."""

    dimension_id: str        # class-level constant, e.g. "openapi_quality"
    dimension_name: str      # class-level constant
    weight: float            # class-level constant (e.g. 0.20)

    @abstractmethod
    async def scan(
        self,
        target: Target,
        *,
        fetch_records: list,   # list[FetchRecord] — append records here
        test_mode: bool = False,
    ) -> DimensionScore:
        """Run all signals for this dimension and return a DimensionScore."""

    def _make_dimension_score(
        self,
        signals: list[Signal],
        score: float,
    ) -> DimensionScore:
        """Helper to construct a DimensionScore from signals and precomputed score."""
        from agentsurface.framework import compute_grade
        return DimensionScore(
            dimension_id=self.dimension_id,
            dimension_name=self.dimension_name,
            weight=self.weight,
            score=round(score, 1),
            grade=compute_grade(score),
            signals=signals,
        )
