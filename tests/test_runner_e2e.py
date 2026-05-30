"""End-to-end test: run all 6 scanners against a fully-fixtured synthetic target."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx

from agentsurface.models import Grade
from agentsurface.report import write_report
from agentsurface.runner import scan_target
from agentsurface.scanners.base import Target

# ---------------------------------------------------------------------------
# Minimal OpenAPI 3 spec for testco
# ---------------------------------------------------------------------------
_OPENAPI_SPEC = json.dumps({
    "openapi": "3.1.0",
    "info": {"title": "TestCo API", "version": "1.0.0"},
    "servers": [{"url": "https://api.testco.example.com"}],
    "components": {
        "securitySchemes": {
            "ApiKey": {"type": "apiKey", "name": "Authorization", "in": "header"}
        }
    },
    "paths": {
        "/items": {
            "get": {
                "operationId": "listItems",
                "summary": "List items",
                "parameters": [
                    {"name": "limit", "in": "query", "schema": {"type": "integer"}, "example": 10}
                ],
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {"application/json": {"schema": {"type": "array"}}},
                    },
                    "400": {
                        "description": "Bad request",
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {"error": {"type": "string"}},
                        }}},
                    },
                }
            }
        }
    }
})

# Minimal llms.txt content
_LLMS_TXT = "# TestCo API\nThis is the TestCo API documentation.\n"

# HTML with plenty of text content so density >= 0.20 and no JS gate
_DOCS_HTML = (
    "<html><head><title>TestCo Docs</title></head><body>"
    + "<p>Welcome to TestCo API documentation."
    + " This API allows programmatic access to testco resources. "
    + "Use your api key for authentication. Machine users and automated scripts are supported. "
    + "Service account credentials are available for non-interactive access. " * 30
    + "</p></body></html>"
)

# PyPI JSON response
_PYPI_JSON = {
    "info": {
        "name": "testco",
        "version": "1.0.0",
        "classifiers": ["Typing :: Typed"],
        "provides_extra": [],
    },
    "urls": [],
}

# npm registry response
_NPM_JSON = {
    "name": "testco",
    "dist-tags": {"latest": "1.0.0"},
    "versions": {
        "1.0.0": {
            "name": "testco",
            "version": "1.0.0",
            "types": "./index.d.ts",
        }
    },
}

# GitHub README
_README = (
    "# TestCo SDK\n\n"
    "pip install testco\n\n"
    "## Usage\n\nSee docs.\n"
)

# Error probe response
_ERROR_JSON = {
    "error": {
        "code": "not_found",
        "message": "Not found",
        "docs_url": "https://docs.testco.example.com/errors",
    }
}

# ai-plugin.json
_AI_PLUGIN = {
    "name_for_human": "TestCo",
    "name_for_model": "testco",
    "description_for_human": "TestCo API plugin",
    "api": {"type": "openapi", "url": "https://testco.example.com/openapi.json"},
}

# robots.txt with AI crawler entries
_ROBOTS_TXT = (
    "User-agent: *\nDisallow: /private/\n\n"
    "User-agent: GPTBot\nDisallow: /\n\n"
    "User-agent: ClaudeBot\nDisallow: /\n"
)

# AGENTS.md
_AGENTS_MD = "# AGENTS.md\nThis repo is agent-friendly.\n"


def _make_testco_target() -> Target:
    return Target(
        slug="testco",
        name="TestCo API",
        category="devtools",
        homepage="https://testco.example.com",
        docs_url="https://docs.testco.example.com",
        openapi_url="https://testco.example.com/openapi.json",
        github_org="testco",
        npm_package="testco",
        pypi_package="testco",
        error_probes=["https://api.testco.example.com/v1/notfound"],
    )


def _register_all_mocks(mock: respx.MockRouter) -> None:
    """Register all HTTP mocks needed for the 6 scanners."""
    json_ct = {"content-type": "application/json"}
    html_ct = {"content-type": "text/html"}
    text_ct = {"content-type": "text/plain"}

    # --- openapi scanner ---
    mock.get("https://testco.example.com/openapi.json").mock(
        return_value=httpx.Response(200, content=_OPENAPI_SPEC.encode(), headers=json_ct)
    )

    # --- docs scanner ---
    mock.get("https://docs.testco.example.com/llms.txt").mock(
        return_value=httpx.Response(200, content=_LLMS_TXT.encode(), headers=text_ct)
    )
    mock.get("https://docs.testco.example.com/llms-full.txt").mock(
        return_value=httpx.Response(200, content=_LLMS_TXT.encode(), headers=text_ct)
    )
    mock.get("https://docs.testco.example.com/").mock(
        return_value=httpx.Response(200, content=_DOCS_HTML.encode(), headers=html_ct)
    )
    # Fallback: scanner may also try homepage base for llms.txt / llms-full.txt
    mock.get("https://testco.example.com/llms.txt").mock(
        return_value=httpx.Response(404)
    )
    mock.get("https://testco.example.com/llms-full.txt").mock(
        return_value=httpx.Response(404)
    )
    mock.get("https://testco.example.com/llms.md").mock(
        return_value=httpx.Response(404)
    )
    mock.get("https://testco.example.com/llms-full.md").mock(
        return_value=httpx.Response(404)
    )
    mock.get("https://docs.testco.example.com/llms.md").mock(
        return_value=httpx.Response(404)
    )
    mock.get("https://docs.testco.example.com/llms-full.md").mock(
        return_value=httpx.Response(404)
    )

    # --- sdk scanner ---
    mock.get("https://pypi.org/pypi/testco/json").mock(
        return_value=httpx.Response(200, json=_PYPI_JSON, headers=json_ct)
    )
    mock.get("https://registry.npmjs.org/testco").mock(
        return_value=httpx.Response(200, json=_NPM_JSON, headers=json_ct)
    )
    mock.get("https://raw.githubusercontent.com/testco/testco/main/README.md").mock(
        return_value=httpx.Response(200, content=_README.encode(), headers=text_ct)
    )
    # master branch fallback (in case main fails; won't be called but safe to register)
    mock.get("https://raw.githubusercontent.com/testco/testco/master/README.md").mock(
        return_value=httpx.Response(404)
    )

    # --- errors scanner ---
    mock.get("https://api.testco.example.com/v1/notfound").mock(
        return_value=httpx.Response(404, json=_ERROR_JSON, headers=json_ct)
    )

    # --- auth scanner ---
    # docs_url and homepage already mocked above for docs/discovery scanners;
    # auth also fetches homepage:
    mock.get("https://testco.example.com/").mock(
        return_value=httpx.Response(200, content=_DOCS_HTML.encode(), headers=html_ct)
    )

    # --- discovery scanner ---
    mock.get("https://raw.githubusercontent.com/testco/testco/main/AGENTS.md").mock(
        return_value=httpx.Response(200, content=_AGENTS_MD.encode(), headers=text_ct)
    )
    mock.get("https://testco.example.com/.well-known/ai-plugin.json").mock(
        return_value=httpx.Response(200, json=_AI_PLUGIN, headers=json_ct)
    )
    mock.get("https://testco.example.com/robots.txt").mock(
        return_value=httpx.Response(200, content=_ROBOTS_TXT.encode(), headers=text_ct)
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_scan_target_returns_valid_report():
    """scan_target() with all HTTP calls mocked returns a well-formed Report."""
    target = _make_testco_target()

    with respx.mock(assert_all_called=False) as mock:
        _register_all_mocks(mock)
        report = await scan_target(target)

    assert report.slug == "testco"
    assert isinstance(report.overall_score, float)
    assert 0.0 <= report.overall_score <= 100.0
    assert len(report.dimensions) == 6
    assert isinstance(report.grade, (str, Grade))
    # grade value must be a valid Grade enum value
    Grade(report.grade)
    assert report.provenance is not None


async def test_scan_target_dimension_ids():
    """All 6 expected dimension IDs are present in the report."""
    target = _make_testco_target()
    expected_ids = {
        "openapi_quality",
        "docs_accessibility",
        "sdk_ergonomics",
        "error_ux",
        "auth_ergonomics",
        "discovery_surface",
    }

    with respx.mock(assert_all_called=False) as mock:
        _register_all_mocks(mock)
        report = await scan_target(target)

    actual_ids = {d.dimension_id for d in report.dimensions}
    assert actual_ids == expected_ids


async def test_write_report_creates_files(tmp_path):
    """write_report() creates .json and .md files that are readable."""
    target = _make_testco_target()

    with respx.mock(assert_all_called=False) as mock:
        _register_all_mocks(mock)
        report = await scan_target(target)

    json_path, md_path = write_report(report, str(tmp_path))

    json_file = Path(json_path)
    md_file = Path(md_path)

    assert json_file.exists(), f"JSON file not found: {json_path}"
    assert md_file.exists(), f"MD file not found: {md_path}"

    # JSON must parse back correctly
    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["slug"] == "testco"
    assert "overall_score" in data
    assert "dimensions" in data
    assert len(data["dimensions"]) == 6
    assert "provenance" in data

    # MD must mention the slug/name
    md_content = md_file.read_text(encoding="utf-8")
    assert "TestCo" in md_content
