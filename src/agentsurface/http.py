"""Shared HTTP client module for AgentSurface scanners.

User-Agent policy:
    All outbound requests identify as ``AgentSurface-Scanner/0.1`` so that API
    owners can recognise and, if desired, allowlist the scanner traffic.

Rate-limit policy (per-domain):
    - Maximum 4 concurrent requests.
    - Minimum 1-second gap between consecutive requests.

Retry policy:
    - HTTP 429 (Too Many Requests) and 503 (Service Unavailable) are retried up
      to 3 times with exponential back-off: 1 s, 2 s, 4 s.

All scanner code MUST import and call :func:`fetch` from this module.  Never
instantiate ``httpx.AsyncClient`` directly in scanner code.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_USER_AGENT = "AgentSurface-Scanner/0.1 (+https://github.com/your-org/agentsurface)"

_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)

_RETRY_STATUSES = {429, 503}
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0  # seconds

_MAX_CONCURRENT_PER_DOMAIN = 4
_MIN_INTERVAL_PER_DOMAIN = 1.0  # seconds

# ---------------------------------------------------------------------------
# Module-level per-domain rate-limit state
# ---------------------------------------------------------------------------

# Semaphore: at most 4 concurrent requests per domain.
_domain_semaphores: dict[str, asyncio.Semaphore] = defaultdict(
    lambda: asyncio.Semaphore(_MAX_CONCURRENT_PER_DOMAIN)
)

# Lock + last-request timestamp for 1 req/sec spacing.
_domain_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_domain_last_request: dict[str, float] = defaultdict(float)


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


@dataclass
class FetchRecord:
    """Records a single URL fetch for provenance tracking."""

    url: str
    fetched_at: str  # ISO-8601 UTC, e.g. "2026-05-30T12:34:56.789012Z"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def make_client(timeout: Optional[httpx.Timeout] = None) -> httpx.AsyncClient:
    """Return a configured :class:`httpx.AsyncClient`.

    The caller is responsible for managing the client lifecycle (``async with``
    or explicit ``.aclose()``).  Use this when you need to reuse a single
    client across many requests in a tight loop; for one-off fetches prefer
    :func:`fetch`.

    Args:
        timeout: Override the default timeout.  Defaults to the module-level
            ``_DEFAULT_TIMEOUT`` (connect=5 s, read=15 s, write=5 s, pool=5 s).

    Returns:
        A configured :class:`httpx.AsyncClient` instance.
    """
    return httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT},
        timeout=timeout or _DEFAULT_TIMEOUT,
        follow_redirects=True,
    )


async def fetch(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[dict[str, str]] = None,
    timeout: Optional[httpx.Timeout] = None,
    follow_redirects: bool = True,
    record_list: Optional[list[FetchRecord]] = None,
) -> httpx.Response:
    """Fetch *url* with retry, per-domain rate limiting, and provenance recording.

    Args:
        url: The URL to fetch.
        method: HTTP method (default ``"GET"``).
        headers: Extra request headers merged on top of the default User-Agent.
        timeout: Override the default timeout for this request.
        follow_redirects: Follow HTTP redirects (default ``True``).
        record_list: If provided, a :class:`FetchRecord` is appended for each
            successful (non-retried) response.

    Returns:
        The :class:`httpx.Response` from the last attempt.

    Raises:
        httpx.HTTPError: Propagated from httpx after all retries are exhausted.
    """
    domain = urlparse(url).netloc

    effective_timeout = timeout or _DEFAULT_TIMEOUT
    merged_headers = {"User-Agent": _USER_AGENT}
    if headers:
        merged_headers.update(headers)

    response: Optional[httpx.Response] = None

    for attempt in range(_MAX_RETRIES + 1):
        # --- per-domain rate limiting -----------------------------------------
        async with _domain_semaphores[domain]:
            async with _domain_locks[domain]:
                now = time.monotonic()
                elapsed = now - _domain_last_request[domain]
                if elapsed < _MIN_INTERVAL_PER_DOMAIN:
                    await asyncio.sleep(_MIN_INTERVAL_PER_DOMAIN - elapsed)
                _domain_last_request[domain] = time.monotonic()

            # Release the per-domain lock before the actual network call so
            # other coroutines can update the timestamp independently; the
            # semaphore still limits concurrency to 4.
            async with httpx.AsyncClient(
                headers=merged_headers,
                timeout=effective_timeout,
                follow_redirects=follow_redirects,
            ) as client:
                response = await client.request(method, url)

        # --- retry logic -------------------------------------------------------
        if response.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES:
            backoff = _BACKOFF_BASE * (2 ** attempt)
            await asyncio.sleep(backoff)
            continue

        # Success (or non-retryable status) — record provenance and return.
        if record_list is not None:
            record_list.append(
                FetchRecord(
                    url=url,
                    fetched_at=datetime.now(tz=timezone.utc).isoformat(),
                )
            )
        return response

    # Should be unreachable, but satisfy the type checker.
    assert response is not None
    return response
