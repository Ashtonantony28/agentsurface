#!/usr/bin/env bash
# Fan-out: write per-scanner test files (TASK-026), concurrency 3.
set -uo pipefail

REPO="/mnt/c/Users/Aiden Antony/agentsurface/agentsurface"
RESULTS="${REPO}/.orchestrate/results"
mkdir -p "${RESULTS}"

run_one() {
  local task_id="$1"
  local prompt_file="$2"
  echo "[fanout-tests] Starting ${task_id}..."
  claude -p "$(cat "${prompt_file}")" \
    --allowedTools "Read,Edit,Glob,Grep,Write" \
    --max-turns 30 \
    --dangerously-skip-permissions \
    --output-format json \
    > "${RESULTS}/${task_id}_tests.json" 2>"${RESULTS}/${task_id}_tests.err"
  echo $? > "${RESULTS}/${task_id}_tests.exit"
  echo "[fanout-tests] Done ${task_id}"
}

# ── OPENAPI scanner test ────────────────────────────────────────────────────
cat > /tmp/prompt_026_openapi.txt <<'PROMPT_EOF'
You are writing tests for TASK-026 (OpenAPI scanner) for the AgentSurface project.
Repo root: /mnt/c/Users/Aiden Antony/agentsurface/agentsurface/

## What to write
1. Fixture files under tests/fixtures/openapi/
2. Test file: tests/test_scanner_openapi.py

## Scanner behaviour (src/agentsurface/scanners/openapi.py)
The OpenAPIScanner fetches:
- target.openapi_url directly (if set)
- OR probes docs_base + /openapi.json, /openapi.yaml, /swagger.json, /api-docs, /api/openapi.json

Signals: spec_discoverable (0.20), valid_oas3 (0.20), has_servers (0.15),
         auth_in_security_schemes (0.20), error_response_schemas (0.15), example_coverage (0.10)

## Fixture files to create

### tests/fixtures/openapi/spec_pass.json
A minimal but valid OAS 3.1.0 JSON spec with:
- openapi: "3.1.0"
- info: {title: "Test API", version: "1.0.0"}
- servers: [{url: "https://api.testapi.example.com"}]
- components.securitySchemes: {ApiKey: {type: "apiKey", name: "Authorization", in: "header"}}
- paths with 3 operations, each having a 400 response with content (schema), and each operation having an example parameter
Write this as valid JSON.

### tests/fixtures/openapi/spec_swagger2.json
An old Swagger 2.0 spec (swagger: "2.0") with no servers and no securitySchemes.
Just minimal valid Swagger 2: swagger, info, paths (one operation, no examples).

## Test file: tests/test_scanner_openapi.py

Use respx to mock httpx. Use pytest-asyncio for async tests (mark with @pytest.mark.asyncio).

```python
import pytest
import respx
import httpx
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "openapi"

@pytest.fixture
def pass_spec():
    return (FIXTURES / "spec_pass.json").read_bytes()

@pytest.fixture
def swagger2_spec():
    return (FIXTURES / "spec_swagger2.json").read_bytes()
```

### Test 1: test_openapi_pass — all signals pass
- Target: slug="testapi", homepage="https://testapi.example.com", docs_url="https://docs.testapi.example.com", openapi_url="https://docs.testapi.example.com/openapi.json"
- Use respx.mock to route GET https://docs.testapi.example.com/openapi.json → 200, content=pass_spec, content_type="application/json"
- Run OpenAPIScanner().scan(target, fetch_records=[])
- Assert: dimension_id == "openapi_quality"
- Assert: signal "openapi.spec_discoverable" has status "pass"
- Assert: signal "openapi.valid_oas3" has status "pass"
- Assert: signal "openapi.has_servers" has status "pass"
- Assert: signal "openapi.auth_in_security_schemes" has status "pass"
- Assert: score > 50.0

