"""ErrorsScanner: measures error response quality by probing the API with bad requests.

Checks whether error responses are JSON, contain machine-readable codes, link to docs,
name offending fields, and use correct HTTP status codes.
"""
from __future__ import annotations

import re

import httpx

from agentsurface import http
from agentsurface.framework import compute_dimension_score
from agentsurface.models import DimensionScore, SignalStatus
from agentsurface.scanners import register
from agentsurface.scanners.base import Scanner, Target, make_signal


def _derive_api_base(target: Target) -> str | None:
    """Derive an API base URL from homepage or docs_url."""
    for url in (target.homepage, target.docs_url):
        if url:
            # Strip path and use root
            match = re.match(r"(https?://[^/]+)", url)
            if match:
                return match.group(1)
    return None


def _get_probe_url(target: Target) -> str | None:
    """Return the best probe URL for this target."""
    if target.error_probes:
        return target.error_probes[0]

    # Prefer explicit api_base_url over heuristic derivation from homepage/docs_url
    if target.api_base_url:
        base = target.api_base_url.rstrip("/")
        return f"{base}/v1/nonexistent_endpoint_xxxxxx"

    # Heuristic fallback: derive from homepage or docs_url (may hit marketing domain)
    base = _derive_api_base(target)
    if base:
        return f"{base}/v1/nonexistent_endpoint_xxxxxx"

    return None


def _find_machine_code(body: dict) -> bool:
    """Check for a stable machine-readable error code string in the response body."""
    code_keys = ["code", "error_code", "type", "status"]
    for key in code_keys:
        val = body.get(key)
        if isinstance(val, str) and not val.isdigit():
            return True

    # error.type nested
    error_obj = body.get("error")
    if isinstance(error_obj, dict):
        val = error_obj.get("type") or error_obj.get("code")
        if isinstance(val, str) and not val.isdigit():
            return True

    return False


def _find_docs_url(body: dict) -> bool:
    """Check if the error response includes a documentation URL."""
    doc_keys = ["doc_url", "docs_url", "documentation_url", "more_info", "help_url"]
    for key in doc_keys:
        val = body.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return True

    # Any string value that looks like a URL
    for val in body.values():
        if isinstance(val, str) and val.startswith("http"):
            return True

    return False


def _find_field_context(body: dict) -> bool:
    """Check if a validation error response names the offending field."""
    field_keys = ["param", "field", "path", "location"]
    for key in field_keys:
        if key in body and body[key]:
            return True

    errors = body.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            for key in field_keys:
                if key in first:
                    return True

    return False


