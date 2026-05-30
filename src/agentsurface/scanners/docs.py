"""Docs Accessibility scanner: measures whether agent documentation is reachable,
content-dense, and accessible without JavaScript execution."""
from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from agentsurface import http
from agentsurface.framework import compute_dimension_score
from agentsurface.models import DimensionScore, SignalStatus
from agentsurface.scanners import register
from agentsurface.scanners.base import Scanner, Target, make_signal


def _base(url: str | None) -> str | None:
    if not url:
        return None
    p = urlparse(url)
    if p.scheme and p.netloc:
        return f"{p.scheme}://{p.netloc}"
    return None


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


@register
class DocsScanner(Scanner):
    dimension_id = "docs_accessibility"
    dimension_name = "Docs Accessibility"
    weight = 0.20

    async def scan(
        self,
        target: Target,
        *,
        fetch_records: list,
        test_mode: bool = False,
    ) -> DimensionScore:
        signals = []

        docs_base = _base(target.docs_url)
        home_base = _base(target.homepage)
        bases = list(dict.fromkeys(b for b in [docs_base, home_base] if b))

        # --- docs.llms_txt ---
        # Probe both docs_url domain AND homepage domain so that cases like
        # OpenAI (docs at platform.openai.com, llms.txt at openai.com) are detected.
        llms_txt_pass = False
        llms_txt_url: str | None = None
        llms_txt_probed: list[str] = []
        for base in bases:
            url = f"{base}/llms.txt"
            llms_txt_probed.append(url)
            try:
                resp = await http.fetch(url, record_list=fetch_records)
                if resp.status_code == 200 and resp.content:
                    llms_txt_pass = True
                    llms_txt_url = url
                    break
            except httpx.HTTPError:
                pass

        signals.append(make_signal(
            id="docs.llms_txt",
            label="llms.txt present",
            weight=0.30,
            status=SignalStatus.PASS if llms_txt_pass else SignalStatus.FAIL,
            evidence_url=llms_txt_url,
            notes=(
                f"Found at {llms_txt_url}" if llms_txt_pass
                else f"Probed {', '.join(llms_txt_probed)} — none returned 200 with content"
            ),
        ))

        # --- docs.llms_full_txt ---
        llms_full_pass = False
        llms_full_url: str | None = None
        for base in bases:
            for path in ("/llms-full.txt", "/llms.md", "/llms-full.md"):
                url = f"{base}{path}"
                try:
                    resp = await http.fetch(url, record_list=fetch_records)
                    if resp.status_code == 200:
                        llms_full_pass = True
                        llms_full_url = url
                        break
                except httpx.HTTPError:
                    pass
            if llms_full_pass:
                break

        signals.append(make_signal(
            id="docs.llms_full_txt",
            label="llms-full.txt / Markdown variant present",
            weight=0.20,
            status=SignalStatus.PASS if llms_full_pass else SignalStatus.FAIL,
            evidence_url=llms_full_url,
            notes=None if llms_full_pass else "No llms-full.txt / .md variant found",
        ))

        # --- docs.html_content_density & docs.no_js_gates ---
        # Both need the docs page HTML — fetch once.
        html_text: str | None = None
        fetch_failed = False
        if target.docs_url:
            try:
                resp = await http.fetch(target.docs_url, record_list=fetch_records)
                if resp.status_code == 200:
                    html_text = resp.text
            except httpx.HTTPError:
                fetch_failed = True

        # docs.html_content_density
        if html_text is None:
            density_status = SignalStatus.SKIP
            if fetch_failed or not target.docs_url:
                density_notes = "Fetch failed or no docs_url"
            else:
                density_notes = "Non-200 response"
        else:
            total_bytes = len(html_text.encode("utf-8"))
            text_content = _strip_tags(html_text)
            text_bytes = len(text_content.encode("utf-8"))
            ratio = text_bytes / total_bytes if total_bytes else 0.0
            if ratio >= 0.20:
                density_status = SignalStatus.PASS
                density_notes = f"text/total ratio {ratio:.2f}"
            elif ratio >= 0.10:
                density_status = SignalStatus.PARTIAL
                density_notes = f"text/total ratio {ratio:.2f} (marginal)"
            else:
                density_status = SignalStatus.FAIL
                density_notes = f"text/total ratio {ratio:.2f} (too low)"

        signals.append(make_signal(
            id="docs.html_content_density",
            label="Docs page content density",
            weight=0.25,
            status=density_status,
            evidence_url=target.docs_url if html_text is not None else None,
            notes=density_notes,
        ))

        # docs.no_js_gates
        if html_text is None:
            js_status = SignalStatus.SKIP
            js_notes = "Fetch failed or no docs_url"
        else:
            total_bytes = len(html_text.encode("utf-8"))
            text_content = _strip_tags(html_text)
            text_bytes = len(text_content.encode("utf-8"))
            lower_html = html_text.lower()
            has_noscript_gate = bool(re.search(
                r"<noscript[^>]*>.*?(javascript required|please enable javascript)",
                lower_html,
                re.DOTALL,
            ))
            if has_noscript_gate:
                js_status = SignalStatus.FAIL
                js_notes = "noscript block indicates JavaScript is required"
            elif text_bytes < 500 and total_bytes > 50_000:
                js_status = SignalStatus.FAIL
                js_notes = f"Likely JS-gated: {text_bytes} text bytes in {total_bytes} total"
            elif text_bytes < 500:
                js_status = SignalStatus.PARTIAL
                js_notes = f"Low text content ({text_bytes} bytes), uncertain"
            else:
                js_status = SignalStatus.PASS
                js_notes = f"{text_bytes} text bytes present; no JS gate detected"

        signals.append(make_signal(
            id="docs.no_js_gates",
            label="Content accessible without JavaScript",
            weight=0.25,
            status=js_status,
            evidence_url=target.docs_url if html_text is not None else None,
            notes=js_notes,
        ))

        # --- docs.changelog_discoverable ---
        changelog_paths = [
            "/changelog", "/releases", "/release-notes", "/whats-new", "/what-s-new",
        ]
        changelog_found = False
        changelog_url: str | None = None
        changelog_probed: list[str] = []

        if docs_base:
            for path in changelog_paths:
                url = f"{docs_base}{path}"
                changelog_probed.append(url)
                try:
                    resp = await http.fetch(url, record_list=fetch_records)
                    if resp.status_code == 200:
                        changelog_found = True
                        changelog_url = url
                        break
                except httpx.HTTPError:
                    pass

        if not changelog_found and target.github_org:
            # Probe GitHub releases page
            repo_candidates = [target.slug]
            for candidate in repo_candidates:
                gh_url = f"https://github.com/{target.github_org}/{candidate}/releases"
                changelog_probed.append(gh_url)
                try:
                    resp = await http.fetch(gh_url, record_list=fetch_records)
                    if resp.status_code == 200 and "releases" in resp.text.lower():
                        changelog_found = True
                        changelog_url = gh_url
                        break
                except httpx.HTTPError:
                    pass

        signals.append(make_signal(
            id="docs.changelog_discoverable",
            label="Changelog discoverable",
            weight=0.15,
            status=SignalStatus.PASS if changelog_found else SignalStatus.FAIL,
            evidence_url=changelog_url,
            notes=(
                f"Found at {changelog_url}" if changelog_found
                else f"Probed {len(changelog_probed)} paths — none returned 200"
            ),
        ))

        # --- docs.sitemap_present ---
        sitemap_found = False
        sitemap_url: str | None = None

        if docs_base:
            url = f"{docs_base}/sitemap.xml"
            try:
                resp = await http.fetch(url, record_list=fetch_records)
                if resp.status_code == 200 and "<url>" in resp.text:
                    sitemap_found = True
                    sitemap_url = url
            except httpx.HTTPError:
                pass

        signals.append(make_signal(
            id="docs.sitemap_present",
            label="sitemap.xml present",
            weight=0.10,
            status=SignalStatus.PASS if sitemap_found else SignalStatus.FAIL,
            evidence_url=sitemap_url,
            notes=(
                f"Found at {sitemap_url}" if sitemap_found
                else (
                    f"Probed {docs_base + '/sitemap.xml' if docs_base else 'N/A'}"
                    " — not found or no <url> entries"
                )
            ),
        ))

        score = compute_dimension_score(signals)
        return self._make_dimension_score(signals, score)