### Test 2: test_openapi_no_spec — spec not found, all signals fail/skip
- Target: no openapi_url, docs_url="https://docs.testapi.example.com"
- Use respx.mock to route all probe paths (docs_base + /openapi.json, /openapi.yaml, etc.) → 404
- Assert: signal "openapi.spec_discoverable" has status "fail"
- Assert: signal "openapi.valid_oas3" has status "fail"
- Assert: signals "has_servers", "auth_in_security_schemes", "error_response_schemas", "example_coverage" all have status "skip"
- Assert: score == 0.0

### Test 3: test_openapi_swagger2 — Swagger 2 spec found, valid_oas3 is partial
- Target: openapi_url="https://docs.testapi.example.com/openapi.json"
- Route GET https://docs.testapi.example.com/openapi.json → 200, swagger2_spec
- Assert: signal "openapi.spec_discoverable" has status "pass"
- Assert: signal "openapi.valid_oas3" has status "partial"

## Implementation notes
- Import OpenAPIScanner: `from agentsurface.scanners.openapi import OpenAPIScanner`
- Use `@respx.mock` decorator on async test functions (easier than context manager for multiple requests)
- The `http.fetch()` function uses `httpx.AsyncClient` internally. Use `respx.mock` at module level or as a decorator — it patches all httpx clients.
- For probe paths: the docs_base is "https://docs.testapi.example.com". Mock all 5 probe paths → 404 for test 2.
- Mark module with `pytestmark = pytest.mark.asyncio`

After writing, print exactly: {"item":"TASK-026-openapi","files_changed":["tests/test_scanner_openapi.py","tests/fixtures/openapi/spec_pass.json","tests/fixtures/openapi/spec_swagger2.json"]}
PROMPT_EOF

# ── DOCS scanner test ────────────────────────────────────────────────────────
cat > /tmp/prompt_026_docs.txt <<'PROMPT_EOF'
You are writing tests for TASK-026 (Docs scanner) for the AgentSurface project.
Repo root: /mnt/c/Users/Aiden Antony/agentsurface/agentsurface/

## What to write
1. Fixture files under tests/fixtures/docs/
2. Test file: tests/test_scanner_docs.py

## Scanner behaviour (src/agentsurface/scanners/docs.py)
The DocsScanner fetches:
- {docs_base}/llms.txt and {home_base}/llms.txt
- {docs_base}/llms-full.txt, /llms.md, /llms-full.md (and home_base variants)
- target.docs_url (the full docs HTML page)

Signals: llms_txt (0.30), llms_full_txt (0.20), html_content_density (0.25), no_js_gates (0.25)

Content density logic:
- text_bytes / total_bytes >= 0.20 → PASS
- >= 0.10 → PARTIAL
- < 0.10 → FAIL

JS gate logic:
- <noscript> with "javascript required" → FAIL
- text_bytes < 500 and total_bytes > 50000 → FAIL (likely JS-gated)
- text_bytes >= 500 and no gate → PASS

## Fixture files to create

### tests/fixtures/docs/llms_txt.txt
Content: a short llms.txt file, e.g.:
```
# Test API
> A test API for agent testing

## Endpoints
- /v1/items - List items
```

### tests/fixtures/docs/docs_page_pass.html
An HTML page with substantial text content (>20% text ratio). Include:
- A normal HTML page with <head>, <body>
- A nav, main content with several paragraphs of real text (>500 chars of text content)
- No noscript gates
- Total size should be reasonable (a few KB)

### tests/fixtures/docs/docs_page_jsgated.html
An HTML page that's JS-gated:
- Small text content: <noscript>JavaScript required. Please enable JavaScript to continue.</noscript>
- Large script tags (to inflate total size > 50KB — just put a big comment inside <script>)
- Very little text content after stripping tags

## Test file: tests/test_scanner_docs.py

```python
import pytest
import respx
import httpx
from pathlib import Path
from agentsurface.scanners.docs import DocsScanner

FIXTURES = Path(__file__).parent / "fixtures" / "docs"
pytestmark = pytest.mark.asyncio
```

