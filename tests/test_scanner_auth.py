from pathlib import Path

import httpx
import pytest
import respx

from agentsurface.scanners.auth import AuthScanner
from agentsurface.scanners.base import Target

FIXTURES = Path(__file__).parent / "fixtures" / "auth"
pytestmark = pytest.mark.asyncio

_M2M_PATHS = [
    "/docs/service-accounts",
    "/docs/machine-to-machine",
    "/docs/m2m",
    "/docs/api-keys/service",
    "/docs/oauth/client-credentials",
]
_WEBHOOK_PATHS = ["/docs/webhooks", "/webhooks", "/docs/events"]


def _mock_m2m_404(base: str) -> None:
    for path in _M2M_PATHS:
        respx.get(f"{base}{path}").mock(return_value=httpx.Response(404))


def _mock_webhook_404(base: str) -> None:
    for path in _WEBHOOK_PATHS:
        respx.get(f"{base}{path}").mock(return_value=httpx.Response(404))


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


def _sig(result, sig_id: str):
    return next(s for s in result.signals if s.id == sig_id)


@respx.mock
async def test_auth_pass_with_apikey():
    docs_html = (FIXTURES / "docs_pass.html").read_text()
    home_html = (FIXTURES / "home_pass.html").read_text()
    spec_json = (FIXTURES / "spec_with_apikey.json").read_text()

    respx.get("https://docs.testapi.example.com/").mock(
        return_value=httpx.Response(200, text=docs_html, headers={"content-type": "text/html"})
    )
    respx.get("https://testapi.example.com/").mock(
        return_value=httpx.Response(200, text=home_html, headers={"content-type": "text/html"})
    )
    # Scanner fetches openapi_url twice (signal 2 and signal 3)
    respx.get("https://docs.testapi.example.com/openapi.json").mock(
        return_value=httpx.Response(
            200, text=spec_json, headers={"content-type": "application/json"}
        )
    )
    # New signals: m2m and webhook probes (all 404)
    _mock_m2m_404("https://docs.testapi.example.com")
    _mock_webhook_404("https://docs.testapi.example.com")

    target = _make_target(openapi_url="https://docs.testapi.example.com/openapi.json")
    scanner = AuthScanner()
    result = await scanner.scan(target, fetch_records=[])

    assert _sig(result, "auth.programmatic_key_issuance").status == "pass"
    assert _sig(result, "auth.security_schemes_defined").status == "pass"
    assert _sig(result, "auth.scopes_enumerable").status == "partial"


@respx.mock
async def test_auth_oauth_scopes():
    docs_html = (FIXTURES / "docs_pass.html").read_text()
    home_html = (FIXTURES / "home_pass.html").read_text()
    spec_json = (FIXTURES / "spec_with_oauth.json").read_text()

    respx.get("https://docs.testapi.example.com/").mock(
        return_value=httpx.Response(200, text=docs_html, headers={"content-type": "text/html"})
    )
    respx.get("https://testapi.example.com/").mock(
        return_value=httpx.Response(200, text=home_html, headers={"content-type": "text/html"})
    )
    respx.get("https://docs.testapi.example.com/openapi.json").mock(
        return_value=httpx.Response(
            200, text=spec_json, headers={"content-type": "application/json"}
        )
    )
    # New signals: m2m and webhook probes (all 404)
    _mock_m2m_404("https://docs.testapi.example.com")
    _mock_webhook_404("https://docs.testapi.example.com")

    target = _make_target(openapi_url="https://docs.testapi.example.com/openapi.json")
    scanner = AuthScanner()
    result = await scanner.scan(target, fetch_records=[])

    assert _sig(result, "auth.security_schemes_defined").status == "pass"
    assert _sig(result, "auth.scopes_enumerable").status == "pass"


@respx.mock
async def test_auth_no_openapi():
    """No openapi_url — security_schemes_defined skips; dashboard-only → programmatic partial."""
    docs_html = "<html><body>Get your key from the dashboard.</body></html>"
    home_html = (FIXTURES / "home_pass.html").read_text()

    respx.get("https://docs.testapi.example.com/").mock(
        return_value=httpx.Response(200, text=docs_html, headers={"content-type": "text/html"})
    )
    respx.get("https://testapi.example.com/").mock(
        return_value=httpx.Response(200, text=home_html, headers={"content-type": "text/html"})
    )
    # New signals: m2m and webhook probes (all 404)
    _mock_m2m_404("https://docs.testapi.example.com")
    _mock_webhook_404("https://docs.testapi.example.com")

    target = _make_target(openapi_url=None)
    scanner = AuthScanner()
    result = await scanner.scan(target, fetch_records=[])

    assert _sig(result, "auth.security_schemes_defined").status == "skip"
    assert _sig(result, "auth.programmatic_key_issuance").status == "partial"
