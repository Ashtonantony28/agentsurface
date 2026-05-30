"""SDK Ergonomics scanner: measures availability, typing, and developer UX of official SDKs."""
from __future__ import annotations

import httpx

from agentsurface import http
from agentsurface.framework import compute_dimension_score
from agentsurface.models import DimensionScore, SignalStatus
from agentsurface.scanners import register
from agentsurface.scanners.base import Scanner, Target, make_signal


@register
class SDKScanner(Scanner):
    dimension_id = "sdk_ergonomics"
    dimension_name = "SDK Ergonomics"
    weight = 0.15

    async def scan(
        self,
        target: Target,
        *,
        fetch_records: list,
        test_mode: bool = False,
    ) -> DimensionScore:
        signals = []
        npm = target.npm_package
        pypi = target.pypi_package
        github_org = target.github_org

        # Cache npm/pypi registry responses for reuse in typed signal
        npm_data: dict | None = None
        pypi_data: dict | None = None
        readme_content: str | None = None

        # --- Signal 1: sdk.npm_package ---
        if npm is None:
            signals.append(make_signal(
                id="sdk.npm_package", label="Official npm package exists",
                weight=0.25, status=SignalStatus.SKIP,
            ))
        else:
            try:
                resp = await http.fetch(
                    f"https://registry.npmjs.org/{npm}",
                    record_list=fetch_records,
                )
                if resp.status_code == 200:
                    try:
                        npm_data = resp.json()
                    except Exception:
                        npm_data = {}
                    if isinstance(npm_data, dict) and "name" in npm_data:
                        signals.append(make_signal(
                            id="sdk.npm_package", label="Official npm package exists",
                            weight=0.25, status=SignalStatus.PASS,
                            evidence_url=f"https://www.npmjs.com/package/{npm}",
                        ))
                    else:
                        signals.append(make_signal(
                            id="sdk.npm_package", label="Official npm package exists",
                            weight=0.25, status=SignalStatus.FAIL,
                            notes="Response missing 'name' field",
                        ))
                else:
                    signals.append(make_signal(
                        id="sdk.npm_package", label="Official npm package exists",
                        weight=0.25, status=SignalStatus.FAIL,
                        notes=f"HTTP {resp.status_code}",
                    ))
            except httpx.HTTPError as exc:
                signals.append(make_signal(
                    id="sdk.npm_package", label="Official npm package exists",
                    weight=0.25, status=SignalStatus.FAIL,
                    notes=str(exc),
                ))

        # --- Signal 2: sdk.pypi_package ---
        if pypi is None:
            signals.append(make_signal(
                id="sdk.pypi_package", label="Official PyPI package exists",
                weight=0.25, status=SignalStatus.SKIP,
            ))
        else:
            try:
                resp = await http.fetch(
                    f"https://pypi.org/pypi/{pypi}/json",
                    record_list=fetch_records,
                )
                if resp.status_code == 200:
                    try:
                        pypi_data = resp.json()
                    except Exception:
                        pypi_data = {}
                    signals.append(make_signal(
                        id="sdk.pypi_package", label="Official PyPI package exists",
                        weight=0.25, status=SignalStatus.PASS,
                        evidence_url=f"https://pypi.org/project/{pypi}/",
                    ))
                else:
                    signals.append(make_signal(
                        id="sdk.pypi_package", label="Official PyPI package exists",
                        weight=0.25, status=SignalStatus.FAIL,
                        notes=f"HTTP {resp.status_code}",
                    ))
            except httpx.HTTPError as exc:
                signals.append(make_signal(
                    id="sdk.pypi_package", label="Official PyPI package exists",
                    weight=0.25, status=SignalStatus.FAIL,
                    notes=str(exc),
                ))

        # --- Signal 3: sdk.readme_install_oneliner ---
        # Cover all common package manager install commands
        install_patterns = [
            "npm install",
            "npm i ",
            "pip install",
            "yarn add",
            "uv add",
            "uv pip install",
            "npx ",
            "pnpm add",
            "pnpm install",
            "bun add",
            "bun install",
            "cargo add",
            "go get",
        ]
        readme_fetched = False
        readme_fetch_error: str | None = None

        if github_org and (npm or pypi):
            repo_name = npm or pypi
            readme_url: str | None = None
            # Use HEAD ref to work for any default branch (main, master, trunk, etc.)
            url = f"https://raw.githubusercontent.com/{github_org}/{repo_name}/HEAD/README.md"
            try:
                resp = await http.fetch(url, record_list=fetch_records)
                if resp.status_code == 200:
                    readme_content = resp.text
                    readme_url = url
                    readme_fetched = True
                else:
                    readme_fetch_error = f"HTTP {resp.status_code} from {url}"
            except httpx.HTTPError as exc:
                readme_fetch_error = str(exc)

            if readme_fetched and readme_content is not None:
                first_20 = readme_content.splitlines()[:20]
                found_install = any(
                    pattern in line
                    for line in first_20
                    for pattern in install_patterns
                )
                if found_install:
                    signals.append(make_signal(
                        id="sdk.readme_install_oneliner",
                        label="README has install command in first 20 lines",
                        weight=0.20, status=SignalStatus.PASS,
                        evidence_url=readme_url,
                    ))
                else:
                    signals.append(make_signal(
                        id="sdk.readme_install_oneliner",
                        label="README has install command in first 20 lines",
                        weight=0.20, status=SignalStatus.FAIL,
                        notes="No install pattern found in first 20 lines",
                    ))
            else:
                # Fetch failed — mark FAIL with error details
                signals.append(make_signal(
                    id="sdk.readme_install_oneliner",
                    label="README has install command in first 20 lines",
                    weight=0.20, status=SignalStatus.FAIL,
                    notes=readme_fetch_error or "README fetch failed",
                ))
        else:
            signals.append(make_signal(
                id="sdk.readme_install_oneliner",
                label="README has install command in first 20 lines",
                weight=0.20, status=SignalStatus.SKIP,
                notes="No github_org configured",
            ))

        # --- Signal 4: sdk.typed ---
        if npm is None and pypi is None:
            signals.append(make_signal(
                id="sdk.typed", label="SDK is typed",
                weight=0.15, status=SignalStatus.SKIP,
                notes="No npm or pypi package configured",
            ))
        else:
            typed_status = SignalStatus.FAIL
            typed_notes: str | None = None

            # Check npm typing
            if npm is not None:
                data = npm_data
                if data is None:
                    # Fetch if not already fetched
                    try:
                        resp = await http.fetch(
                            f"https://registry.npmjs.org/{npm}",
                            record_list=fetch_records,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                    except httpx.HTTPError:
                        data = {}

                if data:
                    latest_tag = (data.get("dist-tags") or {}).get("latest")
                    versions = data.get("versions") or {}
                    latest_version = versions.get(latest_tag, {}) if latest_tag else {}
                    if "types" in latest_version or "typings" in latest_version:
                        typed_status = SignalStatus.PASS
                    else:
                        typed_notes = "No 'types' or 'typings' in latest version"

            # Check pypi typing (may override or complement npm result)
            if pypi is not None and typed_status != SignalStatus.PASS:
                data = pypi_data
                if data is None:
                    try:
                        resp = await http.fetch(
                            f"https://pypi.org/pypi/{pypi}/json",
                            record_list=fetch_records,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                    except httpx.HTTPError:
                        data = {}

                if data:
                    classifiers = (data.get("info") or {}).get("classifiers") or []
                    provides_extra = (data.get("info") or {}).get("provides_extra") or []
                    classifier_str = " ".join(classifiers)
                    if "Typing :: Typed" in classifier_str or "py.typed" in classifier_str:
                        typed_status = SignalStatus.PASS
                    elif any(
                        "typing" in str(e).lower() or "stubs" in str(e).lower()
                        for e in provides_extra
                    ):
                        typed_status = SignalStatus.PARTIAL
                        typed_notes = "Typing stubs available separately"
                    else:
                        typed_notes = typed_notes or "No typing information found in classifiers"

            signals.append(make_signal(
                id="sdk.typed", label="SDK is typed",
                weight=0.15, status=typed_status,
                notes=typed_notes,
            ))

        # --- Signal 5: sdk.readme_quickstart_length ---
        if not readme_fetched:
            if github_org and (npm or pypi):
                # README was attempted but fetch failed — mark as FAIL
                signals.append(make_signal(
                    id="sdk.readme_quickstart_length",
                    label="README quickstart section is concise",
                    weight=0.15, status=SignalStatus.FAIL,
                    notes=readme_fetch_error or "README fetch failed",
                ))
            else:
                # No github_org — not applicable
                signals.append(make_signal(
                    id="sdk.readme_quickstart_length",
                    label="README quickstart section is concise",
                    weight=0.15, status=SignalStatus.SKIP,
                    notes="No github_org configured",
                ))
        else:
            lines = (readme_content or "").splitlines()
            section_keywords = ["quick start", "quickstart", "getting started", "usage"]
            section_start: int | None = None
            section_end: int | None = None

            for i, line in enumerate(lines):
                stripped = line.strip().lstrip("#").strip().lower()
                if section_start is None:
                    if any(kw in stripped for kw in section_keywords):
                        section_start = i
                elif line.startswith("## "):
                    section_end = i
                    break

            if section_start is None:
                # Section not found — can't penalize
                signals.append(make_signal(
                    id="sdk.readme_quickstart_length",
                    label="README quickstart section is concise",
                    weight=0.15, status=SignalStatus.PASS,
                    notes="No quickstart section found — cannot penalize",
                ))
            else:
                end = section_end if section_end is not None else len(lines)
                section_length = end - section_start

                if section_length <= 300:
                    signals.append(make_signal(
                        id="sdk.readme_quickstart_length",
                        label="README quickstart section is concise",
                        weight=0.15, status=SignalStatus.PASS,
                        notes=f"Section is {section_length} lines",
                    ))
                elif section_length <= 600:
                    signals.append(make_signal(
                        id="sdk.readme_quickstart_length",
                        label="README quickstart section is concise",
                        weight=0.15, status=SignalStatus.PARTIAL,
                        notes=f"Section is {section_length} lines (301–600)",
                    ))
                else:
                    signals.append(make_signal(
                        id="sdk.readme_quickstart_length",
                        label="README quickstart section is concise",
                        weight=0.15, status=SignalStatus.FAIL,
                        notes=f"Section is {section_length} lines (> 600)",
                    ))

        # --- Signal 6: sdk.async_client_available ---
        async_keywords = ["async", "asyncio", "async/await", "promise", "async def"]
        npm_has_async = False
        pypi_has_async = False

        if npm is not None:
            # Check npm README or description for async keywords
            text_to_check = ""
            if readme_content is not None:
                text_to_check = readme_content.lower()
            elif npm_data is not None:
                text_to_check = str(npm_data.get("readme", "")).lower()
            if any(kw in text_to_check for kw in async_keywords) or (
                npm is not None and "-async" in npm.lower()
            ):
                npm_has_async = True

        if pypi is not None:
            text_to_check = ""
            if pypi_data is not None:
                info = pypi_data.get("info") or {}
                text_to_check = (
                    str(info.get("description", "")).lower() + " " +
                    str(info.get("summary", "")).lower()
                )
            if any(kw in text_to_check for kw in async_keywords) or (
                pypi is not None and "-async" in pypi.lower()
            ):
                pypi_has_async = True

        if npm is None and pypi is None:
            signals.append(make_signal(
                id="sdk.async_client_available", label="Async client available",
                weight=0.15, status=SignalStatus.SKIP,
                notes="No npm or pypi package configured",
            ))
        elif npm_has_async and pypi_has_async:
            signals.append(make_signal(
                id="sdk.async_client_available", label="Async client available",
                weight=0.15, status=SignalStatus.PASS,
                notes="Async support found in both npm and pypi packages",
            ))
        elif npm_has_async or pypi_has_async:
            which = "npm" if npm_has_async else "pypi"
            signals.append(make_signal(
                id="sdk.async_client_available", label="Async client available",
                weight=0.15, status=SignalStatus.PARTIAL,
                notes=f"Async support found only in {which} package",
            ))
        else:
            signals.append(make_signal(
                id="sdk.async_client_available", label="Async client available",
                weight=0.15, status=SignalStatus.FAIL,
                notes="No async client mention found in npm or pypi packages",
            ))

        # --- Signal 7: sdk.version_in_sync ---
        def _parse_major_minor(version_str: str) -> tuple[int, int] | None:
            """Parse major.minor from a semver-like string."""
            try:
                parts = str(version_str).split(".")
                return int(parts[0]), int(parts[1])
            except (IndexError, ValueError):
                return None

        npm_version: str | None = None
        pypi_version: str | None = None

        if npm is not None and npm_data is not None:
            latest_tag = (npm_data.get("dist-tags") or {}).get("latest")
            if latest_tag:
                npm_version = latest_tag

        if pypi is not None and pypi_data is not None:
            pypi_version = (pypi_data.get("info") or {}).get("version")

        if npm_version is None or pypi_version is None:
            signals.append(make_signal(
                id="sdk.version_in_sync", label="SDK versions in sync",
                weight=0.10, status=SignalStatus.SKIP,
                notes="Only one package ecosystem present or version unavailable",
            ))
        else:
            npm_mm = _parse_major_minor(npm_version)
            pypi_mm = _parse_major_minor(pypi_version)
            if npm_mm is None or pypi_mm is None:
                signals.append(make_signal(
                    id="sdk.version_in_sync", label="SDK versions in sync",
                    weight=0.10, status=SignalStatus.SKIP,
                    notes=f"Could not parse versions: npm={npm_version}, pypi={pypi_version}",
                ))
            elif abs(npm_mm[0] - pypi_mm[0]) <= 1 and npm_mm[1] == pypi_mm[1]:
                signals.append(make_signal(
                    id="sdk.version_in_sync", label="SDK versions in sync",
                    weight=0.10, status=SignalStatus.PASS,
                    notes=f"npm={npm_version}, pypi={pypi_version} (within major.minor)",
                ))
            elif abs(npm_mm[0] - pypi_mm[0]) <= 1:
                signals.append(make_signal(
                    id="sdk.version_in_sync", label="SDK versions in sync",
                    weight=0.10, status=SignalStatus.PARTIAL,
                    notes=f"npm={npm_version}, pypi={pypi_version} (minor versions differ)",
                ))
            else:
                signals.append(make_signal(
                    id="sdk.version_in_sync", label="SDK versions in sync",
                    weight=0.10, status=SignalStatus.FAIL,
                    notes=f"npm={npm_version}, pypi={pypi_version} (major version diverges >1)",
                ))

        score = compute_dimension_score(signals)
        return self._make_dimension_score(signals, score)