### Test 1: test_docs_pass — llms.txt present, good HTML
- Target: homepage="https://testapi.example.com", docs_url="https://docs.testapi.example.com"
- Mock:
  - GET https://docs.testapi.example.com/llms.txt → 200, llms_txt content
  - GET https://testapi.example.com/llms.txt → 404
  - GET https://docs.testapi.example.com/llms-full.txt → 200, b"# LLMs Full"
  - GET https://docs.testapi.example.com → 200, docs_page_pass.html content, content_type="text/html"
- Assert: signal "docs.llms_txt" has status "pass"
- Assert: signal "docs.llms_full_txt" has status "pass"
- Assert: signal "docs.html_content_density" has status "pass"
- Assert: signal "docs.no_js_gates" has status "pass"

### Test 2: test_docs_no_llms_txt — no llms.txt, JS-gated page
- Mock all llms.txt and llms-full.txt probes → 404
- Mock GET docs_url → 200, docs_page_jsgated.html content
- Assert: signal "docs.llms_txt" has status "fail"
- Assert: signal "docs.llms_full_txt" has status "fail"
- Assert: signal "docs.no_js_gates" has status "fail" (noscript gate detected)

### Test 3: test_docs_page_fetch_fails
- Mock all llms.txt → 404
- Mock GET docs_url → raise httpx.ConnectError("connection refused")
- Assert: signal "docs.html_content_density" has status "skip"
- Assert: signal "docs.no_js_gates" has status "skip"

## Implementation notes
- Use `@respx.mock` decorator
- For the JS-gated test, the HTML needs a <noscript> containing "javascript required"
- The docs_page_jsgated.html needs total bytes > 50KB to trigger the JS gate check via the big-script heuristic — OR simply include a noscript gate (which triggers first)
- For llms-full.txt check: the scanner also tries /llms.md and /llms-full.md — mock those too if needed

After writing, print exactly: {"item":"TASK-026-docs","files_changed":["tests/test_scanner_docs.py","tests/fixtures/docs/llms_txt.txt","tests/fixtures/docs/docs_page_pass.html","tests/fixtures/docs/docs_page_jsgated.html"]}
PROMPT_EOF

# ── SDK scanner test ─────────────────────────────────────────────────────────
cat > /tmp/prompt_026_sdk.txt <<'PROMPT_EOF'
You are writing tests for TASK-026 (SDK scanner) for the AgentSurface project.
Repo root: /mnt/c/Users/Aiden Antony/agentsurface/agentsurface/

## What to write
1. Fixture files under tests/fixtures/sdk/
2. Test file: tests/test_scanner_sdk.py

## Scanner behaviour (src/agentsurface/scanners/sdk.py)
The SDKScanner fetches:
- https://registry.npmjs.org/{npm_package} — checks "name" field
- https://pypi.org/pypi/{pypi_package}/json — checks status 200
- https://raw.githubusercontent.com/{github_org}/{repo_name}/main/README.md (or master)
  - Checks first 20 lines for: "npm install", "pip install", "yarn add", "uv pip install"
  - Checks for quickstart section length
- For typing: npm data → latest version has "types" or "typings" key
- For typing: pypi data → classifiers contain "Typing :: Typed"

Signals: npm_package (0.25), pypi_package (0.25), readme_install_oneliner (0.20),
         typed (0.15), readme_quickstart_length (0.15)

## Fixture files to create

### tests/fixtures/sdk/npm_response_pass.json
A minimal npm registry response with:
- "name": "testapi"
- "dist-tags": {"latest": "1.0.0"}
- "versions": {"1.0.0": {"name": "testapi", "version": "1.0.0", "types": "./index.d.ts"}}

### tests/fixtures/sdk/pypi_response_pass.json
A minimal PyPI JSON response:
- info.name: "testapi"
- info.version: "1.0.0"
- info.classifiers: ["Programming Language :: Python :: 3", "Typing :: Typed"]

### tests/fixtures/sdk/readme_pass.md
A README with:
- Line 5: "npm install testapi" (install command in first 20 lines)
- A "## Quick Start" section that is 10 lines long (well under 300)

## Test file: tests/test_scanner_sdk.py

