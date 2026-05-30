import json
from pathlib import Path

import httpx
import pytest
import respx

from agentsurface.scanners.base import Target
from agentsurface.scanners.sdk import SDKScanner

FIXTURES = Path(__file__).parent / "fixtures" / "sdk"
pytestmark = pytest.mark.asyncio


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


def _signal(result, signal_id: str):
    return next(s for s in result.signals if s.id == signal_id)


@respx.mock
@pytest.mark.asyncio
async def test_sdk_pass():
    npm_json = json.loads((FIXTURES / "npm_response_pass.json").read_text())
    pypi_json = json.loads((FIXTURES / "pypi_response_pass.json").read_text())
    readme_text = (FIXTURES / "readme_pass.md").read_text()

    respx.get("https://registry.npmjs.org/testapi").mock(
        return_value=httpx.Response(200, json=npm_json)
    )
    respx.get("https://pypi.org/pypi/testapi/json").mock(
        return_value=httpx.Response(200, json=pypi_json)
    )
    respx.get("https://raw.githubusercontent.com/testorg/testapi/HEAD/README.md").mock(
        return_value=httpx.Response(200, text=readme_text)
    )

    target = _make_target(npm_package="testapi", pypi_package="testapi", github_org="testorg")
    scanner = SDKScanner()
    result = await scanner.scan(target, fetch_records=[])

    for sid in [
        "sdk.npm_package",
        "sdk.pypi_package",
        "sdk.readme_install_oneliner",
        "sdk.typed",
        "sdk.readme_quickstart_length",
    ]:
        assert _signal(result, sid).status == "pass", f"{sid} should be pass"

    assert result.score > 80.0


@pytest.mark.asyncio
async def test_sdk_no_packages():
    target = _make_target(npm_package=None, pypi_package=None, github_org=None)
    scanner = SDKScanner()
    result = await scanner.scan(target, fetch_records=[])

    assert _signal(result, "sdk.npm_package").status == "skip"
    assert _signal(result, "sdk.pypi_package").status == "skip"
    assert _signal(result, "sdk.readme_install_oneliner").status == "skip"
    assert _signal(result, "sdk.typed").status == "skip"


@respx.mock
@pytest.mark.asyncio
async def test_sdk_npm_not_found():
    respx.get("https://registry.npmjs.org/nonexistent").mock(
        return_value=httpx.Response(404)
    )

    target = _make_target(npm_package="nonexistent", pypi_package=None, github_org=None)
    scanner = SDKScanner()
    result = await scanner.scan(target, fetch_records=[])

    assert _signal(result, "sdk.npm_package").status == "fail"


@respx.mock
@pytest.mark.asyncio
async def test_sdk_readme_no_install():
    npm_json = json.loads((FIXTURES / "npm_response_pass.json").read_text())
    pypi_json = json.loads((FIXTURES / "pypi_response_pass.json").read_text())

    respx.get("https://registry.npmjs.org/testapi").mock(
        return_value=httpx.Response(200, json=npm_json)
    )
    respx.get("https://pypi.org/pypi/testapi/json").mock(
        return_value=httpx.Response(200, json=pypi_json)
    )
    respx.get("https://raw.githubusercontent.com/testorg/testapi/HEAD/README.md").mock(
        return_value=httpx.Response(200, text="# Test API\n\nThis is a test API.\n")
    )

    target = _make_target(npm_package="testapi", pypi_package="testapi", github_org="testorg")
    scanner = SDKScanner()
    result = await scanner.scan(target, fetch_records=[])

    assert _signal(result, "sdk.readme_install_oneliner").status == "fail"
