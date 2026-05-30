#!/usr/bin/env bash
# Fan-out: implement 6 scanner files (TASK-010 to TASK-015) with concurrency 3.
set -uo pipefail

REPO="/mnt/c/Users/Aiden Antony/agentsurface/agentsurface"
RESULTS="${REPO}/.orchestrate/results"
mkdir -p "${RESULTS}"

# ── run_one <task_id> <scanner_name> <prompt_file> ──────────────────────────
run_one() {
  local task_id="$1"
  local scanner_name="$2"
  local prompt_file="$3"
  echo "[fanout] Starting ${task_id} (${scanner_name})..."
  claude -p "$(cat "${prompt_file}")" \
    --allowedTools "Read,Edit,Glob,Grep,Write" \
    --max-turns 30 \
    --dangerously-skip-permissions \
    --output-format json \
    > "${RESULTS}/${task_id}.json" 2>"${RESULTS}/${task_id}.err"
  echo $? > "${RESULTS}/${task_id}.exit"
  echo "[fanout] Done ${task_id}"
}

# ── Shared interface reference (written into each prompt) ───────────────────
read -r -d '' IFACE <<'IFACE_EOF' || true
## Existing Interface (already implemented — do NOT re-implement or modify these files)

### src/agentsurface/scanners/base.py
- `Target` dataclass fields: slug, name, category, homepage, docs_url, openapi_url (str|None), github_org (str|None), npm_package (str|None), pypi_package (str|None), mcp_server_url (str|None), error_probes (list[str])
- `Scanner` ABC: class-level attrs `dimension_id: str`, `dimension_name: str`, `weight: float`
  - `async def scan(self, target: Target, *, fetch_records: list, test_mode: bool = False) -> DimensionScore`
  - `def _make_dimension_score(self, signals: list[Signal], score: float) -> DimensionScore`
- `make_signal(id, label, weight, status, evidence_url=None, notes=None) -> Signal`

### src/agentsurface/scanners/__init__.py
- `register` decorator — apply as `@register` on your Scanner subclass

### src/agentsurface/models.py
- `SignalStatus`: PASS, FAIL, PARTIAL, SKIP
- `Signal`, `DimensionScore` (pydantic v2 models)

### src/agentsurface/http.py
- `async def fetch(url, *, method="GET", headers=None, timeout=None, follow_redirects=True, record_list=None) -> httpx.Response`
- `FetchRecord` dataclass with fields url: str, fetched_at: str

### src/agentsurface/framework.py
- `compute_dimension_score(signals: list[Signal]) -> float`  — weighted avg * 100, SKIP signals excluded

## Standard scanner pattern

```python
from __future__ import annotations
import httpx
from agentsurface.scanners import register
from agentsurface.scanners.base import Scanner, Target, make_signal
from agentsurface.models import SignalStatus, DimensionScore
from agentsurface.framework import compute_dimension_score
from agentsurface import http

@register
class XxxScanner(Scanner):
    dimension_id = "xxx_dimension"
    dimension_name = "Xxx Dimension"
    weight = 0.XX

    async def scan(
        self,
        target: Target,
        *,
        fetch_records: list,
        test_mode: bool = False,
    ) -> DimensionScore:
        signals = []

        # Example signal check
        try:
            resp = await http.fetch(target.homepage, record_list=fetch_records)
            if resp.status_code == 200:
                signals.append(make_signal(
                    id="xxx.some_signal", label="Some Signal",
                    weight=0.25, status=SignalStatus.PASS,
                    evidence_url=target.homepage,
                ))
            else:
                signals.append(make_signal(
                    id="xxx.some_signal", label="Some Signal",
                    weight=0.25, status=SignalStatus.FAIL,
                    notes=f"HTTP {resp.status_code}",
                ))
        except httpx.HTTPError as exc:
            signals.append(make_signal(
                id="xxx.some_signal", label="Some Signal",
                weight=0.25, status=SignalStatus.FAIL,
                notes=str(exc),
            ))

        score = compute_dimension_score(signals)
        return self._make_dimension_score(signals, score)
```

## Rules
- ALL HTTP calls MUST use `await http.fetch(url, record_list=fetch_records)` — never create raw httpx clients
- Wrap every HTTP call in try/except httpx.HTTPError — network failure → FAIL signal
- Never let scan() raise — always return a DimensionScore
- Signal weights within each scanner MUST sum to 1.0
- Use make_signal() for all Signal construction
- Add a module-level docstring describing what this scanner measures
- Write ONLY your assigned scanner file. Do NOT touch STATUS.md, TASKS.md, or any other file.
- After writing the file successfully, print to stdout EXACTLY this JSON (one line, no other output):
  {"item":"TASK-0XX","files_changed":["src/agentsurface/scanners/XXX.py"]}