```python
import pytest
import respx
import httpx
from pathlib import Path
from agentsurface.scanners.sdk import SDKScanner

FIXTURES = Path(__file__).parent / "fixtures" / "sdk"
pytestmark = pytest.mark.asyncio
```

### Test 1: test_sdk_pass — npm, pypi, readme all pass
- Target: slug="testapi", homepage="https://testapi.example.com", docs_url="https://docs.testapi.example.com", npm_package="testapi", pypi_package="testapi", github_org="testorg"
- Mock:
  - GET https://registry.npmjs.org/testapi → 200, npm_response_pass.json content
  - GET https://pypi.org/pypi/testapi/json → 200, pypi_response_pass.json content
  - GET https://raw.githubusercontent.com/testorg/testapi/main/README.md → 200, readme_pass.md content
- Assert: all 5 signals are status "pass"
- Assert: score > 80.0

### Test 2: test_sdk_no_packages — no npm or pypi, most signals skip
- Target: npm_package=None, pypi_package=None, github_org=None
- No mocks needed (nothing will be fetched)
- Assert: signal "sdk.npm_package" has status "skip"
- Assert: signal "sdk.pypi_package" has status "skip"
- Assert: signal "sdk.readme_install_oneliner" has status "skip"
- Assert: signal "sdk.typed" has status "skip"

### Test 3: test_sdk_npm_not_found — npm 404
- Target: npm_package="nonexistent", pypi_package=None, github_org=None
- Mock GET https://registry.npmjs.org/nonexistent → 404
- Assert: signal "sdk.npm_package" has status "fail"

### Test 4: test_sdk_readme_no_install — README found but no install command
- Target: npm_package="testapi", pypi_package="testapi", github_org="testorg"
- Mock npm/pypi → 200 (from fixtures)
- Mock README → 200, content = "# Test API\n\nThis is a test API.\n" (no install command in first 20 lines)
- Assert: signal "sdk.readme_install_oneliner" has status "fail"

After writing, print exactly: {"item":"TASK-026-sdk","files_changed":["tests/test_scanner_sdk.py","tests/fixtures/sdk/npm_response_pass.json","tests/fixtures/sdk/pypi_response_pass.json","tests/fixtures/sdk/readme_pass.md"]}
PROMPT_EOF

# ── ERRORS scanner test ──────────────────────────────────────────────────────
cat > /tmp/prompt_026_errors.txt <<'PROMPT_EOF'
You are writing tests for TASK-026 (Errors scanner) for the AgentSurface project.
Repo root: /mnt/c/Users/Aiden Antony/agentsurface/agentsurface/

## What to write
1. Fixture files under tests/fixtures/errors/
2. Test file: tests/test_scanner_errors.py

## Scanner behaviour (src/agentsurface/scanners/errors.py)
The ErrorsScanner:
1. Derives a probe URL: uses target.error_probes[0] if set, else heuristic
   - Heuristic: strips to base URL from docs_url or homepage, then appends /v1/nonexistent_endpoint_xxxxxx
2. Fetches probe_url with headers {"Accept": "application/json"}
3. Parses JSON body

Signals:
- errors.json_response (0.25): PASS if Content-Type has "json" AND body is JSON object; PARTIAL if JSON but wrong CT
- errors.machine_code (0.25): PASS if body has code/error_code/type/status with non-numeric string value
- errors.docs_url (0.20): PASS if body has any URL string value
- errors.names_offending_field (0.15): PASS if body has param/field/path/location; PARTIAL if 400 but no field
- errors.correct_status_code (0.15): PASS if 4xx; FAIL if 200 or 5xx

## Fixture files to create

### tests/fixtures/errors/error_pass.json
A great error response JSON body:
```json
{
  "error": {
    "type": "invalid_request_error",
    "code": "resource_not_found",
    "message": "The requested resource does not exist.",
    "doc_url": "https://docs.testapi.example.com/errors/resource_not_found",
    "param": "id"
  }
}
```

### tests/fixtures/errors/error_no_code.json
A poor error response with no machine code, no docs URL, no field:
```json
{"message": "Not found", "status": 404}
```
Note: "status" with value 404 (integer) does NOT satisfy machine_code (must be non-numeric string).

