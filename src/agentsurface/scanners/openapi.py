"""OpenAPI Quality scanner.

Measures discoverability, validity, and completeness of OpenAPI specs.
"""
from __future__ import annotations

import json
from urllib.parse import urlparse

import httpx
import yaml

from agentsurface import http
from agentsurface.framework import compute_dimension_score
from agentsurface.models import DimensionScore, SignalStatus
from agentsurface.scanners import register
from agentsurface.scanners.base import Scanner, Target, make_signal


def _parse_spec(content: str) -> dict | None:
    try:
        return json.loads(content)
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        result = yaml.safe_load(content)
        if isinstance(result, dict):
            return result
    except yaml.YAMLError:
        pass
    return None


def _looks_like_openapi(content: str) -> bool:
    return "openapi" in content or "swagger" in content or "paths" in content


@register
class OpenAPIScanner(Scanner):
    dimension_id = "openapi_quality"
    dimension_name = "OpenAPI Quality"
    weight = 0.20

    async def scan(
        self,
        target: Target,
        *,
        fetch_records: list,
        test_mode: bool = False,
    ) -> DimensionScore:
        signals = []
        spec_content: str | None = None
        spec_url: str | None = None

        # Signal 1: openapi.spec_discoverable
        # Track whether openapi_url was explicitly provided to distinguish FAIL vs SKIP below
        had_explicit_url = target.openapi_url is not None

        if target.openapi_url:
            try:
                resp = await http.fetch(target.openapi_url, record_list=fetch_records)
                if resp.status_code == 200 and _looks_like_openapi(resp.text):
                    spec_content = resp.text
                    spec_url = target.openapi_url
            except httpx.HTTPError:
                pass

        if spec_content is None and target.docs_url:
            parsed = urlparse(target.docs_url)
            base = f"{parsed.scheme}://{parsed.netloc}"
            probe_paths = [
                "/openapi.json",
                "/openapi.yaml",
                "/swagger.json",
                "/api/openapi.json",
                "/api/swagger.json",
            ]
            for path in probe_paths:
                try:
                    url = base + path
                    resp = await http.fetch(url, record_list=fetch_records)
                    if resp.status_code == 200 and _looks_like_openapi(resp.text):
                        spec_content = resp.text
                        spec_url = url
                        break
                except httpx.HTTPError:
                    continue

        if spec_content is not None:
            signals.append(make_signal(
                id="openapi.spec_discoverable", label="Spec Discoverable",
                weight=0.20, status=SignalStatus.PASS,
                evidence_url=spec_url,
            ))
        elif had_explicit_url:
            # We tried the explicit URL and well-known paths — it's a definitive FAIL
            signals.append(make_signal(
                id="openapi.spec_discoverable", label="Spec Discoverable",
                weight=0.20, status=SignalStatus.FAIL,
                notes="No OpenAPI spec found at configured URL or well-known paths",
            ))
        else:
            # No explicit openapi_url was configured; well-known discovery found nothing
            signals.append(make_signal(
                id="openapi.spec_discoverable", label="Spec Discoverable",
                weight=0.20, status=SignalStatus.FAIL,
                notes="No OpenAPI spec found at well-known discovery paths",
            ))

        # Parse spec once
        spec: dict | None = None
        if spec_content is not None:
            spec = _parse_spec(spec_content)

        # Signal 2: openapi.valid_oas3
        if spec is None:
            signals.append(make_signal(
                id="openapi.valid_oas3", label="Valid OAS 3.x",
                weight=0.20, status=SignalStatus.FAIL,
                notes="No spec to parse" if spec_content is None else "Failed to parse spec",
            ))
        elif isinstance(spec.get("openapi"), str) and spec["openapi"].startswith("3."):
            signals.append(make_signal(
                id="openapi.valid_oas3", label="Valid OAS 3.x",
                weight=0.20, status=SignalStatus.PASS,
                evidence_url=spec_url,
            ))
        elif "swagger" in spec:
            signals.append(make_signal(
                id="openapi.valid_oas3", label="Valid OAS 3.x",
                weight=0.20, status=SignalStatus.PARTIAL,
                notes=f"Swagger 2.x spec found (swagger: {spec.get('swagger')})",
            ))
        else:
            signals.append(make_signal(
                id="openapi.valid_oas3", label="Valid OAS 3.x",
                weight=0.20, status=SignalStatus.FAIL,
                notes="Spec lacks openapi/swagger version key",
            ))

        # Signal 3: openapi.has_servers
        if spec is None:
            signals.append(make_signal(
                id="openapi.has_servers", label="Has Servers Array",
                weight=0.15, status=SignalStatus.SKIP,
                notes="No spec available",
            ))
        else:
            servers = spec.get("servers", [])
            if isinstance(servers, list) and any(
                isinstance(s, dict) and s.get("url") for s in servers
            ):
                signals.append(make_signal(
                    id="openapi.has_servers", label="Has Servers Array",
                    weight=0.15, status=SignalStatus.PASS,
                    evidence_url=spec_url,
                ))
            else:
                signals.append(make_signal(
                    id="openapi.has_servers", label="Has Servers Array",
                    weight=0.15, status=SignalStatus.FAIL,
                    notes="No servers array or no entry with url",
                ))

        # Signal 4: openapi.auth_in_security_schemes
        if spec is None:
            signals.append(make_signal(
                id="openapi.auth_in_security_schemes", label="Auth in Security Schemes",
                weight=0.20, status=SignalStatus.SKIP,
                notes="No spec available",
            ))
        else:
            schemes = spec.get("components", {}).get("securitySchemes", {})
            if isinstance(schemes, dict) and len(schemes) > 0:
                signals.append(make_signal(
                    id="openapi.auth_in_security_schemes", label="Auth in Security Schemes",
                    weight=0.20, status=SignalStatus.PASS,
                    evidence_url=spec_url,
                ))
            else:
                signals.append(make_signal(
                    id="openapi.auth_in_security_schemes", label="Auth in Security Schemes",
                    weight=0.20, status=SignalStatus.FAIL,
                    notes="No securitySchemes found in components",
                ))

        # Collect operations once for signals 5 and 6
        operations: list[dict] = []
        if spec is not None:
            paths = spec.get("paths", {})
            if isinstance(paths, dict):
                http_methods = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
                for path_item in paths.values():
                    if not isinstance(path_item, dict):
                        continue
                    for method, op in path_item.items():
                        if method.lower() in http_methods and isinstance(op, dict):
                            operations.append(op)

        # Signal 5: openapi.error_response_schemas
        if spec is None:
            signals.append(make_signal(
                id="openapi.error_response_schemas", label="Error Response Schemas",
                weight=0.15, status=SignalStatus.SKIP,
                notes="No spec available",
            ))
        else:
            sampled = operations[:10]
            if not sampled:
                signals.append(make_signal(
                    id="openapi.error_response_schemas", label="Error Response Schemas",
                    weight=0.15, status=SignalStatus.FAIL,
                    notes="No operations found in spec",
                ))
            else:
                count = 0
                for op in sampled:
                    responses = op.get("responses", {})
                    has_error = any(
                        str(code).startswith(("4", "5")) and
                        isinstance(resp_obj, dict) and resp_obj.get("content")
                        for code, resp_obj in responses.items()
                    )
                    if has_error:
                        count += 1
                ratio = count / len(sampled)
                if ratio >= 0.50:
                    status = SignalStatus.PASS
                elif ratio >= 0.25:
                    status = SignalStatus.PARTIAL
                else:
                    status = SignalStatus.FAIL
                signals.append(make_signal(
                    id="openapi.error_response_schemas", label="Error Response Schemas",
                    weight=0.15, status=status,
                    notes=f"{count}/{len(sampled)} ops have error response schemas",
                ))

        # Signal 6: openapi.example_coverage
        if spec is None:
            signals.append(make_signal(
                id="openapi.example_coverage", label="Example Coverage",
                weight=0.10, status=SignalStatus.SKIP,
                notes="No spec available",
            ))
        else:
            sampled = operations[:20]
            if not sampled:
                signals.append(make_signal(
                    id="openapi.example_coverage", label="Example Coverage",
                    weight=0.10, status=SignalStatus.FAIL,
                    notes="No operations found in spec",
                ))
            else:
                count = 0
                for op in sampled:
                    has_example = False
                    # Check requestBody
                    req_body = op.get("requestBody", {})
                    if isinstance(req_body, dict):
                        for media in req_body.get("content", {}).values():
                            if isinstance(media, dict) and (
                                media.get("example") is not None or media.get("examples")
                            ):
                                has_example = True
                                break
                    # Check parameters
                    if not has_example:
                        for param in op.get("parameters", []):
                            if isinstance(param, dict) and (
                                param.get("example") is not None or param.get("examples")
                            ):
                                has_example = True
                                break
                    if has_example:
                        count += 1
                ratio = count / len(sampled)
                if ratio >= 0.50:
                    status = SignalStatus.PASS
                elif ratio >= 0.25:
                    status = SignalStatus.PARTIAL
                else:
                    status = SignalStatus.FAIL
                signals.append(make_signal(
                    id="openapi.example_coverage", label="Example Coverage",
                    weight=0.10, status=status,
                    notes=f"{count}/{len(sampled)} ops have examples",
                ))

        # Signal 7: openapi.operation_ids_present
        if spec is None:
            signals.append(make_signal(
                id="openapi.operation_ids_present", label="Operation IDs Present",
                weight=0.10, status=SignalStatus.SKIP,
                notes="No spec available",
            ))
        else:
            if not operations:
                signals.append(make_signal(
                    id="openapi.operation_ids_present", label="Operation IDs Present",
                    weight=0.10, status=SignalStatus.FAIL,
                    notes="No operations found in spec",
                ))
            else:
                with_id = sum(1 for op in operations if op.get("operationId", "").strip())
                ratio = with_id / len(operations)
                if ratio >= 0.80:
                    status = SignalStatus.PASS
                elif ratio >= 0.50:
                    status = SignalStatus.PARTIAL
                else:
                    status = SignalStatus.FAIL
                signals.append(make_signal(
                    id="openapi.operation_ids_present", label="Operation IDs Present",
                    weight=0.10, status=status,
                    evidence_url=spec_url if status == SignalStatus.PASS else None,
                    notes=f"{with_id}/{len(operations)} operations have operationId",
                ))

        # Signal 8: openapi.response_descriptions
        if spec is None:
            signals.append(make_signal(
                id="openapi.response_descriptions", label="Response Descriptions",
                weight=0.10, status=SignalStatus.SKIP,
                notes="No spec available",
            ))
        else:
            all_responses: list[dict] = []
            for op in operations:
                for resp_obj in op.get("responses", {}).values():
                    if isinstance(resp_obj, dict):
                        all_responses.append(resp_obj)
            if not all_responses:
                signals.append(make_signal(
                    id="openapi.response_descriptions", label="Response Descriptions",
                    weight=0.10, status=SignalStatus.FAIL,
                    notes="No response objects found in spec",
                ))
            else:
                with_desc = sum(
                    1 for r in all_responses
                    if isinstance(r.get("description"), str) and r["description"].strip()
                )
                ratio = with_desc / len(all_responses)
                if ratio >= 0.80:
                    status = SignalStatus.PASS
                elif ratio >= 0.50:
                    status = SignalStatus.PARTIAL
                else:
                    status = SignalStatus.FAIL
                signals.append(make_signal(
                    id="openapi.response_descriptions", label="Response Descriptions",
                    weight=0.10, status=status,
                    evidence_url=spec_url if status == SignalStatus.PASS else None,
                    notes=f"{with_desc}/{len(all_responses)} responses have description",
                ))

        score = compute_dimension_score(signals)
        return self._make_dimension_score(signals, score)
