"""SVG badge generation for Agent Readiness grades.

Generates shields.io-style SVG badges embedding API slug, overall grade,
and hex colour mapped from the Grade enum. Output is deterministic.
"""

from __future__ import annotations

import os

# Grade color mapping
_GRADE_COLORS: dict[str, str] = {
    "A+": "#44cc11",
    "A":  "#44cc11",
    "A-": "#44cc11",
    "B+": "#97ca00",
    "B":  "#97ca00",
    "B-": "#97ca00",
    "C+": "#dfb317",
    "C":  "#dfb317",
    "C-": "#dfb317",
    "D+": "#fe7d37",
    "D":  "#fe7d37",
    "D-": "#fe7d37",
    "F":  "#e05d44",
}

_LABEL = "Agent Readiness"
# Fixed pixel widths: label section 120px, value section 60px, total 180px
_LABEL_WIDTH = 120
_VALUE_WIDTH = 60
_TOTAL_WIDTH = _LABEL_WIDTH + _VALUE_WIDTH
_HEIGHT = 20
_FONT = "DejaVu Sans,Verdana,Geneva,sans-serif"
_FONT_SIZE = 11


def _grade_color(grade: str) -> str:
    """Return the hex color string for the given grade letter."""
    return _GRADE_COLORS.get(grade, "#9f9f9f")


def generate_badge(slug: str, grade: str, overall_score: float) -> str:
    """
    Generate an SVG badge string for an API.

    Args:
        slug: API slug (e.g., "stripe")
        grade: Grade letter+modifier (e.g., "A+", "B-", "F")
        overall_score: 0-100 float, shown as "B+ (82.4)"

    Returns:
        SVG string (valid XML)
    """
    color = _grade_color(grade)
    score_fmt = f"{overall_score:.1f}"
    value_text = f"{grade} ({score_fmt})"

    # Determine dynamic value section width based on text length
    # Each character is roughly 7px wide at 11px font; add padding
    value_width = max(_VALUE_WIDTH, len(value_text) * 7 + 10)
    total_width = _LABEL_WIDTH + value_width

    label_mid_x = _LABEL_WIDTH // 2
    value_mid_x = _LABEL_WIDTH + value_width // 2

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{_HEIGHT}">\n'
        f'  <title>Agent Readiness: {grade}</title>\n'
        f'  <linearGradient id="s" x2="0" y2="100%">\n'
        f'    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>\n'
        f'    <stop offset="1" stop-opacity=".1"/>\n'
        f'  </linearGradient>\n'
        f'  <rect rx="3" width="{total_width}" height="{_HEIGHT}" fill="#555"/>\n'
        f'  <rect rx="3" x="{_LABEL_WIDTH}" width="{value_width}"'
        f' height="{_HEIGHT}" fill="{color}"/>\n'
        f'  <rect rx="3" width="{total_width}" height="{_HEIGHT}" fill="url(#s)"/>\n'
        f'  <g fill="#fff" text-anchor="middle"'
        f' font-family="{_FONT}" font-size="{_FONT_SIZE}">\n'
        f'    <text x="{label_mid_x}" y="15" fill="#010101" fill-opacity=".3">{_LABEL}</text>\n'
        f'    <text x="{label_mid_x}" y="14">{_LABEL}</text>\n'
        f'    <text x="{value_mid_x}" y="15" fill="#010101" fill-opacity=".3">{value_text}</text>\n'
        f'    <text x="{value_mid_x}" y="14">{value_text}</text>\n'
        f'  </g>\n'
        f'</svg>'
    )
    return svg


def badge_img_snippet(slug: str, grade: str, badge_url: str) -> str:
    """
    Return an HTML <img> snippet for embedding the badge.

    Args:
        slug: API slug (e.g., "stripe")
        grade: Grade letter+modifier (e.g., "B+")
        badge_url: e.g. "/badge/stripe.svg"

    Returns:
        HTML <img> tag string
    """
    alt = f"Agent Readiness: {grade}"
    style = "vertical-align: middle; border: 0;"
    return f'<img src="{badge_url}" alt="{alt}" style="{style}">'


def write_badge(slug: str, grade: str, overall_score: float, output_dir: str) -> str:
    """
    Write the SVG badge to output_dir/badge/<slug>.svg.
    Creates the directory if it doesn't exist.

    Args:
        slug: API slug (e.g., "stripe")
        grade: Grade letter+modifier (e.g., "B+")
        overall_score: 0-100 float
        output_dir: Base output directory (e.g., "site")

    Returns:
        The absolute path to the written SVG file.
    """
    badge_dir = os.path.join(output_dir, "badge")
    os.makedirs(badge_dir, exist_ok=True)
    path = os.path.join(badge_dir, f"{slug}.svg")
    svg = generate_badge(slug, grade, overall_score)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(svg)
    return os.path.abspath(path)