## Test file: tests/test_scanner_errors.py

```python
import pytest
import respx
import httpx
from pathlib import Path
from agentsurface.scanners.errors import ErrorsScanner
from agentsurface.scanners.base import Target

FIXTURES = Path(__file__).parent / "fixtures" / "errors"
pytestmark = pytest.mark.asyncio
```

### Test 1: test_errors_pass — perfect error response
- Target: slug="testapi", homepage="https://testapi.example.com", docs_url="https://docs.testapi.example.com", error_probes=["https://testapi.example.com/v1/customers/nonexistent_id_xxx"]
- Mock GET https://testapi.example.com/v1/customers/nonexistent_id_xxx → 404, error_pass.json content, content_type="application/json"
- Assert: signal "errors.json_response" → "pass"
- Assert: signal "errors.machine_code" → "pass"  (error.type is "invalid_request_error", non-numeric string)
- Assert: signal "errors.docs_url" → "pass"  (doc_url field)
- Assert: signal "errors.names_offending_field" → "pass"  (param field inside error obj... wait: the scanner checks top-level only. Let me re-check)

Actually the scanner's _find_field_context checks top-level keys "param", "field", "path", "location" AND top-level "errors" array. The fixture has nested error.param.

Adjust test: the fixture should have param at TOP LEVEL:
Fixture error_pass.json should be:
```json
{
  "type": "invalid_request_error",
  "code": "resource_not_found",
  "message": "Not found.",
  "doc_url": "https://docs.testapi.example.com/errors/resource_not_found",
  "param": "id"
}
```

- Assert: signal "errors.correct_status_code" → "pass" (404 is 4xx)
- Assert: score > 70.0

### Test 2: test_errors_poor_response — no machine code, no docs URL
- Use error_probes to set a specific URL
- Mock → 404, error_no_code.json, content_type="application/json"
- Assert: signal "errors.json_response" → "pass"
- Assert: signal "errors.machine_code" → "fail" (status is integer 404, not a string)
- Assert: signal "errors.docs_url" → "fail" (no URL value in body)
- Assert: signal "errors.names_offending_field" → "partial" (400-range but no field named... wait 404 → not a 400 validation error)
  - Actually for 404: signal logic says if NOT 400-range → SKIP. 404 IS in 400 range. But no field → FAIL.
- Assert: signal "errors.correct_status_code" → "pass"

### Test 3: test_errors_no_probe — no error_probes, unreachable heuristic URL
- Target: homepage="https://testapi.example.com", docs_url="https://docs.testapi.example.com"
- The heuristic probe URL will be "https://testapi.example.com/v1/nonexistent_endpoint_xxxxxx"
- Mock GET https://testapi.example.com/v1/nonexistent_endpoint_xxxxxx → raise httpx.ConnectError
- Assert: all 5 signals have status "skip"

After writing, print exactly: {"item":"TASK-026-errors","files_changed":["tests/test_scanner_errors.py","tests/fixtures/errors/error_pass.json","tests/fixtures/errors/error_no_code.json"]}
PROMPT_EOF

# ── AUTH scanner test ────────────────────────────────────────────────────────
cat > /tmp/prompt_026_auth.txt <<'PROMPT_EOF'
You are writing tests for TASK-026 (Auth scanner) for the AgentSurface project.
Repo root: /mnt/c/Users/Aiden Antony/agentsurface/agentsurface/

## What to write
1. Fixture files under tests/fixtures/auth/
2. Test file: tests/test_scanner_auth.py

## Scanner behaviour (src/agentsurface/scanners/auth.py)
The AuthScanner fetches:
1. target.docs_url → HTML (searches for programmatic/dashboard keywords)
2. target.homepage → HTML (same search)
3. target.openapi_url (if set) → spec (for securitySchemes and scopes)
   NOTE: fetches openapi_url TWICE — once for signal 2, once for signal 3. Mock accordingly.

Signal 1 (auth.programmatic_key_issuance, 0.35):
- PASS if programmatic_keywords found: "api key", "service account", "programmatic", "machine", "automated", "non-interactive"
- PARTIAL if only dashboard_keywords: "console", "dashboard", "portal"
- FAIL if neither

