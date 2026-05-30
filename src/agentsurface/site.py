"""Static site generator for AgentSurface leaderboard."""

from __future__ import annotations

import json
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader

from agentsurface.badge import badge_img_snippet, write_badge  # noqa: F401


def _render_template(env: Environment, template_name: str, **kwargs: object) -> str:
    return env.get_template(template_name).render(**kwargs)


def build_site(
    reports_dir: str = "data/reports",
    templates_dir: str = "templates",
    output_dir: str = "site",
    docs_dir: str = "docs",
) -> None:
    """
    Build the complete static site:
    1. Load all *.json reports from reports_dir
    2. Render site/index.html (leaderboard)
    3. Render site/api/<slug>.html per API
    4. Render site/framework.html from docs/framework.md
    5. Render site/submit.html
    6. Generate site/badge/<slug>.svg per API
    """
    reports_path = Path(reports_dir)
    output_path = Path(output_dir)
    docs_path = Path(docs_dir)

    # Create output directories
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "api").mkdir(parents=True, exist_ok=True)
    (output_path / "badge").mkdir(parents=True, exist_ok=True)

    # Load Jinja2 environment
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)

    # Load all reports (skip index.json)
    reports: list[dict] = []
    if reports_path.exists():
        for json_file in sorted(reports_path.glob("*.json")):
            if json_file.name == "index.json":
                continue
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                reports.append(data)
            except (json.JSONDecodeError, OSError):
                continue

    # Sort by overall_score descending
    reports.sort(key=lambda r: r.get("overall_score", 0.0), reverse=True)

    # Build leaderboard api list
    apis = []
    for r in reports:
        provenance = r.get("provenance", {})
        apis.append(
            {
                "slug": r.get("slug", ""),
                "name": r.get("name", ""),
                "category": r.get("category", ""),
                "overall_score": r.get("overall_score", 0.0),
                "grade": r.get("grade", "F"),
                "last_scanned": provenance.get("scanned_at", ""),
            }
        )

    # Render index.html
    index_html = _render_template(env, "index.html.j2", apis=apis)
    (output_path / "index.html").write_text(index_html, encoding="utf-8")

    # Render per-API pages and badges
    for r in reports:
        slug = r.get("slug", "")
        grade = r.get("grade", "F")
        overall_score = r.get("overall_score", 0.0)
        badge_url = f"/badge/{slug}.svg"

        api_html = _render_template(env, "api.html.j2", report=r, badge_url=badge_url)
        (output_path / "api" / f"{slug}.html").write_text(api_html, encoding="utf-8")

        write_badge(slug, grade, overall_score, output_dir)

    # Render framework.html
    framework_md_path = docs_path / "framework.md"
    if framework_md_path.exists():
        framework_md_text = framework_md_path.read_text(encoding="utf-8")
        framework_html_content = markdown.markdown(
            framework_md_text, extensions=["tables", "fenced_code"]
        )
    else:
        framework_html_content = "<p>Framework specification coming soon.</p>"

    framework_html = _render_template(
        env, "framework.html.j2", framework_html=framework_html_content
    )
    (output_path / "framework.html").write_text(framework_html, encoding="utf-8")

    # Render submit.html
    submit_html = _render_template(env, "submit.html.j2")
    (output_path / "submit.html").write_text(submit_html, encoding="utf-8")
