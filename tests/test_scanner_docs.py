from pathlib import Path

import httpx
import pytest
import respx

from agentsurface.scanners.base import Target
from agentsurface.scanners.docs import DocsScanner

FIXTURES = Path(__file__).parent / "fixtures" / "docs"
pytestmark = pytest.mark.asyncio


def _signal(result, signal_id):
    return next(s for s in result.signals if s.id == signal_id)


_CHANGELOG_PATHS = ["/changelog", "/releases", "/release-notes", "/whats-new", "/what-s-new"]


def _mock_changelog_404(base: str) -> None:
    for path in _CHANGELOG_PATHS:
        respx.get(f"{base}{path}").mock(return_value=httpx.Response(404))


@respx.mock
async def test_docs_pass():
    llms_txt_content = (FIXTURES / "llms_txt.txt").read_bytes()
    docs_html = (FIXTURES / "docs_page_pass.html").read_bytes()

    respx.get("https://docs.testapi.example.com/llms.txt").mock(
        return_value=httpx.Response(200, content=llms_txt_content)
    )
    respx.get("https://testapi.example.com/llms.txt").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://docs.testapi.example.com/llms-full.txt").mock(
        return_value=httpx.Response(200, content=b"# LLMs Full")
    )
    # Home base llms-full paths (not reached since docs_base succeeds first, but mock anyway)
    respx.get("https://testapi.example.com/llms-full.txt").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://docs.testapi.example.com/llms.md").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://docs.testapi.example.com/llms-full.md").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://testapi.example.com/llms.md").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://testapi.example.com/llms-full.md").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://docs.testapi.example.com").mock(
        return_value=httpx.Response(200, content=docs_html, headers={"content-type": "text/html"})
    )
    # New signals: changelog paths and sitemap (all 404 for this test)
    _mock_changelog_404("https://docs.testapi.example.com")
    respx.get("https://docs.testapi.example.com/sitemap.xml").mock(
        return_value=httpx.Response(404)
    )

    target = Target(
        slug="testapi",
        name="Test API",
        category="test",
        homepage="https://testapi.example.com",
        docs_url="https://docs.testapi.example.com",
    )
    scanner = DocsScanner()
    result = await scanner.scan(target, fetch_records=[])

    assert _signal(result, "docs.llms_txt").status == "pass"
    assert _signal(result, "docs.llms_full_txt").status == "pass"
    assert _signal(result, "docs.html_content_density").status == "pass"
    assert _signal(result, "docs.no_js_gates").status == "pass"


@respx.mock
async def test_docs_no_llms_txt():
    jsgated_html = (FIXTURES / "docs_page_jsgated.html").read_bytes()

    for base in ("https://docs.testapi.example.com", "https://testapi.example.com"):
        respx.get(f"{base}/llms.txt").mock(return_value=httpx.Response(404))
        for path in ("/llms-full.txt", "/llms.md", "/llms-full.md"):
            respx.get(f"{base}{path}").mock(return_value=httpx.Response(404))

    respx.get("https://docs.testapi.example.com").mock(
        return_value=httpx.Response(
            200, content=jsgated_html, headers={"content-type": "text/html"}
        )
    )
    # New signals
    _mock_changelog_404("https://docs.testapi.example.com")
    respx.get("https://docs.testapi.example.com/sitemap.xml").mock(
        return_value=httpx.Response(404)
    )

    target = Target(
        slug="testapi",
        name="Test API",
        category="test",
        homepage="https://testapi.example.com",
        docs_url="https://docs.testapi.example.com",
    )
    scanner = DocsScanner()
    result = await scanner.scan(target, fetch_records=[])

    assert _signal(result, "docs.llms_txt").status == "fail"
    assert _signal(result, "docs.llms_full_txt").status == "fail"
    assert _signal(result, "docs.no_js_gates").status == "fail"


@respx.mock
async def test_docs_page_fetch_fails():
    for base in ("https://docs.testapi.example.com", "https://testapi.example.com"):
        respx.get(f"{base}/llms.txt").mock(return_value=httpx.Response(404))
        for path in ("/llms-full.txt", "/llms.md", "/llms-full.md"):
            respx.get(f"{base}{path}").mock(return_value=httpx.Response(404))

    respx.get("https://docs.testapi.example.com").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    # New signals
    _mock_changelog_404("https://docs.testapi.example.com")
    respx.get("https://docs.testapi.example.com/sitemap.xml").mock(
        return_value=httpx.Response(404)
    )

    target = Target(
        slug="testapi",
        name="Test API",
        category="test",
        homepage="https://testapi.example.com",
        docs_url="https://docs.testapi.example.com",
    )
    scanner = DocsScanner()
    result = await scanner.scan(target, fetch_records=[])

    assert _signal(result, "docs.html_content_density").status == "skip"
    assert _signal(result, "docs.no_js_gates").status == "skip"