Signal 2 (auth.security_schemes_defined, 0.35):
- SKIP if no openapi_url
- PASS if securitySchemes has entry with type in {apiKey, http, oauth2, openIdConnect}
- PARTIAL if security in paths but no schemes
- FAIL if no schemes

Signal 3 (auth.scopes_enumerable, 0.30):
- PASS if OAuth2 scopes in spec
- PARTIAL if simple API keys (apiKey type) or scope keywords in docs
- FAIL otherwise

## Fixture files to create

### tests/fixtures/auth/docs_pass.html
HTML page that contains "api key" and "programmatic" keywords in body text.
Simple HTML: <html><body>Get an API key programmatically via our service account endpoint.</body></html>

### tests/fixtures/auth/spec_with_apikey.json
OAS3 spec with an apiKey securityScheme (no OAuth scopes):
```json
{
  "openapi": "3.1.0",
  "info": {"title": "Test", "version": "1.0"},
  "components": {
    "securitySchemes": {
      "ApiKey": {"type": "apiKey", "in": "header", "name": "Authorization"}
    }
  },
  "paths": {}
}
```

### tests/fixtures/auth/spec_with_oauth.json
OAS3 spec with OAuth2 + scopes:
```json
{
  "openapi": "3.1.0",
  "info": {"title": "Test", "version": "1.0"},
  "components": {
    "securitySchemes": {
      "OAuth2": {
        "type": "oauth2",
        "flows": {
          "clientCredentials": {
            "tokenUrl": "https://auth.example.com/token",
            "scopes": {
              "read:items": "Read items",
              "write:items": "Write items"
            }
          }
        }
      }
    }
  },
  "paths": {}
}
```

### tests/fixtures/auth/home_pass.html
Simple homepage HTML with no auth keywords (to avoid triggering keywords from homepage in signal 1 tests).
<html><body>Welcome to Test API.</body></html>

## Test file: tests/test_scanner_auth.py

```python
import pytest
import respx
import httpx
from pathlib import Path
from agentsurface.scanners.auth import AuthScanner
from agentsurface.scanners.base import Target

FIXTURES = Path(__file__).parent / "fixtures" / "auth"
pytestmark = pytest.mark.asyncio
```

### Test 1: test_auth_pass_with_apikey — programmatic docs, apiKey spec
- Target: homepage="https://testapi.example.com", docs_url="https://docs.testapi.example.com", openapi_url="https://docs.testapi.example.com/openapi.json"
- Mock:
  - GET https://docs.testapi.example.com → 200, docs_pass.html, content_type="text/html"
  - GET https://testapi.example.com → 200, home_pass.html, content_type="text/html"
  - GET https://docs.testapi.example.com/openapi.json → 200, spec_with_apikey.json (mock it twice for the two fetches in signal 2 and signal 3)
- Assert: signal "auth.programmatic_key_issuance" → "pass" (found "api key" and "programmatic")
- Assert: signal "auth.security_schemes_defined" → "pass" (apiKey scheme found)
- Assert: signal "auth.scopes_enumerable" → "partial" (simple API key, no scopes)

### Test 2: test_auth_oauth_scopes — spec has OAuth2 with scopes
- Target same but openapi.json returns spec_with_oauth.json
- Assert: signal "auth.security_schemes_defined" → "pass"
- Assert: signal "auth.scopes_enumerable" → "pass" (OAuth2 scopes found)

### Test 3: test_auth_no_openapi — no openapi_url, dashboard only
- Target: homepage="https://testapi.example.com", docs_url="https://docs.testapi.example.com", openapi_url=None
- Mock docs → HTML with only "dashboard" keyword: <body>Get your key from the dashboard.</body>
- Mock homepage → home_pass.html
- Assert: signal "auth.security_schemes_defined" → "skip"
- Assert: signal "auth.programmatic_key_issuance" → "partial" (dashboard keyword only)

