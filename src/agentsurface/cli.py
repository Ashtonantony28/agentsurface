"""AgentSurface CLI — scan, score, and publish developer API agent-readiness reports."""
import asyncio
import json
import sys
from pathlib import Path

import click

from agentsurface import report, runner


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """AgentSurface — grade developer APIs for agent usability."""


@cli.command()
@click.argument("slug")
@click.option("--seed", default="data/seed_apis.yaml", help="Path to seed_apis.yaml")
@click.option("--output-dir", default="data/reports", help="Output directory for reports")
@click.option("--test-mode", is_flag=True, default=False, help="Use fixed timestamps (for testing)")
@click.option(
    "--force", is_flag=True, default=False,
    help="Re-scan even if a fresh cached report exists",
)
def scan(slug, seed, output_dir, test_mode, force):
    """Scan a single API by slug and write its report."""
    try:
        result = asyncio.run(
            runner.scan_by_slug(slug, seed_path=seed, test_mode=test_mode, force=force)
        )
    except ValueError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)
    report.write_report(result, output_dir=output_dir)
    click.echo(f"✓ Scored {slug}: {result.grade} ({result.overall_score})")


async def _scan_all_async(targets, output_dir, test_mode, force=False):
    from agentsurface import report as report_module
    from agentsurface import runner as _runner

    results = []
    for i, target in enumerate(targets, 1):
        click.echo(f"[{i}/{len(targets)}] Scanning {target.slug}...")
        try:
            if not force:
                cached = _runner.load_cached_report(target.slug)
                if cached is not None:
                    click.echo("  → Using cached report")
                    report_module.write_report(cached, output_dir=output_dir)
                    results.append(cached)
                    continue
            result = await _runner.scan_target(target, test_mode=test_mode)
            report_module.write_report(result, output_dir=output_dir)
            results.append(result)
            click.echo(f"  → {result.grade} ({result.overall_score})")
        except Exception as exc:
            click.echo(f"  ✗ Failed: {exc}", err=True)

    # Write index.json
    index = {
        r.slug: {
            "name": r.name,
            "category": r.category,
            "overall_score": r.overall_score,
            "grade": r.grade if isinstance(r.grade, str) else r.grade.value,
            "scanned_at": r.provenance.scanned_at,
        }
        for r in results
    }
    index_path = Path(output_dir) / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True))
    return results


@cli.command("scan-all")
@click.option("--seed", default="data/seed_apis.yaml", help="Path to seed_apis.yaml")
@click.option("--output-dir", default="data/reports", help="Output directory for reports")
@click.option("--test-mode", is_flag=True, default=False)
@click.option("--concurrency", default=3, help="Max concurrent scans")
@click.option(
    "--force", is_flag=True, default=False,
    help="Re-scan even if a fresh cached report exists",
)
def scan_all(seed, output_dir, test_mode, concurrency, force):
    """Scan all APIs in seed_apis.yaml and write data/reports/index.json."""
    targets = runner.load_targets(seed)
    results = asyncio.run(_scan_all_async(targets, output_dir, test_mode, force=force))
    click.echo(f"Scored {len(results)}/{len(targets)} APIs. index.json written to {output_dir}")


@cli.command("build-site")
@click.option("--reports-dir", default="data/reports", help="Directory with .json reports")
@click.option("--output-dir", default="site", help="Output directory for static site")
@click.option("--templates-dir", default="templates", help="Jinja2 templates directory")
@click.option("--docs-dir", default="docs", help="docs/ directory for framework.md")
def build_site(reports_dir, output_dir, templates_dir, docs_dir):
    """Build the static leaderboard site from reports."""
    from agentsurface.site import build_site as _build_site
    _build_site(
        reports_dir=reports_dir,
        templates_dir=templates_dir,
        output_dir=output_dir,
        docs_dir=docs_dir,
    )
    click.echo(f"Site built → {output_dir}/")
