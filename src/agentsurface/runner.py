"""Scan runner: loads targets, runs all 6 scanners concurrently, returns a Report."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml

from agentsurface.aggregate import aggregate
from agentsurface.framework import compute_grade
from agentsurface.http import FetchRecord
from agentsurface.models import DimensionScore, Provenance, Report, SignalStatus
from agentsurface.scanners import get_all_scanner_classes
from agentsurface.scanners.base import Target, make_signal

_PROJECT_ROOT = Path(__file__).parent.parent.parent

logger = logging.getLogger(__name__)


def load_cached_report(slug: str, max_age_seconds: int = 86400) -> "Report | None":
    """Return a cached Report if data/reports/<slug>.json exists and is fresh enough."""
    path = _PROJECT_ROOT / "data" / "reports" / f"{slug}.json"
    if not path.exists():
        return None
    age = datetime.utcnow().timestamp() - os.path.getmtime(path)
    if age > max_age_seconds:
        return None
    text = path.read_text(encoding="utf-8")
    return Report.model_validate_json(text)


def load_targets(seed_path: str = "data/seed_apis.yaml") -> list[Target]:
    """Load all targets from seed_apis.yaml."""
    path = Path(seed_path)
    with path.open("r", encoding="utf-8") as fh:
        entries = yaml.safe_load(fh)
    return [Target.from_dict(entry) for entry in entries]


async def scan_target(
    target: Target,
    *,
    test_mode: bool = False,
) -> Report:
    """
    Run all 6 scanners on target concurrently.
    Returns a Report with all dimension scores and provenance.
    """
    scanner_classes = get_all_scanner_classes()
    scanners = [cls() for cls in scanner_classes]
    fetch_records: list[FetchRecord] = []

    async def _run_scanner(scanner) -> DimensionScore:
        try:
            return await scanner.scan(target, fetch_records=fetch_records, test_mode=test_mode)
        except Exception as exc:  # noqa: BLE001
            print(
                f"[agentsurface] scanner {scanner.dimension_id!r} raised unexpected "
                f"exception for target {target.slug!r}: {exc!r}",
                file=sys.stderr,
            )
            # Build a zero-score DimensionScore with FAIL signals
            fallback_signals = [
                make_signal(
                    id=f"{scanner.dimension_id}.error",
                    label="Scanner error",
                    weight=1.0,
                    status=SignalStatus.FAIL,
                    notes=str(exc),
                )
            ]
            return DimensionScore(
                dimension_id=scanner.dimension_id,
                dimension_name=scanner.dimension_name,
                weight=scanner.weight,
                score=0.0,
                grade=compute_grade(0.0),
                signals=fallback_signals,
            )

    dimension_scores: list[DimensionScore] = list(
        await asyncio.gather(*[_run_scanner(s) for s in scanners])
    )

    scanned_at = (
        "2026-01-01T00:00:00Z"
        if test_mode
        else datetime.utcnow().isoformat() + "Z"
    )

    provenance = Provenance(
        scanned_at=scanned_at,
        urls_fetched=[rec.url for rec in fetch_records],
        test_mode=test_mode,
    )

    return aggregate(
        slug=target.slug,
        name=target.name,
        category=target.category,
        dimension_scores=dimension_scores,
        provenance=provenance,
    )


async def scan_by_slug(
    slug: str,
    seed_path: str = "data/seed_apis.yaml",
    *,
    test_mode: bool = False,
    force: bool = False,
) -> Report:
    """
    Load Target from seed_apis.yaml by slug, then call scan_target().
    Raises ValueError if slug not found.
    If force=False, returns a cached report if one exists and is less than 24h old.
    """
    if not force:
        cached = load_cached_report(slug)
        if cached is not None:
            logger.info("Using cached report for %s", slug)
            return cached
    targets = load_targets(seed_path)
    for target in targets:
        if target.slug == slug:
            return await scan_target(target, test_mode=test_mode)
    raise ValueError(f"Slug {slug!r} not found in {seed_path!r}")