After writing, print exactly: {"item":"TASK-026-auth","files_changed":["tests/test_scanner_auth.py","tests/fixtures/auth/docs_pass.html","tests/fixtures/auth/spec_with_apikey.json","tests/fixtures/auth/spec_with_oauth.json","tests/fixtures/auth/home_pass.html"]}
PROMPT_EOF

# ── DISCOVERY scanner test ───────────────────────────────────────────────────
cat > /tmp/prompt_026_discovery.txt <<'PROMPT_EOF'
You are writing tests for TASK-026 (Discovery scanner) for the AgentSurface project.
Repo root: /mnt/c/Users/Aiden Antony/agentsurface/agentsurface/

## What to write
1. Fixture files under tests/fixtures/discovery/
2. Test file: tests/test_scanner_discovery.py

## Scanner behaviour (src/agentsurface/scanners/discovery.py)
The DiscoveryScanner fetches:

Signal 1 (discovery.agents_md, 0.30):
- SKIP if no github_org
- Tries: https://raw.githubusercontent.com/{github_org}/{repo}/main/AGENTS.md (and /master/AGENTS.md)
  repo candidates: target.slug, target.npm_package, target.pypi_package (in order)
- PASS if 200 and non-empty text

Signal 2 (discovery.mcp_server, 0.25):
- If mcp_server_url: fetch it → PASS if 200/401/405; SKIP on timeout; FAIL otherwise
- If no mcp_server_url: fetch homepage and docs_url, check for "mcp" or "model context protocol" keywords
  → PARTIAL if found; FAIL if not

Signal 3 (discovery.ai_plugin_json, 0.20):
- Fetches: {homepage_base}/.well-known/ai-plugin.json
- PASS if 200, valid JSON with plugin_fields (name_for_human/name_for_model/description_for_human/api)
- PARTIAL if 200 but missing fields
- FAIL if 404; SKIP on connection error

Signal 4 (discovery.robots_ai_policy, 0.25):
- Fetches: {homepage_base}/robots.txt
- Counts "user-agent:" lines matching AI crawlers: gptbot, claudebot, perplexitybot, anthropic-ai, chatgpt-user, google-extended, bytespider
- PASS if >= 2; PARTIAL if 1; FAIL if 0 but robots.txt exists; SKIP on non-200

## Fixture files to create

### tests/fixtures/discovery/agents_md.md
Content: "# AGENTS.md\n\nThis repo is AI-agent friendly.\n"

### tests/fixtures/discovery/ai_plugin.json
Valid plugin manifest:
```json
{"name_for_human": "Test API", "name_for_model": "testapi", "description_for_human": "A test API", "api": {"type": "openapi", "url": "https://testapi.example.com/openapi.json"}}
```

### tests/fixtures/discovery/robots_pass.txt
robots.txt with 2+ AI crawlers:
```
User-agent: *
Disallow:

User-agent: GPTBot
Disallow: /private/

User-agent: ClaudeBot
Disallow: /private/
```
(Note: scanner lowercases both the file content and the crawler names before matching)

### tests/fixtures/discovery/robots_fail.txt
robots.txt with no AI crawler entries:
```
User-agent: *
Disallow: /admin/
```

## Test file: tests/test_scanner_discovery.py

```python
import pytest
import respx
import httpx
from pathlib import Path
from agentsurface.scanners.discovery import DiscoveryScanner
from agentsurface.scanners.base import Target

FIXTURES = Path(__file__).parent / "fixtures" / "discovery"
pytestmark = pytest.mark.asyncio
```

### Test 1: test_discovery_pass — all signals pass
- Target: slug="testapi", homepage="https://testapi.example.com", docs_url="https://docs.testapi.example.com", github_org="testorg", npm_package="testapi"
- Mock:
  - GET https://raw.githubusercontent.com/testorg/testapi/main/AGENTS.md → 200, agents_md.md content
  - GET https://testapi.example.com → 200, b"<html><body>Welcome. We support MCP.</body></html>" (for mcp_server signal since no mcp_server_url)
  - GET https://docs.testapi.example.com → 200, b"<html><body>model context protocol is supported.</body></html>"
  - GET https://testapi.example.com/.well-known/ai-plugin.json → 200, ai_plugin.json content, content_type="application/json"
  - GET https://testapi.example.com/robots.txt → 200, robots_pass.txt content
