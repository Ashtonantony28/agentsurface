"""
Pytest configuration: network guard, shared fixtures, Target factory.

IMPORTANT: The no-network guard blocks all real socket connections in tests.
"""

import json
import socket
from pathlib import Path

import pytest


@pytest.fixture(autouse=True, scope="session")
def block_real_network():
    """Prevent any test from opening a real TCP/IP network socket.

    AF_UNIX sockets (used by asyncio's internal self-pipe) are allowed through.
    Only AF_INET and AF_INET6 sockets are blocked to prevent accidental live
    network calls.
    """
    original = socket.socket
    _AF_INET = socket.AF_INET
    _AF_INET6 = socket.AF_INET6

    def no_tcp_socket(family=socket.AF_INET, *args, **kwargs):
        if family in (_AF_INET, _AF_INET6):
            raise RuntimeError(
                "No real network sockets in tests — use respx fixtures. "
                f"Attempted: socket(family={family}, {args}, {kwargs})"
            )
        return original(family, *args, **kwargs)

    socket.socket = no_tcp_socket
    yield
    socket.socket = original


@pytest.fixture
def make_target():
    """Factory for creating test Target instances with sensible defaults."""
    from agentsurface.scanners.base import Target

    def _make(
        slug="testapi",
        name="Test API",
        category="devtools_observability",
        homepage="https://testapi.example.com",
        docs_url="https://docs.testapi.example.com",
        **kwargs,
    ):
        return Target(
            slug=slug,
            name=name,
            category=category,
            homepage=homepage,
            docs_url=docs_url,
            **kwargs,
        )

    return _make


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(scanner_name: str, fixture_name: str) -> bytes:
    """Load a recorded HTTP fixture from tests/fixtures/<scanner_name>/<fixture_name>."""
    path = FIXTURES_DIR / scanner_name / fixture_name
    return path.read_bytes()


def load_json_fixture(scanner_name: str, fixture_name: str) -> dict:
    """Load and parse a JSON fixture."""
    return json.loads(load_fixture(scanner_name, fixture_name))
