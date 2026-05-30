"""Tests for build_site(): HTML output assertions."""
from __future__ import annotations

from pathlib import Path

from agentsurface.models import (
    DimensionScore,
    Grade,
    Provenance,
    Report,
    Signal,
    SignalStatus,
)
from agentsurface.report import write_report
from agentsurface.site import build_site

# Absolute paths from the project root (needed because cwd may vary under pytest)
_PROJECT_ROOT = Path(__file__).parent.parent
_TEMPLATES_DIR = _PROJECT_ROOT / "templates"
_DOCS_DIR = _PROJECT_ROOT / "docs"


def _make_signal(id: str, label: str, status: SignalStatus) -> Signal:
    score_map = {
        SignalStatus.PASS: 1.0,
        SignalStatus.PARTIAL: 0.5,
        SignalStatus.FAIL: 0.0,
        SignalStatus.SKIP: 0.0,
    }
    return Signal(
        id=id,
        label=label,
        weight=1.0,
        status=status,
        score=score_map[status],
    )


def _make_dim(
    dimension_id: str, dimension_name: str, weight: float, score: float
) -> DimensionScore:
    return DimensionScore(
        dimension_id=dimension_id,
        dimension_name=dimension_name,
        weight=weight,
        score=score,
        grade=Grade.B,
        signals=[
            _make_signal(f"{dimension_id}.sig1", "Signal one", SignalStatus.PASS),
        ],
    )


def _make_report() -> Report:
    """Create a minimal Report with 6 DimensionScore entries."""
    dimensions = [
        _make_dim("openapi_quality", "OpenAPI Quality", 0.20, 80.0),
        _make_dim("docs_accessibility", "Docs Accessibility", 0.20, 75.0),
        _make_dim("sdk_ergonomics", "SDK Ergonomics", 0.15, 70.0),
        _make_dim("error_ux", "Error UX", 0.15, 65.0),
        _make_dim("auth_ergonomics", "Auth Ergonomics", 0.15, 60.0),
        _make_dim("discovery_surface", "Discovery Surface", 0.15, 55.0),
    ]
    provenance = Provenance(
        scanned_at="2026-01-01T00:00:00Z",
        urls_fetched=["https://testco.example.com/openapi.json"],
        test_mode=True,
    )
    return Report(
        slug="testco",
        name="TestCo API",
        category="devtools",
        overall_score=69.3,
        grade=Grade.C_PLUS,
        dimensions=dimensions,
        provenance=provenance,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_build_site_creates_expected_files(tmp_path):
    """build_site() creates index.html, per-api page, badge, framework, submit."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    output_dir = tmp_path / "site"

    report = _make_report()
    write_report(report, str(reports_dir))

    build_site(
        reports_dir=str(reports_dir),
        templates_dir=str(_TEMPLATES_DIR),
        output_dir=str(output_dir),
        docs_dir=str(_DOCS_DIR),
    )

    # index.html
    index_html = output_dir / "index.html"
    assert index_html.exists(), "index.html not found"
    index_content = index_html.read_text(encoding="utf-8")
    # Should contain the slug or name
    assert "testco" in index_content.lower() or "TestCo" in index_content

    # per-API page
    api_page = output_dir / "api" / "testco.html"
    assert api_page.exists(), "api/testco.html not found"
    api_content = api_page.read_text(encoding="utf-8")
    assert "testco" in api_content.lower() or "TestCo" in api_content

    # badge SVG
    badge_file = output_dir / "badge" / "testco.svg"
    assert badge_file.exists(), "badge/testco.svg not found"
    badge_content = badge_file.read_text(encoding="utf-8")
    assert "<svg" in badge_content

    # framework page
    framework_html = output_dir / "framework.html"
    assert framework_html.exists(), "framework.html not found"

    # submit page
    submit_html = output_dir / "submit.html"
    assert submit_html.exists(), "submit.html not found"


def test_build_site_empty_reports_dir(tmp_path):
    """build_site() with no reports still creates index.html, framework.html, submit.html."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    output_dir = tmp_path / "site"

    build_site(
        reports_dir=str(reports_dir),
        templates_dir=str(_TEMPLATES_DIR),
        output_dir=str(output_dir),
        docs_dir=str(_DOCS_DIR),
    )

    assert (output_dir / "index.html").exists(), "index.html should exist even when no reports"
    assert (output_dir / "framework.html").exists(), "framework.html should exist when no reports"
    assert (output_dir / "submit.html").exists(), "submit.html should exist when no reports"