@register
class ErrorsScanner(Scanner):
    dimension_id = "error_ux"
    dimension_name = "Error UX"
    weight = 0.15

    async def scan(
        self,
        target: Target,
        *,
        fetch_records: list,
        test_mode: bool = False,
    ) -> DimensionScore:
        signals = []
        probe_url = _get_probe_url(target)

        if not probe_url:
            # No probe available — SKIP everything
            for sig_id, label, w in [
                ("errors.json_response", "JSON Error Response", 0.25),
                ("errors.machine_code", "Machine-Readable Error Code", 0.25),
                ("errors.docs_url", "Error Docs URL", 0.20),
                ("errors.names_offending_field", "Names Offending Field", 0.15),
                ("errors.correct_status_code", "Correct Status Code", 0.15),
                ("errors.request_id_in_response", "Request ID in Response", 0.15),
                ("errors.4xx_5xx_distinction", "4xx vs 5xx Distinction", 0.10),
            ]:
                signals.append(make_signal(
                    id=sig_id, label=label, weight=w,
                    status=SignalStatus.SKIP, notes="No probe URL available",
                ))
            score = compute_dimension_score(signals)
            return self._make_dimension_score(signals, score)

        resp = None
        body_json: dict | None = None
        fetch_error: str | None = None

        try:
            resp = await http.fetch(
                probe_url,
                headers={"Accept": "application/json"},
                record_list=fetch_records,
            )
        except httpx.HTTPError as exc:
            fetch_error = str(exc)

        if fetch_error or resp is None:
            note = fetch_error or "No response"
            for sig_id, label, w in [
                ("errors.json_response", "JSON Error Response", 0.25),
                ("errors.machine_code", "Machine-Readable Error Code", 0.25),
                ("errors.docs_url", "Error Docs URL", 0.20),
                ("errors.names_offending_field", "Names Offending Field", 0.15),
                ("errors.correct_status_code", "Correct Status Code", 0.15),
                ("errors.request_id_in_response", "Request ID in Response", 0.15),
                ("errors.4xx_5xx_distinction", "4xx vs 5xx Distinction", 0.10),
            ]:
                signals.append(make_signal(
                    id=sig_id, label=label, weight=w,
                    status=SignalStatus.SKIP, notes=note,
                ))
            score = compute_dimension_score(signals)
            return self._make_dimension_score(signals, score)

        # Parse body
        content_type = resp.headers.get("content-type", "")
        is_json_ct = "json" in content_type
        try:
            parsed = resp.json()
            if isinstance(parsed, dict):
                body_json = parsed
            body_parses = True
        except Exception:
            body_parses = False

        # Signal 1: errors.json_response
        if is_json_ct and body_parses and body_json is not None:
            signals.append(make_signal(
                id="errors.json_response", label="JSON Error Response",
                weight=0.25, status=SignalStatus.PASS,
                evidence_url=probe_url,
            ))
        elif body_parses and body_json is not None:
            signals.append(make_signal(
                id="errors.json_response", label="JSON Error Response",
                weight=0.25, status=SignalStatus.PARTIAL,
                notes="Body is JSON but Content-Type does not indicate json",
                evidence_url=probe_url,
            ))
        else:
            signals.append(make_signal(
                id="errors.json_response", label="JSON Error Response",
                weight=0.25, status=SignalStatus.FAIL,
                notes=f"Non-JSON response (Content-Type: {content_type})",
                evidence_url=probe_url,
            ))

        # Signal 2: errors.machine_code
        if body_json is None:
            signals.append(make_signal(
                id="errors.machine_code", label="Machine-Readable Error Code",
                weight=0.25, status=SignalStatus.SKIP,
                notes="No JSON response body",
            ))
        elif _find_machine_code(body_json):
            signals.append(make_signal(
                id="errors.machine_code", label="Machine-Readable Error Code",
                weight=0.25, status=SignalStatus.PASS,
                evidence_url=probe_url,
            ))
        else:
            signals.append(make_signal(
                id="errors.machine_code", label="Machine-Readable Error Code",
                weight=0.25, status=SignalStatus.FAIL,
                notes="No machine-readable error code found in response",
            ))

        # Signal 3: errors.docs_url
        if body_json is None:
            signals.append(make_signal(
                id="errors.docs_url", label="Error Docs URL",
                weight=0.20, status=SignalStatus.SKIP,
                notes="No JSON response body",
            ))
        elif _find_docs_url(body_json):
            signals.append(make_signal(
                id="errors.docs_url", label="Error Docs URL",
                weight=0.20, status=SignalStatus.PASS,
                evidence_url=probe_url,
            ))
        else:
            signals.append(make_signal(
                id="errors.docs_url", label="Error Docs URL",
                weight=0.20, status=SignalStatus.FAIL,
                notes="No documentation URL found in error response",
            ))

        # Signal 4: errors.names_offending_field
        status_code = resp.status_code
        if body_json is None:
            signals.append(make_signal(
                id="errors.names_offending_field", label="Names Offending Field",
                weight=0.15, status=SignalStatus.SKIP,
                notes="No JSON response body",
            ))
        elif not (400 <= status_code < 500):
            signals.append(make_signal(
                id="errors.names_offending_field", label="Names Offending Field",
                weight=0.15, status=SignalStatus.SKIP,
                notes=f"Status {status_code} is not in 400-range",
            ))
        elif _find_field_context(body_json):
            signals.append(make_signal(
                id="errors.names_offending_field", label="Names Offending Field",
                weight=0.15, status=SignalStatus.PASS,
                evidence_url=probe_url,
            ))
        elif status_code == 400:
            signals.append(make_signal(
                id="errors.names_offending_field", label="Names Offending Field",
                weight=0.15, status=SignalStatus.PARTIAL,
                notes="400 response but no offending field named",
            ))
        else:
            signals.append(make_signal(
                id="errors.names_offending_field", label="Names Offending Field",
                weight=0.15, status=SignalStatus.FAIL,
                notes="No field context in error response",
            ))

        # Signal 5: errors.correct_status_code
        if status_code in range(400, 500):
            signals.append(make_signal(
                id="errors.correct_status_code", label="Correct Status Code",
                weight=0.15, status=SignalStatus.PASS,
                evidence_url=probe_url,
                notes=f"HTTP {status_code}",
            ))
        elif status_code == 200:
            signals.append(make_signal(
                id="errors.correct_status_code", label="Correct Status Code",
                weight=0.15, status=SignalStatus.FAIL,
                notes="200 OK returned for what should be a client error",
            ))
        elif status_code >= 500:
            signals.append(make_signal(
                id="errors.correct_status_code", label="Correct Status Code",
                weight=0.15, status=SignalStatus.FAIL,
                notes=f"Server error {status_code} returned for client probe",
            ))
        else:
            signals.append(make_signal(
                id="errors.correct_status_code", label="Correct Status Code",
                weight=0.15, status=SignalStatus.FAIL,
                notes=f"Unexpected status code {status_code}",
            ))

        # Signal 6: errors.request_id_in_response
        request_id_keys = {
            "request_id", "requestId", "trace_id", "traceId",
            "x-request-id", "correlation_id",
        }
        if body_json is None:
            signals.append(make_signal(
                id="errors.request_id_in_response", label="Request ID in Response",
                weight=0.15, status=SignalStatus.SKIP,
                notes="No JSON response body",
            ))
        else:
            # Also check headers
            header_keys = {k.lower() for k in resp.headers.keys()}
            body_keys = {k.lower() for k in body_json.keys()}
            # Check nested error object too
            error_obj = body_json.get("error")
            if isinstance(error_obj, dict):
                body_keys |= {k.lower() for k in error_obj.keys()}
            found_request_id = bool(request_id_keys & (body_keys | header_keys))
            if found_request_id:
                signals.append(make_signal(
                    id="errors.request_id_in_response", label="Request ID in Response",
                    weight=0.15, status=SignalStatus.PASS,
                    evidence_url=probe_url,
                    notes="Correlation/request ID found in response",
                ))
            else:
                signals.append(make_signal(
                    id="errors.request_id_in_response", label="Request ID in Response",
                    weight=0.15, status=SignalStatus.FAIL,
                    notes="No request_id/trace_id/correlation_id in response body or headers",
                ))

        # Signal 7: errors.4xx_5xx_distinction
        content_type_lower = content_type.lower()
        is_html = "html" in content_type_lower
        if is_html and not body_parses:
            signals.append(make_signal(
                id="errors.4xx_5xx_distinction", label="4xx vs 5xx Distinction",
                weight=0.10, status=SignalStatus.SKIP,
                notes="Response is HTML (marketing site), cannot determine error classification",
            ))
        elif status_code == 404:
            signals.append(make_signal(
                id="errors.4xx_5xx_distinction", label="4xx vs 5xx Distinction",
                weight=0.10, status=SignalStatus.PASS,
                evidence_url=probe_url,
                notes="HTTP 404 returned for nonexistent resource (correct)",
            ))
        else:
            signals.append(make_signal(
                id="errors.4xx_5xx_distinction", label="4xx vs 5xx Distinction",
                weight=0.10, status=SignalStatus.FAIL,
                notes=f"Expected HTTP 404 for missing resource probe, got {status_code}",
            ))

        score = compute_dimension_score(signals)
        return self._make_dimension_score(signals, score)
