"""Checks whether an API has published agent-discovery artefacts.

Artefacts checked: AGENTS.md, MCP server, ai-plugin.json, robots.txt AI policy.
"""
from __future__ import annotations

import json
from urllib.parse import urlparse

import httpx

from agentsurface import http
from agentsurface.framework import compute_dimension_score
from agentsurface.models import DimensionScore, SignalStatus
from agentsurface.scanners import register
from agentsurface.scanners.base import Scanner, Target, make_signal


@register
class DiscoveryScanner(Scanner):
    dimension_id = "discovery_surface"
    dimension_name = "Discovery Surface"
    weight = 0.15

    async def scan(
        self,
        target: Target,
        *,
        fetch_records: list,
        test_mode: bool = False,
    ) -> DimensionScore:
        signals = []

        # 1. discovery.agents_md
        signals.append(await self._check_agents_md(target, fetch_records))

        # 2. discovery.mcp_server
        signals.append(await self._check_mcp_server(target, fetch_records))

        # 3. discovery.ai_plugin_json
        signals.append(await self._check_ai_plugin_json(target, fetch_records))

        # 4. discovery.robots_ai_policy
        signals.append(await self._check_robots_ai_policy(target, fetch_records))

        # 5. discovery.llms_txt_disallow_rules
        signals.append(await self._check_llms_txt_disallow(target, fetch_records))

        # 6. discovery.changelog_feed_present
        signals.append(await self._check_changelog_feed(target, fetch_records))

        score = compute_dimension_score(signals)
        return self._make_dimension_score(signals, score)

    async def _check_agents_md(self, target: Target, fetch_records: list):
        if not target.github_org:
            return make_signal(
                id="discovery.agents_md",
                label="AGENTS.md in GitHub repo",
                weight=0.30,
                status=SignalStatus.SKIP,
                notes="No github_org set",
            )

        repo_candidates = [
            c for c in [target.slug, target.npm_package, target.pypi_package] if c
        ]
        if not repo_candidates:
            return make_signal(
                id="discovery.agents_md",
                label="AGENTS.md in GitHub repo",
                weight=0.30,
                status=SignalStatus.SKIP,
                notes="No repo name candidate",
            )

        for repo in repo_candidates:
            for branch in ("main", "master"):
                url = f"https://raw.githubusercontent.com/{target.github_org}/{repo}/{branch}/AGENTS.md"
                try:
                    resp = await http.fetch(url, record_list=fetch_records)
                    if resp.status_code == 200 and resp.text.strip():
                        return make_signal(
                            id="discovery.agents_md",
                            label="AGENTS.md in GitHub repo",
                            weight=0.30,
                            status=SignalStatus.PASS,
                            evidence_url=url,
                        )
                except httpx.HTTPError:
                    continue

        return make_signal(
            id="discovery.agents_md",
            label="AGENTS.md in GitHub repo",
            weight=0.30,
            status=SignalStatus.FAIL,
            notes="AGENTS.md not found in any candidate repo/branch",
        )

    async def _check_mcp_server(self, target: Target, fetch_records: list):
        if target.mcp_server_url:
            try:
                resp = await http.fetch(target.mcp_server_url, record_list=fetch_records)
                if resp.status_code in (200, 401, 405):
                    return make_signal(
                        id="discovery.mcp_server",
                        label="MCP server documented or reachable",
                        weight=0.25,
                        status=SignalStatus.PASS,
                        evidence_url=target.mcp_server_url,
                    )
                return make_signal(
                    id="discovery.mcp_server",
                    label="MCP server documented or reachable",
                    weight=0.25,
                    status=SignalStatus.FAIL,
                    notes=f"HTTP {resp.status_code}",
                )
            except httpx.TimeoutException:
                return make_signal(
                    id="discovery.mcp_server",
                    label="MCP server documented or reachable",
                    weight=0.25,
                    status=SignalStatus.SKIP,
                    notes="Connection timeout",
                )
            except httpx.HTTPError as exc:
                return make_signal(
                    id="discovery.mcp_server",
                    label="MCP server documented or reachable",
                    weight=0.25,
                    status=SignalStatus.FAIL,
                    notes=str(exc),
                )

        # No mcp_server_url — scan homepage and docs_url HTML for MCP mentions
        mcp_keywords = ("mcp", "model context protocol")
        found = False
        for url in filter(None, [target.homepage, target.docs_url]):
            try:
                resp = await http.fetch(url, record_list=fetch_records)
                if resp.status_code == 200:
                    text_lower = resp.text.lower()
                    if any(kw in text_lower for kw in mcp_keywords):
                        found = True
                        break
            except httpx.HTTPError:
                continue

        if found:
            return make_signal(
                id="discovery.mcp_server",
                label="MCP server documented or reachable",
                weight=0.25,
                status=SignalStatus.PARTIAL,
                notes="MCP mentioned in homepage/docs but no mcp_server_url set",
            )
        return make_signal(
            id="discovery.mcp_server",
            label="MCP server documented or reachable",
            weight=0.25,
            status=SignalStatus.FAIL,
            notes="No MCP server URL and no MCP mention found",
        )

    async def _check_ai_plugin_json(self, target: Target, fetch_records: list):
        parsed = urlparse(target.homepage)
        base = f"{parsed.scheme}://{parsed.netloc}"
        url = f"{base}/.well-known/ai-plugin.json"

        try:
            resp = await http.fetch(url, record_list=fetch_records)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    plugin_fields = {
                        "name_for_human", "name_for_model",
                        "description_for_human", "api",
                    }
                    if isinstance(data, dict) and plugin_fields & data.keys():
                        return make_signal(
                            id="discovery.ai_plugin_json",
                            label="/.well-known/ai-plugin.json present",
                            weight=0.20,
                            status=SignalStatus.PASS,
                            evidence_url=url,
                        )
                    return make_signal(
                        id="discovery.ai_plugin_json",
                        label="/.well-known/ai-plugin.json present",
                        weight=0.20,
                        status=SignalStatus.PARTIAL,
                        notes="200 but missing expected plugin manifest fields",
                        evidence_url=url,
                    )
                except (json.JSONDecodeError, ValueError):
                    return make_signal(
                        id="discovery.ai_plugin_json",
                        label="/.well-known/ai-plugin.json present",
                        weight=0.20,
                        status=SignalStatus.PARTIAL,
                        notes="200 but body is not valid JSON",
                        evidence_url=url,
                    )
            return make_signal(
                id="discovery.ai_plugin_json",
                label="/.well-known/ai-plugin.json present",
                weight=0.20,
                status=SignalStatus.FAIL,
                notes=f"HTTP {resp.status_code}",
            )
        except httpx.HTTPError as exc:
            return make_signal(
                id="discovery.ai_plugin_json",
                label="/.well-known/ai-plugin.json present",
                weight=0.20,
                status=SignalStatus.SKIP,
                notes=str(exc),
            )

    async def _check_robots_ai_policy(self, target: Target, fetch_records: list):
        parsed = urlparse(target.homepage)
        base = f"{parsed.scheme}://{parsed.netloc}"
        url = f"{base}/robots.txt"

        ai_crawlers = {
            "gptbot", "claudebot", "perplexitybot", "anthropic-ai",
            "chatgpt-user", "google-extended", "bytespider",
        }

        try:
            resp = await http.fetch(url, record_list=fetch_records)
            if resp.status_code != 200:
                return make_signal(
                    id="discovery.robots_ai_policy",
                    label="robots.txt distinguishes AI crawlers",
                    weight=0.25,
                    status=SignalStatus.SKIP,
                    notes=f"robots.txt returned HTTP {resp.status_code}",
                )

            found_agents: set[str] = set()
            for line in resp.text.splitlines():
                line_stripped = line.strip().lower()
                if line_stripped.startswith("user-agent:"):
                    agent = line_stripped.split(":", 1)[1].strip()
                    if agent in ai_crawlers:
                        found_agents.add(agent)

            if len(found_agents) >= 2:
                return make_signal(
                    id="discovery.robots_ai_policy",
                    label="robots.txt distinguishes AI crawlers",
                    weight=0.25,
                    status=SignalStatus.PASS,
                    evidence_url=url,
                    notes=f"Found AI crawlers: {', '.join(sorted(found_agents))}",
                )
            if len(found_agents) == 1:
                return make_signal(
                    id="discovery.robots_ai_policy",
                    label="robots.txt distinguishes AI crawlers",
                    weight=0.25,
                    status=SignalStatus.PARTIAL,
                    evidence_url=url,
                    notes=f"Only 1 AI crawler entry: {next(iter(found_agents))}",
                )
            return make_signal(
                id="discovery.robots_ai_policy",
                label="robots.txt distinguishes AI crawlers",
                weight=0.25,
                status=SignalStatus.FAIL,
                notes="robots.txt exists but no AI-specific User-agent entries found",
            )
        except httpx.HTTPError as exc:
            return make_signal(
                id="discovery.robots_ai_policy",
                label="robots.txt distinguishes AI crawlers",
                weight=0.25,
                status=SignalStatus.SKIP,
                notes=str(exc),
            )

    async def _check_llms_txt_disallow(self, target: Target, fetch_records: list):
        """Check if llms.txt has disallow rules (signal: discovery.llms_txt_disallow_rules)."""
        parsed = urlparse(target.homepage)
        if not parsed.scheme or not parsed.netloc:
            return make_signal(
                id="discovery.llms_txt_disallow_rules",
                label="llms.txt has disallow rules",
                weight=0.10,
                status=SignalStatus.SKIP,
                notes="Homepage not reachable or not configured",
            )

        bases = [f"{parsed.scheme}://{parsed.netloc}"]
        # Also check docs_url domain if different
        if target.docs_url:
            dp = urlparse(target.docs_url)
            docs_base = f"{dp.scheme}://{dp.netloc}"
            if docs_base not in bases:
                bases.append(docs_base)

        llms_txt_content: str | None = None
        llms_txt_found_url: str | None = None

        for base in bases:
            url = f"{base}/llms.txt"
            try:
                resp = await http.fetch(url, record_list=fetch_records)
                if resp.status_code == 200 and resp.content:
                    llms_txt_content = resp.text
                    llms_txt_found_url = url
                    break
            except httpx.HTTPError:
                pass

        if llms_txt_content is None:
            return make_signal(
                id="discovery.llms_txt_disallow_rules",
                label="llms.txt has disallow rules",
                weight=0.10,
                status=SignalStatus.FAIL,
                notes="llms.txt not found at any probed URL",
            )

        has_disallow = "disallow:" in llms_txt_content.lower()
        if has_disallow:
            return make_signal(
                id="discovery.llms_txt_disallow_rules",
                label="llms.txt has disallow rules",
                weight=0.10,
                status=SignalStatus.PASS,
                evidence_url=llms_txt_found_url,
                notes="llms.txt contains disallow: entries",
            )
        return make_signal(
            id="discovery.llms_txt_disallow_rules",
            label="llms.txt has disallow rules",
            weight=0.10,
            status=SignalStatus.PARTIAL,
            evidence_url=llms_txt_found_url,
            notes="llms.txt exists but no disallow: rules found",
        )

    async def _check_changelog_feed(self, target: Target, fetch_records: list):
        """Check for RSS/Atom changelog feed (signal: discovery.changelog_feed_present)."""
        if not target.homepage:
            return make_signal(
                id="discovery.changelog_feed_present",
                label="Changelog feed (RSS/Atom) present",
                weight=0.10,
                status=SignalStatus.SKIP,
                notes="No homepage configured",
            )

        parsed = urlparse(target.homepage)
        base = f"{parsed.scheme}://{parsed.netloc}"
        feed_paths = ["/feed.xml", "/atom.xml", "/rss.xml", "/feed"]
        feed_found_url: str | None = None

        for path in feed_paths:
            url = f"{base}{path}"
            try:
                resp = await http.fetch(url, record_list=fetch_records)
                if resp.status_code == 200 and resp.content:
                    ct = resp.headers.get("content-type", "").lower()
                    body = resp.text.lower()
                    if (
                        "xml" in ct or "rss" in ct or "atom" in ct
                        or "<rss" in body or "<feed" in body or "<channel" in body
                    ):
                        feed_found_url = url
                        break
            except httpx.HTTPError:
                pass

        # Also check GitHub releases.atom if github_org is set
        if feed_found_url is None and target.github_org:
            repo_candidates = [
                c for c in [target.slug, target.npm_package, target.pypi_package] if c
            ]
            for repo in repo_candidates:
                url = f"https://github.com/{target.github_org}/{repo}/releases.atom"
                try:
                    resp = await http.fetch(url, record_list=fetch_records)
                    if resp.status_code == 200 and resp.content:
                        feed_found_url = url
                        break
                except httpx.HTTPError:
                    pass
            if feed_found_url:
                pass  # found

        if feed_found_url:
            return make_signal(
                id="discovery.changelog_feed_present",
                label="Changelog feed (RSS/Atom) present",
                weight=0.10,
                status=SignalStatus.PASS,
                evidence_url=feed_found_url,
                notes=f"Feed found at {feed_found_url}",
            )
        return make_signal(
            id="discovery.changelog_feed_present",
            label="Changelog feed (RSS/Atom) present",
            weight=0.10,
            status=SignalStatus.FAIL,
            notes="No RSS/Atom feed found at homepage or GitHub releases",
        )
