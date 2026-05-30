from pathlib import Path

import httpx
import pytest
import respx

from agentsurface.scanners.base import Target
from agentsurface.scanners.discovery import DiscoveryScanner

FIXTURES = Path(__file__).parent / "fixtures" / "discovery"
pytestmark = pytest.mark.asyncio


def _sig(result, sig_id: str):
    return next(s for s in result.signals if s.id == sig_id)


def _make_target(**kwargs) -> Target:
    defaults = dict(
        slug="testapi",
        name="Test API",
        category="test",
        homepage="https://testapi.example.com",
        docs_url="https://docs.testapi.example.com",
    )
    defaults.update(kwargs)
    return Target(**defaults)


_FEED_PATHS = ["/feed.xml", "/atom.xml", "/rss.xml", "/feed"]


def _mock_feeds_404(base: str) -> None:
    for path in _FEED_PATHS:
        respx.get(f"{base}{path}").mock(return_value=httpx.Response(404))


@respx.mock
async def test_discovery_pass():
    agents_md_content = (FIXTURES / "agents_md.md").read_bytes()
    ai_plugin_content = (FIXTURES / "ai_plugin.json").read_bytes()
    robots_pass_content = (FIXTURES / "robots_pass.txt").read_bytes()

    respx.get("https://raw.githubusercontent.com/testorg/testapi/main/AGENTS.md").mock(
        return_value=httpx.Response(200, content=agents_md_content)
    )
    respx.get("https://testapi.example.com/").mock(
        return_value=httpx.Response(
            200, content=b"<html><body>Welcome. We support MCP.</body></html>"
        )
    )
    respx.get("https://docs.testapi.example.com/").mock(
        return_value=httpx.Response(
            200,
            content=b"<html><body>model context protocol is supported.</body></html>",
        )
    )
    respx.get("https://testapi.example.com/.well-known/ai-plugin.json").mock(
        return_value=httpx.Response(
            200, content=ai_plugin_content, headers={"content-type": "application/json"}
        )
    )
    respx.get("https://testapi.example.com/robots.txt").mock(
        return_value=httpx.Response(200, content=robots_pass_content)
    )
    # New signals: llms.txt disallow (homepage + docs domains) and feeds
    respx.get("https://testapi.example.com/llms.txt").mock(return_value=httpx.Response(404))
    respx.get("https://docs.testapi.example.com/llms.txt").mock(return_value=httpx.Response(404))
    _mock_feeds_404("https://testapi.example.com")
    # GitHub releases.atom for slug=testapi, npm_package=testapi (same repo, checked once)
    respx.get("https://github.com/testorg/testapi/releases.atom").mock(
        return_value=httpx.Response(404)
    )

    target = _make_target(github_org="testorg", npm_package="testapi")
    scanner = DiscoveryScanner()
    result = await scanner.scan(target, fetch_records=[])

    assert _sig(result, "discovery.agents_md").status == "pass"
    assert _sig(result, "discovery.mcp_server").status == "partial"
    assert _sig(result, "discovery.ai_plugin_json").status == "pass"
    assert _sig(result, "discovery.robots_ai_policy").status == "pass"


@respx.mock
async def test_discovery_fail():
    robots_fail_content = (FIXTURES / "robots_fail.txt").read_bytes()

    # slug == npm_package == "testapi" → only 2 unique repo+branch combos
    respx.get("https://raw.githubusercontent.com/testorg/testapi/main/AGENTS.md").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://raw.githubusercontent.com/testorg/testapi/master/AGENTS.md").mock(
        return_value=httpx.Response(404)
    )

    respx.get("https://testapi.example.com/").mock(
        return_value=httpx.Response(200, content=b"<html><body>Welcome.</body></html>")
    )
    respx.get("https://docs.testapi.example.com/").mock(
        return_value=httpx.Response(200, content=b"<html><body>Documentation.</body></html>")
    )
    respx.get("https://testapi.example.com/.well-known/ai-plugin.json").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://testapi.example.com/robots.txt").mock(
        return_value=httpx.Response(200, content=robots_fail_content)
    )
    # New signals: llms.txt (all fail) and feeds (all fail)
    respx.get("https://testapi.example.com/llms.txt").mock(return_value=httpx.Response(404))
    respx.get("https://docs.testapi.example.com/llms.txt").mock(return_value=httpx.Response(404))
    _mock_feeds_404("https://testapi.example.com")
    respx.get("https://github.com/testorg/testapi/releases.atom").mock(
        return_value=httpx.Response(404)
    )

    target = _make_target(github_org="testorg", npm_package="testapi")
    scanner = DiscoveryScanner()
    result = await scanner.scan(target, fetch_records=[])

    assert _sig(result, "discovery.agents_md").status == "fail"
    assert _sig(result, "discovery.mcp_server").status == "fail"
    assert _sig(result, "discovery.ai_plugin_json").status == "fail"
    assert _sig(result, "discovery.robots_ai_policy").status == "fail"
    assert result.score == 0.0


@respx.mock
async def test_discovery_no_github():
    robots_pass_content = (FIXTURES / "robots_pass.txt").read_bytes()

    respx.get("https://testapi.example.com/").mock(
        return_value=httpx.Response(200, content=b"<html><body>Welcome.</body></html>")
    )
    respx.get("https://docs.testapi.example.com/").mock(
        return_value=httpx.Response(200, content=b"<html><body>Documentation.</body></html>")
    )
    respx.get("https://testapi.example.com/.well-known/ai-plugin.json").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    respx.get("https://testapi.example.com/robots.txt").mock(
        return_value=httpx.Response(200, content=robots_pass_content)
    )
    # New signals: llms.txt and feeds (no github_org, so no releases.atom)
    respx.get("https://testapi.example.com/llms.txt").mock(return_value=httpx.Response(404))
    respx.get("https://docs.testapi.example.com/llms.txt").mock(return_value=httpx.Response(404))
    _mock_feeds_404("https://testapi.example.com")

    target = _make_target(github_org=None)
    scanner = DiscoveryScanner()
    result = await scanner.scan(target, fetch_records=[])

    assert _sig(result, "discovery.agents_md").status == "skip"
    assert _sig(result, "discovery.ai_plugin_json").status == "skip"
    assert _sig(result, "discovery.robots_ai_policy").status == "pass"
