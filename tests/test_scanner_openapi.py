"""Tests for OpenAPIScanner (TASK-026)."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from agentsurface.scanners.base import Target
from agentsurface.scanners.openapi import OpenAPIScanner

FIXTURES = Path(__file__).parent / "fixtures" / "openapi"

pytestmark = pytest.mark.asyncio


@pytest.fixture
def pass_spec():
    return (FIXTURES / "spec_pass.json").read_bytes()


@pytest.fixture
def swagger2_spec():
    return (FIXTURES / "spec_swagger2.json").read_bytes()


@respx.mock
async def test_openapi_pass(pass_spec):
    target = Target(
        slug="testapi",
        name="Test API",
        category="test",
        homepage="https://testapi.example.com",
        docs_url="https://docs.testapi.example.com",
        openapi_url="https://docs.testapi.example.com/openapi.json",
    )
    respx.get("https://docs.testapi.example.com/openapi.json").mock(
        return_value=httpx.Response(
            200,
            content=pass_spec,
            headers={"content-type": "application/json"},
        )
    )

    result = await OpenAPIScanner().scan(target, fetch_records=[])

    assert result.dimension_id == "openapi_quality"

    signals = {s.id: s for s in result.signals}
    assert signals["openapi.spec_discoverable"].status == "pass"
    assert signals["openapi.valid_oas3"].status == "pass"
    assert signals["openapi.has_servers"].status == "pass"
    assert signals["openapi.auth_in_security_schemes"].status == "pass"
    assert result.score > 50.0


@respx.mock
async def test_openapi_no_spec():
    target = Target(
        slug="testapi",
        name="Test API",
        category="test",
        homepage="https://testapi.example.com",
        docs_url="https://docs.testapi.example.com",
    )
    probe_base = "https://docs.testapi.example.com"
    probe_paths = [
        "/openapi.json", "/openapi.yaml", "/swagger.json", "/api/openapi.json", "/api/swagger.json",
    ]
    for path in probe_paths:
        respx.get(probe_base + path).mock(return_value=httpx.Response(404))

    result = await OpenAPIScanner().scan(target, fetch_records=[])

    signals = {s.id: s for s in result.signals}
    assert signals["openapi.spec_discoverable"].status == "fail"
    assert signals["openapi.valid_oas3"].status == "fail"
    assert signals["openapi.has_servers"].status == "skip"
    assert signals["openapi.auth_in_security_schemes"].status == "skip"
    assert signals["openapi.error_response_schemas"].status == "skip"
    assert signals["openapi.example_coverage"].status == "skip"
    assert result.score == 0.0


@respx.mock
async def test_openapi_swagger2(swagger2_spec):
    target = Target(
        slug="testapi",
        name="Test API",
        category="test",
        homepage="https://testapi.example.com",
        docs_url="https://docs.testapi.example.com",
        openapi_url="https://docs.testapi.example.com/openapi.json",
    )
    respx.get("https://docs.testapi.example.com/openapi.json").mock(
        return_value=httpx.Response(
            200,
            content=swagger2_spec,
            headers={"content-type": "application/json"},
        )
    )

    result = await OpenAPIScanner().scan(target, fetch_records=[])

    signals = {s.id: s for s in result.signals}
    assert signals["openapi.spec_discoverable"].status == "pass"
    assert signals["openapi.valid_oas3"].status == "partial"
