"""Auth Ergonomics scanner — measures how well an API documents and implements
authentication for automated/agent use, including programmatic key issuance,
OpenAPI security scheme definitions, and scope enumerability."""

from __future__ import annotations

import json

import httpx

from agentsurface import http
from agentsurface.framework import compute_dimension_score
from agentsurface.models import DimensionScore, SignalStatus
from agentsurface.scanners import register
from agentsurface.scanners.base import Scanner, Target, make_signal


@register
class AuthScanner(Scanner):
    dimension_id = "auth_ergonomics"
    dimension_name = "Auth Ergonomics"
    weight = 0.15

    async def scan(
        self,
        target: Target,
        *,
        fetch_records: list,
        test_mode: bool = False,
    ) -> DimensionScore:
        signals = []

        # ── Signal 1: auth.programmatic_key_issuance ──────────────────────────
        programmatic_keywords = {
            "api key", "service account", "programmatic", "machine",
            "automated", "non-interactive",
        }
        dashboard_keywords = {"console", "dashboard", "portal"}

        docs_text = ""
        home_text = ""

        if target.docs_url:
            try:
                resp = await http.fetch(target.docs_url, record_list=fetch_records)
                if resp.status_code == 200:
                    docs_text = resp.text.lower()
            except httpx.HTTPError:
                pass

        try:
            resp = await http.fetch(target.homepage, record_list=fetch_records)
            if resp.status_code == 200:
                home_text = resp.text.lower()
        except httpx.HTTPError:
            pass

        combined_text = docs_text + " " + home_text
        found_programmatic = [kw for kw in programmatic_keywords if kw in combined_text]
        found_dashboard = [kw for kw in dashboard_keywords if kw in combined_text]

        if found_programmatic:
            signals.append(make_signal(
                id="auth.programmatic_key_issuance",
                label="Programmatic Key Issuance",
                weight=0.35,
                status=SignalStatus.PASS,
                evidence_url=target.docs_url or target.homepage,
                notes=f"Found keywords: {', '.join(sorted(found_programmatic))}",
            ))
        elif found_dashboard:
            signals.append(make_signal(
                id="auth.programmatic_key_issuance",
                label="Programmatic Key Issuance",
                weight=0.35,
                status=SignalStatus.PARTIAL,
                evidence_url=target.docs_url or target.homepage,
                notes=(
                    f"Only dashboard-based key creation mentioned"
                    f" ({', '.join(sorted(found_dashboard))});"
                    f" no programmatic path documented"
                ),
            ))
        else:
            signals.append(make_signal(
                id="auth.programmatic_key_issuance",
                label="Programmatic Key Issuance",
                weight=0.35,
                status=SignalStatus.FAIL,
                notes="Auth method is entirely undocumented on public pages",
            ))

        # ── Signal 2: auth.security_schemes_defined ───────────────────────────
        VALID_SCHEME_TYPES = {"apikey", "http", "oauth2", "openidconnect"}

        if target.openapi_url is None:
            signals.append(make_signal(
                id="auth.security_schemes_defined",
                label="Security Schemes Defined",
                weight=0.35,
                status=SignalStatus.SKIP,
                notes="No OpenAPI URL provided",
            ))
        else:
            spec_text = ""
            spec_fetched = False
            try:
                resp = await http.fetch(target.openapi_url, record_list=fetch_records)
                if resp.status_code == 200:
                    spec_text = resp.text
                    spec_fetched = True
            except httpx.HTTPError as exc:
                signals.append(make_signal(
                    id="auth.security_schemes_defined",
                    label="Security Schemes Defined",
                    weight=0.35,
                    status=SignalStatus.SKIP,
                    notes=f"Could not fetch OpenAPI spec: {exc}",
                ))
                spec_fetched = False

            if spec_fetched:
                try:
                    spec = json.loads(spec_text)
                except Exception:
                    try:
                        import yaml  # type: ignore
                        spec = yaml.safe_load(spec_text)
                    except Exception:
                        spec = {}

                schemes = (
                    spec.get("components", {}).get("securitySchemes", {})
                    if isinstance(spec, dict) else {}
                )
                valid_schemes = [
                    name for name, defn in schemes.items()
                    if isinstance(defn, dict) and defn.get("type", "").lower() in VALID_SCHEME_TYPES
                ] if schemes else []

                if valid_schemes:
                    signals.append(make_signal(
                        id="auth.security_schemes_defined",
                        label="Security Schemes Defined",
                        weight=0.35,
                        status=SignalStatus.PASS,
                        evidence_url=target.openapi_url,
                        notes=f"Schemes: {', '.join(valid_schemes)}",
                    ))
                else:
                    # Check if security is mentioned in paths
                    paths = spec.get("paths", {}) if isinstance(spec, dict) else {}
                    path_has_security = any(
                        "security" in op
                        for path_item in paths.values() if isinstance(path_item, dict)
                        for op in path_item.values() if isinstance(op, dict)
                    )
                    if path_has_security:
                        signals.append(make_signal(
                            id="auth.security_schemes_defined",
                            label="Security Schemes Defined",
                            weight=0.35,
                            status=SignalStatus.PARTIAL,
                            evidence_url=target.openapi_url,
                            notes=(
                                "Security referenced in paths but no"
                                " securitySchemes defined in components"
                            ),
                        ))
                    else:
                        signals.append(make_signal(
                            id="auth.security_schemes_defined",
                            label="Security Schemes Defined",
                            weight=0.35,
                            status=SignalStatus.FAIL,
                            evidence_url=target.openapi_url,
                            notes="No securitySchemes found in OpenAPI spec",
                        ))

        # ── Signal 3: auth.scopes_enumerable ──────────────────────────────────
        scopes_evidence_url = None
        scopes_status = SignalStatus.FAIL
        scopes_notes = "No scope or permission information found"

        # Check OpenAPI spec for oauth2 scopes or x-scopes
        if target.openapi_url:
            spec_obj: dict = {}
            try:
                resp = await http.fetch(target.openapi_url, record_list=fetch_records)
                if resp.status_code == 200:
                    try:
                        spec_obj = json.loads(resp.text)
                    except Exception:
                        try:
                            import yaml  # type: ignore
                            spec_obj = yaml.safe_load(resp.text) or {}
                        except Exception:
                            spec_obj = {}
            except httpx.HTTPError:
                pass

            if isinstance(spec_obj, dict):
                schemes = spec_obj.get("components", {}).get("securitySchemes", {}) or {}
                has_oauth_scopes = False
                has_x_scopes = False
                for defn in schemes.values():
                    if not isinstance(defn, dict):
                        continue
                    scheme_type = defn.get("type", "").lower()
                    if scheme_type == "oauth2":
                        flows = defn.get("flows", {}) or {}
                        for flow in flows.values():
                            if isinstance(flow, dict) and flow.get("scopes"):
                                has_oauth_scopes = True
                    if "x-scopes" in defn:
                        has_x_scopes = True

                if has_oauth_scopes or has_x_scopes:
                    scopes_status = SignalStatus.PASS
                    scopes_evidence_url = target.openapi_url
                    scopes_notes = "Scopes explicitly listed in OpenAPI spec"
                else:
                    # Simple API key with no scopes — PARTIAL
                    api_key_schemes = [
                        d for d in schemes.values()
                        if isinstance(d, dict) and d.get("type", "").lower() == "apikey"
                    ]
                    if api_key_schemes:
                        scopes_status = SignalStatus.PARTIAL
                        scopes_evidence_url = target.openapi_url
                        scopes_notes = (
                            "API uses simple API keys without scopes;"
                            " scoped keys would improve agent security"
                        )

        # Also check docs text for scope/permission keywords
        if scopes_status == SignalStatus.FAIL and docs_text:
            scope_keywords = ["scopes", "permissions", "access levels", "access level"]
            found_scope_kws = [kw for kw in scope_keywords if kw in docs_text]
            if found_scope_kws:
                scopes_status = SignalStatus.PARTIAL
                scopes_evidence_url = target.docs_url
                scopes_notes = (
                    f"Scope/permission keywords found in docs"
                    f" ({', '.join(found_scope_kws)})"
                    f" but not explicitly enumerated"
                )

        signals.append(make_signal(
            id="auth.scopes_enumerable",
            label="Scopes Enumerable",
            weight=0.30,
            status=scopes_status,
            evidence_url=scopes_evidence_url,
            notes=scopes_notes,
        ))

        # ── Signal 4: auth.m2m_docs_discoverable ─────────────────────────────
        m2m_paths = [
            "/docs/service-accounts",
            "/docs/machine-to-machine",
            "/docs/m2m",
            "/docs/api-keys/service",
            "/docs/oauth/client-credentials",
        ]
        m2m_found = False
        m2m_url: str | None = None

        if target.docs_url is None:
            signals.append(make_signal(
                id="auth.m2m_docs_discoverable",
                label="M2M / Service Account Docs",
                weight=0.15,
                status=SignalStatus.SKIP,
                notes="No docs_url configured",
            ))
        else:
            from urllib.parse import urlparse as _urlparse
            docs_parsed = _urlparse(target.docs_url)
            docs_base_url = f"{docs_parsed.scheme}://{docs_parsed.netloc}"
            for path in m2m_paths:
                url = f"{docs_base_url}{path}"
                try:
                    resp = await http.fetch(url, record_list=fetch_records)
                    if resp.status_code == 200:
                        m2m_found = True
                        m2m_url = url
                        break
                except httpx.HTTPError:
                    pass
            signals.append(make_signal(
                id="auth.m2m_docs_discoverable",
                label="M2M / Service Account Docs",
                weight=0.15,
                status=SignalStatus.PASS if m2m_found else SignalStatus.FAIL,
                evidence_url=m2m_url,
                notes=(
                    f"Found at {m2m_url}" if m2m_found
                    else f"Probed {len(m2m_paths)} paths — none returned 200"
                ),
            ))

        # ── Signal 5: auth.webhook_signing_documented ─────────────────────────
        webhook_paths = ["/docs/webhooks", "/webhooks", "/docs/events"]
        webhook_signing_keywords = {"signing", "secret", "hmac"}
        webhook_found = False
        webhook_url: str | None = None

        if target.docs_url is None:
            signals.append(make_signal(
                id="auth.webhook_signing_documented",
                label="Webhook Signing Documented",
                weight=0.15,
                status=SignalStatus.SKIP,
                notes="No docs_url configured",
            ))
        else:
            from urllib.parse import urlparse as _urlparse2
            docs_parsed2 = _urlparse2(target.docs_url)
            docs_base_url2 = f"{docs_parsed2.scheme}://{docs_parsed2.netloc}"
            for path in webhook_paths:
                url = f"{docs_base_url2}{path}"
                try:
                    resp = await http.fetch(url, record_list=fetch_records)
                    if resp.status_code == 200:
                        body_lower = resp.text.lower()
                        if "webhook" in body_lower and any(
                            kw in body_lower for kw in webhook_signing_keywords
                        ):
                            webhook_found = True
                            webhook_url = url
                            break
                except httpx.HTTPError:
                    pass
            signals.append(make_signal(
                id="auth.webhook_signing_documented",
                label="Webhook Signing Documented",
                weight=0.15,
                status=SignalStatus.PASS if webhook_found else SignalStatus.FAIL,
                evidence_url=webhook_url,
                notes=(
                    f"Webhook signing docs found at {webhook_url}" if webhook_found
                    else "No webhook signing documentation found at probed paths"
                ),
            ))

        score = compute_dimension_score(signals)
        return self._make_dimension_score(signals, score)