IFACE_EOF

# ── Per-scanner prompts ──────────────────────────────────────────────────────

# TASK-010: OpenAPI scanner
cat > /tmp/prompt_010.txt <<PROMPT_EOF
You are implementing TASK-010 for the AgentSurface project.
Repo root: /mnt/c/Users/Aiden Antony/agentsurface/agentsurface/

${IFACE}

## Your task: Write src/agentsurface/scanners/openapi.py

Implement OpenAPIScanner with dimension_id="openapi_quality", dimension_name="OpenAPI Quality", weight=0.20.

### Signals (weights must sum to 1.0):

1. **openapi.spec_discoverable** (weight=0.20): Can an OpenAPI spec be found?
   - If target.openapi_url is set, try fetching it directly
   - Otherwise, probe these paths from target.docs_url base: /openapi.json, /openapi.yaml, /swagger.json, /api-docs, /api/openapi.json
   - PASS if any returns 200 with OpenAPI-like content; FAIL otherwise
   - Store the found URL in evidence_url

2. **openapi.valid_oas3** (weight=0.20): Is it a valid OAS 3.x spec?
   - Parse response as JSON or YAML
   - Check for "openapi" key starting with "3."
   - PASS if valid OAS3; PARTIAL if old Swagger 2.x found; FAIL if parse fails or no spec

3. **openapi.has_servers** (weight=0.15): Does the spec have a non-empty servers[] array?
   - PASS if servers list exists and has at least one entry with a url field
   - FAIL otherwise; SKIP if no spec found

4. **openapi.auth_in_security_schemes** (weight=0.20): Is auth defined in the spec's securitySchemes?
   - Check components.securitySchemes for at least one entry
   - PASS if found; FAIL if absent; SKIP if no spec

5. **openapi.error_response_schemas** (weight=0.15): Do error responses have schemas?
   - Sample up to 10 operations; count how many have at least one 4xx or 5xx response with content defined
   - PASS if ≥50% of sampled ops have error schemas; PARTIAL if 25–49%; FAIL if <25%; SKIP if no spec

6. **openapi.example_coverage** (weight=0.10): Do ≥50% of operations have examples?
   - Sample up to 20 operations; check requestBody or parameters for examples/example fields
   - PASS if ≥50%; PARTIAL if 25–49%; FAIL if <25%; SKIP if no spec

