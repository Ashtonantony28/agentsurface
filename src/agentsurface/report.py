"""Write Report objects to disk as JSON and Markdown."""

from __future__ import annotations

from pathlib import Path

from agentsurface import __version__
from agentsurface.models import Report, SignalStatus

_STATUS_ICON = {
    SignalStatus.PASS: "✅ PASS",
    SignalStatus.FAIL: "❌ FAIL",
    SignalStatus.PARTIAL: "⚠️ PARTIAL",
    SignalStatus.SKIP: "⏭ SKIP",
    # str values (when use_enum_values=True serialises them)
    "pass": "✅ PASS",
    "fail": "❌ FAIL",
    "partial": "⚠️ PARTIAL",
    "skip": "⏭ SKIP",
}


def _status_icon(status) -> str:
    return _STATUS_ICON.get(status, str(status))


def _build_markdown(report: Report) -> str:
    lines: list[str] = []

    # Title
    lines.append(f"# {report.name} — Agent Readiness Report")
    lines.append("")

    # Executive summary line
    if report.dimensions:
        top_dim = max(report.dimensions, key=lambda d: d.score)
        bot_dim = min(report.dimensions, key=lambda d: d.score)
        lines.append(
            f"**Grade {report.grade} (score {report.overall_score:.1f})**"
            f" — Top strength: {top_dim.dimension_name} ({top_dim.score:.1f})."
            f" Top weakness: {bot_dim.dimension_name} ({bot_dim.score:.1f})."
        )
        lines.append("")

    # Summary
    lines.append(
        f"**Overall Score:** {report.overall_score:.1f} / 100"
        f" — Grade: **{report.grade}**"
    )
    lines.append(
        f"**Scanned:** {report.provenance.scanned_at}"
        f" | Scanner version: {report.provenance.scanner_version}"
    )
    lines.append("")

    # Dimension Scores table
    lines.append("## Dimension Scores")
    lines.append("")
    lines.append("| Dimension | Score | Grade | Weight |")
    lines.append("|-----------|-------|-------|--------|")
    for dim in report.dimensions:
        weight_pct = f"{int(round(dim.weight * 100))}%"
        lines.append(
            f"| {dim.dimension_name} | {dim.score:.1f} | {dim.grade} | {weight_pct} |"
        )
    lines.append("")

    # Signal Breakdown
    lines.append("## Signal Breakdown")
    lines.append("")
    for dim in report.dimensions:
        lines.append(f"### {dim.dimension_name} ({dim.score:.1f} — {dim.grade})")
        lines.append("")
        lines.append("| Signal | Status | Notes |")
        lines.append("|--------|--------|-------|")
        for sig in dim.signals:
            notes = sig.notes if sig.notes else "—"
            if sig.evidence_url:
                evidence = f" [[link]({sig.evidence_url})]"
            else:
                evidence = ""
            lines.append(
                f"| {sig.label} | {_status_icon(sig.status)} | {notes}{evidence} |"
            )
        lines.append("")

    # How to Improve
    lines.append("## How to Improve")
    lines.append("")
    improvement_items: list[str] = []
    for dim in report.dimensions:
        for sig in dim.signals:
            status = sig.status
            # Handle both enum instances and string values
            status_val = status.value if hasattr(status, "value") else status
            if status_val in ("fail", "partial"):
                notes = sig.notes if sig.notes else "Review and fix this signal."
                improvement_items.append(
                    f"- **[{dim.dimension_name}] {sig.label}**: {notes}"
                )

    if improvement_items:
        lines.append(
            "The following signals failed or were only partially satisfied:"
        )
        lines.append("")
        lines.extend(improvement_items)
    else:
        lines.append(
            "All signals passed or were skipped — no improvements identified."
        )
    lines.append("")

    # Provenance
    lines.append("## Provenance")
    lines.append("")
    lines.append(f"- Scanned at: {report.provenance.scanned_at}")
    lines.append(f"- Scanner version: {report.provenance.scanner_version}")
    lines.append("- URLs fetched:")
    for url in report.provenance.urls_fetched:
        lines.append(f"  - {url}")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append(
        f"*Scanned: {report.provenance.scanned_at} · AgentSurface v{__version__}*"
    )
    lines.append("")

    return "\n".join(lines)


def write_report(report: Report, output_dir: str = "data/reports") -> tuple[str, str]:
    """
    Write report to <output_dir>/<slug>.json and <output_dir>/<slug>.md.
    Creates output_dir if it doesn't exist.
    Returns (json_path, md_path).
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    json_path = out / f"{report.slug}.json"
    md_path = out / f"{report.slug}.md"

    json_path.write_text(report.to_json(), encoding="utf-8")
    md_path.write_text(_build_markdown(report), encoding="utf-8")

    return str(json_path), str(md_path)
