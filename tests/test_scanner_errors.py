"""Tests for ErrorsScanner (TASK-026)."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from agentsurface.scanners.base import Target
from agentsurface.scanners.errors import ErrorsScanner

FIXTURES = Path(__file__).parent / "fixtures" / "errors"

pytestmark = pytest.mark.asyncio


@respx.mock
async def test_errors_pass():
    """Perfect error response: all signals pass."""
    body = (FIXTURES / "error_pass.json").read_bytes()
    target = Target(
        slug="testapi",
        name="Test API",
        category="test",
        homepage="https://testapi.example.com",
        docs_url="https://docs.testapi.example.com",
        error_probes=["https://testapi.example.com/v1/customers/nonexistent_id_xxx"],
    )
    respx.get("https://testapi.example.com/v1/customers/nonexistent_id_xxx").mock(
        return_value=httpx.Response(
            404,
            content=body,
            headers={"content-type": "application/json"},
        )
    )

    result = await ErrorsScanner().scan(target, fetch_records=[])

    signals = {s.id: s for s in result.signals}
    assert signals["errors.json_response"].status == "pass"
    assert signals["errors.machine_code"].status == "pass"
    assert signals["errors.docs_url"].status == "pass"
    assert signals["errors.names_offending_field"].status == "pass"
    assert signals["errors.correct_status_code"].status == "pass"
    assert result.score > 70.0


@respx.mock
async def test_errors_poor_response():
    """Poor error: JSON with integer status, no docs URL, no field name."""
    body = (FIXTURES / "error_no_code.json").read_bytes()
    target = Target(
        slug="testapi",
        name="Test API",
        category="test",
        homepage="https://testapi.example.com",
        docs_url="https://docs.testapi.example.com",
        error_probes=["https://testapi.example.com/v1/customers/nonexistent_id_xxx"],
    )
    respx.get("https://testapi.example.com/v1/customers/nonexistent_id_xxx").mock(
        return_value=httpx.Response(
            404,
            content=body,
            headers={"content-type": "application/json"},
        )
    )

    result = await ErrorsScanner().scan(target, fetch_records=[])

    signals = {s.id: s for s in result.signals}
    assert signals["errors.json_response"].status == "pass"
    assert signals["errors.machine_code"].status == "fail"
    assert signals["errors.docs_url"].status == "fail"
    assert signals["errors.names_offending_field"].status == "fail"
    assert signals["errors.correct_status_code"].status == "pass"


@respx.mock
async def test_errors_no_probe():
    """No error_probes set; heuristic URL is unreachable — all signals skip."""
    target = Target(
        slug="testapi",
        name="Test API",
        category="test",
        homepage="https://testapi.example.com",
        docs_url="https://docs.testapi.example.com",
    )
    respx.get("https://testapi.example.com/v1/nonexistent_endpoint_xxxxxx").mock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    result = await ErrorsScanner().scan(target, fetch_records=[])

    signals = {s.id: s for s in result.signals}
    for sig_id in [
        "errors.json_response",
        "errors.machine_code",
        "errors.docs_url",
        "errors.names_offending_field",
        "errors.correct_status_code",
    ]:
        assert signals[sig_id].status == "skip", f"{sig_id} expected skip"