### Notes:
- Parse YAML using `import yaml` (pyyaml is installed)
- Parse JSON using `import json`
- Probe docs_url base by extracting scheme+netloc from target.docs_url
- For the spec URL, strip to base URL (scheme://host) if target.openapi_url has a full path

After writing, print exactly: {"item":"TASK-010","files_changed":["src/agentsurface/scanners/openapi.py"]}
PROMPT_EOF

# TASK-011: Docs scanner
cat > /tmp/prompt_011.txt <<PROMPT_EOF
You are implementing TASK-011 for the AgentSurface project.
Repo root: /mnt/c/Users/Aiden Antony/agentsurface/agentsurface/

${IFACE}

## Your task: Write src/agentsurface/scanners/docs.py

Implement DocsScanner with dimension_id="docs_accessibility", dimension_name="Docs Accessibility", weight=0.20.

### Signals (weights must sum to 1.0):

1. **docs.llms_txt** (weight=0.30): Does /llms.txt return 200?
   - Fetch {docs_base}/llms.txt where docs_base is scheme://host of target.docs_url
   - Also try {homepage_base}/llms.txt
   - PASS if any returns 200 with non-empty body; FAIL otherwise
   - Store the working URL in evidence_url

2. **docs.llms_full_txt** (weight=0.20): Does /llms-full.txt or a Markdown variant exist?
   - Probe: /llms-full.txt, /llms.md, /llms-full.md (on both docs_base and homepage_base)
   - PASS if any returns 200; FAIL otherwise

3. **docs.html_content_density** (weight=0.25): Is the docs page content-dense (not mostly boilerplate)?
   - Fetch the docs_url HTML page
   - Count the raw byte length vs the text content length (strip HTML tags)
   - Metric: text_bytes / total_bytes. PASS if ≥ 0.20 (20% is content); PARTIAL if 0.10–0.19; FAIL if < 0.10
   - Use a simple regex to strip tags: re.sub(r'<[^>]+>', '', html)
   - SKIP if fetch fails

4. **docs.no_js_gates** (weight=0.25): Is content accessible without JavaScript?
   - Heuristic: check if the HTML contains <noscript> with "javascript required" or "please enable javascript"
   - Also check if there's a meaningful amount of text content even without JS execution
   - If text content (after strip) is < 500 chars while total HTML is > 50KB, likely JS-gated → FAIL
   - PASS if text content is present and no JS-required gates detected; PARTIAL if uncertain; SKIP if fetch fails

### Notes:
- Extract base URL: from target.docs_url, use urllib.parse.urlparse to get scheme + netloc
- Do the same for target.homepage
- Strip tags with re.sub(r'<[^>]+>', '', html_text)

After writing, print exactly: {"item":"TASK-011","files_changed":["src/agentsurface/scanners/docs.py"]}
PROMPT_EOF

# TASK-012: SDK scanner
cat > /tmp/prompt_012.txt <<PROMPT_EOF
You are implementing TASK-012 for the AgentSurface project.
Repo root: /mnt/c/Users/Aiden Antony/agentsurface/agentsurface/

${IFACE}

## Your task: Write src/agentsurface/scanners/sdk.py

Implement SDKScanner with dimension_id="sdk_ergonomics", dimension_name="SDK Ergonomics", weight=0.15.

### Signals (weights must sum to 1.0):

1. **sdk.npm_package** (weight=0.25): Official npm package exists?
   - If target.npm_package is None → SKIP
   - Fetch https://registry.npmjs.org/{npm_package}
   - PASS if 200 and response contains "name" field; FAIL if 404
   - evidence_url = f"https://www.npmjs.com/package/{npm_package}"

2. **sdk.pypi_package** (weight=0.25): Official PyPI package exists?
   - If target.pypi_package is None → SKIP
   - Fetch https://pypi.org/pypi/{pypi_package}/json
   - PASS if 200; FAIL if 404
   - evidence_url = f"https://pypi.org/project/{pypi_package}/"

3. **sdk.readme_install_oneliner** (weight=0.20): README has an install command in first 20 lines?
   - If target.github_org and (npm_package or pypi_package): try fetching raw README from GitHub
   - Try: https://raw.githubusercontent.com/{github_org}/{npm_package or pypi_package}/main/README.md
     then: https://raw.githubusercontent.com/{github_org}/{npm_package or pypi_package}/master/README.md
   - Check first 20 lines for patterns: "npm install", "pip install", "yarn add", "uv pip install"
   - PASS if found; FAIL if not; SKIP if no github_org

4. **sdk.typed** (weight=0.15): Is the SDK typed?
   - For npm packages: fetch https://registry.npmjs.org/{npm_package}, check if "types" or "typings" key exists in latest version dist-tags response
   - For pypi packages: check if package metadata mentions "py.typed" or "Typing :: Typed" in classifiers
   - PASS if typed; PARTIAL if typing stubs available separately; FAIL if no types; SKIP if neither package exists

5. **sdk.readme_quickstart_length** (weight=0.15): Is the README quickstart section concise (<300 lines)?
   - Use the README fetched in signal 3 (or re-fetch if needed)
   - Find a "Quick Start", "Getting Started", or "Usage" section
   - Count lines until the next ## heading
   - PASS if ≤ 300 lines or section not found (can't penalize what we can't measure); PARTIAL if 301–600; FAIL if > 600
   - SKIP if no README found

### Notes:
- Track which README you fetched to avoid re-fetching
- Store the readme content in a local variable shared across signal checks in the scan() method
- If both npm and pypi are None, most signals will SKIP — that's fine

After writing, print exactly: {"item":"TASK-012","files_changed":["src/agentsurface/scanners/sdk.py"]}
PROMPT_EOF

# TASK-013: Errors scanner
cat > /tmp/prompt_013.txt <<PROMPT_EOF
You are implementing TASK-013 for the AgentSurface project.
Repo root: /mnt/c/Users/Aiden Antony/agentsurface/agentsurface/

${IFACE}

## Your task: Write src/agentsurface/scanners/errors.py

Implement ErrorsScanner with dimension_id="error_ux", dimension_name="Error UX", weight=0.15.

This scanner probes the API with a deliberately bad request to observe error response quality.

### Probe strategy:
- If target.error_probes is non-empty, use the first URL as the probe URL
- Otherwise, use heuristics:
  - If target.openapi_url contains "stripe": try GET {base}/v1/customers/nonexistent_id_xxxxxx
  - Generic: try GET {api_base}/v1/nonexistent_endpoint_xxxxxx where api_base is derived from docs_url or homepage
  - Try common patterns: /api/v1/test, /v1/test, /api/test (expecting 404 or 400)
  - Set the request header: "Accept: application/json"
- Parse the response body as JSON

### Signals (weights must sum to 1.0):

1. **errors.json_response** (weight=0.25): Is the error response valid JSON?
   - PASS if Content-Type contains "json" AND body parses as JSON object
   - PARTIAL if body is JSON but Content-Type header doesn't say json
   - FAIL if not JSON; SKIP if no probe URL available and no response obtained

2. **errors.machine_code** (weight=0.25): Does the JSON error contain a stable machine-readable code?
   - Look for keys: "code", "error_code", "type", "error.type", "error", "status" (where value is a string, not an int)
   - PASS if found and value is a non-numeric string (e.g., "invalid_request", "not_found")
   - FAIL if missing; SKIP if no JSON response

3. **errors.docs_url** (weight=0.20): Does the error response include a link to documentation?
   - Look for keys: "doc_url", "docs_url", "documentation_url", "more_info", "help_url", or any value that is a URL string starting with "http"
   - PASS if a docs URL is found; FAIL otherwise; SKIP if no JSON

4. **errors.names_offending_field** (weight=0.15): For validation errors, does the response name the offending field?
   - This applies when the response indicates a validation/bad-request error
   - Look for: "param", "field", "path", "location", nested "errors" array with field info
   - PASS if field context is present; PARTIAL if only top-level error without field; FAIL if no field context; SKIP if status code isn't 400-range or no JSON

5. **errors.correct_status_code** (weight=0.15): Is the HTTP status code semantically correct?
   - 400: bad request (validation error) — correct
   - 404: not found — correct
   - 401/403: auth needed — correct
   - 200 or 5xx for what should be a client error → FAIL
   - PASS if status is in 4xx range and makes semantic sense; FAIL if 200 or 5xx; SKIP if no response

### Notes:
- Do NOT make authenticated requests — always use unauthenticated requests
- A 401 or 403 response is fine (common for public APIs without auth)
- For the probe, prefer to trigger a clear client error (not a 500)
- The probe may fail completely (network error, timeout) — in that case all signals SKIP

After writing, print exactly: {"item":"TASK-013","files_changed":["src/agentsurface/scanners/errors.py"]}
PROMPT_EOF

# TASK-014: Auth scanner
cat > /tmp/prompt_014.txt <<PROMPT_EOF
You are implementing TASK-014 for the AgentSurface project.
Repo root: /mnt/c/Users/Aiden Antony/agentsurface/agentsurface/

${IFACE}

## Your task: Write src/agentsurface/scanners/auth.py

Implement AuthScanner with dimension_id="auth_ergonomics", dimension_name="Auth Ergonomics", weight=0.15.

This scanner checks how well the API documents and implements auth for automated/agent use.

### Signals (weights must sum to 1.0):

1. **auth.programmatic_key_issuance** (weight=0.35): Can an agent obtain an API key without human-only flows?
   - Heuristic: fetch the docs_url page and search for keywords: "api key", "service account", "programmatic", "machine", "automated", "non-interactive"
   - Also check if the homepage mentions a "console", "dashboard" or programmatic approach
   - PASS if clear programmatic/service-account path is documented
   - PARTIAL if only dashboard-based key creation mentioned (human flow, but at least it's documented)
   - FAIL if auth method is entirely undocumented on public pages
   - Use notes to record what was found

2. **auth.security_schemes_defined** (weight=0.35): Is auth defined in the OpenAPI spec?
   - If target.openapi_url is None → SKIP
   - Fetch the OpenAPI spec and check components.securitySchemes
   - PASS if at least one securityScheme is defined with a valid type (apiKey, http, oauth2, openIdConnect)
   - PARTIAL if security is mentioned in paths but not in securitySchemes
   - FAIL if no securitySchemes; SKIP if spec not available

3. **auth.scopes_enumerable** (weight=0.30): Are auth scopes/permissions documented and enumerable?
   - Check the OpenAPI spec for oauth2 flows with scopes defined, OR apiKey with x-scopes extension
   - Also check docs_url for a page containing "scopes", "permissions", "access levels"
   - PASS if scopes are explicitly listed (in spec or docs); PARTIAL if vaguely mentioned; FAIL if absent
   - evidence_url = wherever scopes were found (spec URL or docs page)

### Notes:
- This scanner is heuristic-heavy — use conservative scoring when uncertain
- For signal 1, scanning the text content of the docs homepage is sufficient; no deep crawl
- For signal 3, if the API uses simple API keys (no scopes), score as PARTIAL with a note
  that scoped keys would improve agent security

After writing, print exactly: {"item":"TASK-014","files_changed":["src/agentsurface/scanners/auth.py"]}
PROMPT_EOF

# TASK-015: Discovery scanner
cat > /tmp/prompt_015.txt <<PROMPT_EOF
You are implementing TASK-015 for the AgentSurface project.
Repo root: /mnt/c/Users/Aiden Antony/agentsurface/agentsurface/

${IFACE}

## Your task: Write src/agentsurface/scanners/discovery.py

Implement DiscoveryScanner with dimension_id="discovery_surface", dimension_name="Discovery Surface", weight=0.15.

This scanner checks whether the API has published agent-discovery artefacts.

### Signals (weights must sum to 1.0):

1. **discovery.agents_md** (weight=0.30): Does the GitHub repo have an AGENTS.md at the root?
   - If target.github_org is None → SKIP
   - Guess the primary repo name: try target.slug, then target.npm_package, then target.pypi_package
   - Fetch: https://raw.githubusercontent.com/{github_org}/{repo}/main/AGENTS.md
   - Also try: /master/AGENTS.md if main fails
   - PASS if 200 and non-empty; FAIL if 404; SKIP if no github_org
   - evidence_url = the working URL if found

2. **discovery.mcp_server** (weight=0.25): Is an MCP server documented or reachable?
   - If target.mcp_server_url is set: fetch it, PASS if 200/401/405 (reachable), FAIL if connection error
   - If target.mcp_server_url is None: check homepage and docs_url HTML for text "mcp", "model context protocol"
   - PASS if mcp_server_url is reachable; PARTIAL if text mentions MCP but no URL; FAIL if no mention; SKIP if unreachable with timeout

3. **discovery.ai_plugin_json** (weight=0.20): Is /.well-known/ai-plugin.json present?
   - Fetch {homepage_base}/.well-known/ai-plugin.json
   - PASS if 200 and body parses as JSON with "name_for_human" or similar ChatGPT plugin fields
   - PARTIAL if 200 but doesn't look like a valid plugin manifest
   - FAIL if 404; SKIP if connection error

4. **discovery.robots_ai_policy** (weight=0.25): Does robots.txt distinguish AI crawlers?
   - Fetch {homepage_base}/robots.txt
   - Check for User-agent entries specifically for AI crawlers: GPTBot, ClaudeBot, PerplexityBot, anthropic-ai, ChatGPT-User, Google-Extended, Bytespider
   - PASS if at least 2 AI-specific User-agent entries found
   - PARTIAL if 1 AI-specific entry found
   - FAIL if robots.txt exists but no AI-specific entries; SKIP if robots.txt returns non-200

### Notes:
- Homepage base: urllib.parse.urlparse(target.homepage) → scheme://netloc
- For signal 1, try multiple repo name guesses before giving up
- A 401 or 405 response for mcp_server_url counts as "reachable" (server exists, auth required)

After writing, print exactly: {"item":"TASK-015","files_changed":["src/agentsurface/scanners/discovery.py"]}
PROMPT_EOF

# ── Fan-out execution (concurrency 3) ───────────────────────────────────────
declare -A JOBS

launch_job() {
  local task_id="$1"
  local scanner_name="$2"
  local prompt_file="$3"
  run_one "${task_id}" "${scanner_name}" "${prompt_file}" &
  JOBS["${task_id}"]=$!
}

running_count() {
  local count=0
  for pid in "${JOBS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      ((count++)) || true
    fi
  done
  echo $count
}

# Launch with concurrency 3
for ITEM in "TASK-010:openapi:/tmp/prompt_010.txt" \
            "TASK-011:docs:/tmp/prompt_011.txt" \
            "TASK-012:sdk:/tmp/prompt_012.txt" \
            "TASK-013:errors:/tmp/prompt_013.txt" \
            "TASK-014:auth:/tmp/prompt_014.txt" \
            "TASK-015:discovery:/tmp/prompt_015.txt"; do
  IFS=':' read -r task_id scanner_name prompt_file <<< "${ITEM}"

  # Wait until fewer than 3 jobs are running
  while [ "$(running_count)" -ge 3 ]; do
    sleep 5
  done

  launch_job "${task_id}" "${scanner_name}" "${prompt_file}"
done

# Wait for all remaining
wait
echo "[fanout] All scanner jobs complete."