- Assert: signal "discovery.agents_md" → "pass"
- Assert: signal "discovery.mcp_server" → "partial" (text mention, no URL)
- Assert: signal "discovery.ai_plugin_json" → "pass"
- Assert: signal "discovery.robots_ai_policy" → "pass"

### Test 2: test_discovery_fail — nothing found
- Target: slug="testapi", homepage="https://testapi.example.com", docs_url="https://docs.testapi.example.com", github_org="testorg", npm_package="testapi"
- Mock:
  - All AGENTS.md paths → 404 (try main and master for slug, npm, pypi)
  - GET homepage → 200, b"<html><body>Welcome.</body></html>" (no MCP keywords)
  - GET docs_url → 200, b"<html><body>Documentation.</body></html>"
  - GET /.well-known/ai-plugin.json → 404
  - GET /robots.txt → 200, robots_fail.txt content
- Assert: signal "discovery.agents_md" → "fail"
- Assert: signal "discovery.mcp_server" → "fail"
- Assert: signal "discovery.ai_plugin_json" → "fail"
- Assert: signal "discovery.robots_ai_policy" → "fail"
- Assert: score == 0.0

### Test 3: test_discovery_no_github — no github_org, agents_md skipped
- Target: github_org=None, homepage="https://testapi.example.com", docs_url="https://docs.testapi.example.com"
- Mock homepage and docs for MCP check → no MCP keywords
- Mock /.well-known/ai-plugin.json → raise httpx.ConnectError
- Mock /robots.txt → 200, robots_pass.txt
- Assert: signal "discovery.agents_md" → "skip"
- Assert: signal "discovery.ai_plugin_json" → "skip"
- Assert: signal "discovery.robots_ai_policy" → "pass"

## Implementation notes
- For test 2: mock ALL possible AGENTS.md URLs (main/master branches, slug/npm/pypi candidates)
  - Target has slug="testapi", npm_package="testapi" — so 4 URLs to mock (slug+main, slug+master, npm+main, npm+master — but slug == npm, so effectively 2 unique URLs but the scanner may try them as separate requests)
  - Mock: https://raw.githubusercontent.com/testorg/testapi/main/AGENTS.md → 404
  - Mock: https://raw.githubusercontent.com/testorg/testapi/master/AGENTS.md → 404
- For robots_pass.txt: write it lowercase to file (scanner lowercases the file lines before matching)

After writing, print exactly: {"item":"TASK-026-discovery","files_changed":["tests/test_scanner_discovery.py","tests/fixtures/discovery/agents_md.md","tests/fixtures/discovery/ai_plugin.json","tests/fixtures/discovery/robots_pass.txt","tests/fixtures/discovery/robots_fail.txt"]}
PROMPT_EOF

# ── Fan-out execution (concurrency 3) ────────────────────────────────────────
declare -A JOBS

running_count() {
  local count=0
  for pid in "${JOBS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      ((count++)) || true
    fi
  done
  echo $count
}

for ITEM in \
  "TASK-026-openapi:/tmp/prompt_026_openapi.txt" \
  "TASK-026-docs:/tmp/prompt_026_docs.txt" \
  "TASK-026-sdk:/tmp/prompt_026_sdk.txt" \
  "TASK-026-errors:/tmp/prompt_026_errors.txt" \
  "TASK-026-auth:/tmp/prompt_026_auth.txt" \
  "TASK-026-discovery:/tmp/prompt_026_discovery.txt"
do
  IFS=':' read -r task_id prompt_file <<< "${ITEM}"

  while [ "$(running_count)" -ge 3 ]; do
    sleep 5
  done

  echo "[fanout-tests] Launching ${task_id}..."
  run_one "${task_id}" "${prompt_file}" &
  JOBS["${task_id}"]=$!
done

wait
echo "[fanout-tests] All test jobs complete."
