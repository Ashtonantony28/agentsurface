<!--
SPDX-License-Identifier: CC-BY-4.0
Copyright (c) 2026 AgentSurface Contributors
This document is licensed under Creative Commons Attribution 4.0 International.
See https://creativecommons.org/licenses/by/4.0/
-->

# AgentSurface Scoring Framework

## Overview

The **Agent Readiness Index (ARI)** is a 0–100 composite score that measures how
well a developer API is structured for consumption by autonomous software agents
(LLM-based tools, coding assistants, multi-step orchestrators, and similar
automated clients). It assesses six independent dimensions: the quality of the
OpenAPI specification, the accessibility of developer documentation, the ergonomics
of official SDKs, the quality of error responses, the ergonomics of authentication,
and the discoverability of agent-specific surfaces. ARI is intended for API
producers who want objective signal on where to invest, for developer-tools
teams evaluating API integrations, and for researchers studying the agent-readiness
landscape of the public API ecosystem. All input data is fetched from public
surfaces only; no authentication is required to produce a score.

---

## How Scores Work

### Scale

Every signal, dimension, and the overall ARI are expressed on a **0–100** scale.

- A signal scores **100** (PASS), **50** (PARTIAL), or **0** (FAIL or SKIP).
- A dimension score is the weighted average of its constituent signal scores,
  where weights are the per-signal fractions defined in each dimension section.
  If a signal is SKIP (unapplicable or not checkable), its weight is redistributed
  proportionally across the remaining active signals in that dimension.
- The **overall ARI** is the weighted average of the six dimension scores, using
  the dimension weights shown below (which sum to 1.0).

### Dimension weights

| Dimension                  | Weight |
|----------------------------|--------|
| OpenAPI Quality            | 20%    |
| Docs Accessibility         | 20%    |
| SDK Ergonomics             | 15%    |
| Error UX                   | 15%    |
| Auth Ergonomics            | 15%    |
| Discovery Surface          | 15%    |

### Grade table

Letter grades with +/- modifiers are assigned from the overall ARI score.
Within each band the range is divided into equal thirds: the top third earns `+`,
the middle earns the plain letter, and the bottom third earns `-`.

| Grade | Score range | Notes                                  |
|-------|-------------|----------------------------------------|
| A+    | 97–100      | Top third of 90–100 band               |
| A     | 93–96       | Middle third of 90–100 band            |
| A-    | 90–92       | Bottom third of 90–100 band            |
| B+    | 85–89       | Top third of 75–89 band                |
| B     | 80–84       | Middle third of 75–89 band             |
| B-    | 75–79       | Bottom third of 75–89 band             |
| C+    | 70–74       | Top third of 60–74 band                |
| C     | 65–69       | Middle third of 60–74 band             |
| C-    | 60–64       | Bottom third of 60–74 band             |
| D+    | 53–59       | Top third of 40–59 band                |
| D     | 47–52       | Middle third of 40–59 band             |
| D-    | 40–46       | Bottom third of 40–59 band             |
| F     | 0–39        | No modifier                            |

The thresholds above are computed from `compute_grade()` in
`src/agentsurface/framework.py` using exact floating-point arithmetic; the
ranges in the table are integer approximations for readability.

### Float precision

All reported scores are rounded to **one decimal place**. This applies to
dimension scores, the overall ARI, and any intermediate values written to
output files. The rounding is applied once at the final aggregation step; it
is not applied to intermediate calculations.

---

## Dimension 1: OpenAPI Quality (20%)

### What it measures

This dimension checks whether a machine-readable API contract exists, whether it
is structurally valid, and whether it contains the information an agent needs to
make calls without human assistance: server base URLs, authentication schemes,
error response schemas, and concrete examples. A well-formed OpenAPI document
allows an agent to discover endpoints, construct valid requests, and handle
failure modes without consulting prose documentation.

### Signals

#### Spec discoverable (20% of this dimension)

| Status  | Meaning |
|---------|---------|
| PASS    | A `.json` or `.yaml` OpenAPI document is reachable at a public URL. The URL may be supplied explicitly in the seed data or found by probing common paths (`/openapi.json`, `/openapi.yaml`, `/swagger.json`, `/api/openapi.json`). |
| PARTIAL | A link to the spec is found in the HTML documentation but the raw spec URL does not return a parseable document on first fetch. |
| FAIL    | No OpenAPI document is discoverable. |

**Why it matters for agents.** Without a machine-readable spec, an agent must
parse prose documentation or rely on hard-coded knowledge to construct requests.
A discoverable spec is the prerequisite for all other signals in this dimension.

---

#### Valid OAS 3.x (20%)

| Status  | Meaning |
|---------|---------|
| PASS    | The fetched document parses as valid OpenAPI Specification version 3.0.x or 3.1.x (validated against the relevant JSON Schema). |
| PARTIAL | The document identifies itself as OAS 3.x but contains schema validation errors that do not prevent parsing (e.g., non-standard extension fields at the root level, minor `$ref` inconsistencies). |
| FAIL    | The document is Swagger 2.x, unparseable, or fails OAS 3.x schema validation with structural errors. |

**Why it matters for agents.** Tooling that auto-generates API clients or
function-call schemas from OpenAPI documents requires OAS 3.x. Swagger 2.x is
not supported by most modern agent frameworks.

---

#### Has servers[] (15%)

| Status  | Meaning |
|---------|---------|
| PASS    | The document's top-level `servers` array contains at least one entry with a non-empty `url` field. |
| PARTIAL | A `servers` array is present but the URL is a template placeholder (e.g., `{scheme}://{host}/`) with no default values provided. |
| FAIL    | `servers` is absent or empty. |

**Why it matters for agents.** Without `servers`, an agent cannot determine the
base URL for API calls from the spec alone. It must infer the base URL from
documentation, which is error-prone and requires additional reasoning.

---

#### Auth in securitySchemes (20%)

| Status  | Meaning |
|---------|---------|
| PASS    | The document's `components.securitySchemes` object contains at least one named scheme, and at least one operation or the global `security` field references it. |
| PARTIAL | `securitySchemes` is defined but not referenced by any operation or global `security` object. |
| FAIL    | `securitySchemes` is absent or empty. |

**Why it matters for agents.** An agent must be able to read the authentication
requirements from the spec to insert the correct credential type (API key, Bearer
token, OAuth2) into requests. Without this, the agent must guess the auth scheme
or fail.

---

#### Error response schemas (15%)

| Status  | Meaning |
|---------|---------|
| PASS    | At least 50% of operations in the spec define a response schema for at least one 4xx or 5xx status code. |
| PARTIAL | Fewer than 50% but at least one operation defines an error response schema. |
| FAIL    | No operation defines any error response schema. |

**Why it matters for agents.** Agents need to interpret error responses
programmatically to decide whether to retry, adjust the request, or surface a
human-readable message. Undefined error schemas force agents to rely on
heuristics or fail silently.

---

#### Example coverage ≥50% (10%)

| Status  | Meaning |
|---------|---------|
| PASS    | At least 50% of request body schemas or parameter definitions contain an `example` or `examples` field. |
| PARTIAL | Between 10% and 50% of schemas or parameter definitions contain examples. |
| FAIL    | Fewer than 10% of schemas or parameter definitions contain examples. |

**Why it matters for agents.** Examples allow agents and code-generation tools
to produce valid sample requests without needing to infer values from schema
constraints. Low example coverage increases hallucination risk in agent-generated
API calls.

---

#### Operation IDs present ≥80% (10%)

| Status  | Meaning |
|---------|---------|
| PASS    | At least 80% of operations in the spec have a non-empty `operationId` field. |
| PARTIAL | Between 50% and 79% of operations have an `operationId`. |
| FAIL    | Fewer than 50% of operations have an `operationId`, or the spec is not available. |

**Why it matters for agents.** SDK generators, function-call schemas, and agent
tooling rely on `operationId` to produce stable, human-readable method names.
Without `operationId`, generated code uses path-based names that are brittle and
verbose, making it harder for agents to select the right operation.

---

#### Response descriptions present ≥80% (10%)

| Status  | Meaning |
|---------|---------|
| PASS    | At least 80% of response objects (across all operations) have a non-empty `description` field. |
| PARTIAL | Between 50% and 79% of response objects have a description. |
| FAIL    | Fewer than 50% of response objects have a description, or the spec is not available. |

**Why it matters for agents.** Response descriptions tell an agent what each
status code means in context — distinguishing a successful partial response from
an error, or explaining what data is returned. Missing descriptions force agents
to infer meaning from status codes alone.

---

## Dimension 2: Docs Accessibility (20%)

### What it measures

This dimension checks whether developer documentation is structured for
machine consumption. It focuses on three properties: whether the API provides
dedicated machine-readable documentation files following the `llms.txt`
convention, whether the HTML documentation is dense with text (rather than
requiring JavaScript execution to reveal content), and whether documentation
is gated behind JS-only rendering that prevents automated retrieval.

### Signals

#### /llms.txt returns 200 (30%)

| Status  | Meaning |
|---------|---------|
| PASS    | A GET request to `<docs_root>/llms.txt` returns HTTP 200 with a non-empty body. |
| PARTIAL | The file exists and returns 200 but is under 200 bytes (likely a stub). |
| FAIL    | The path returns any non-200 status, or no docs root is known. |

**Why it matters for agents.** The `llms.txt` convention provides a
curated, concise entry point for LLM-based tools that need to understand an
API's capabilities without crawling the entire docs site.

---

#### /llms-full.txt or .md variant (20%)

| Status  | Meaning |
|---------|---------|
| PASS    | One of the following paths returns HTTP 200: `/llms-full.txt`, `/llms.md`, `/llms-full.md`. |
| PARTIAL | The path returns 200 but is under 1 KB (likely a stub or redirect). |
| FAIL    | None of the variant paths return 200. |

**Why it matters for agents.** The full-text variant provides comprehensive
API documentation in a flat, parseable format. It allows agents to retrieve
complete reference material in a single request.

---

#### HTML content density ≥20% text (25%)

| Status  | Meaning |
|---------|---------|
| PASS    | On a sampled documentation page, the ratio of visible text characters to total HTML characters is ≥20%. |
| PARTIAL | The ratio is between 5% and 20%. |
| FAIL    | The ratio is below 5%, or the page body is empty after stripping script and style tags. |

**Why it matters for agents.** Low content density indicates that the page
relies heavily on client-side JavaScript to render documentation. Pages that
deliver minimal HTML server-side are not reliably parseable by agents that
fetch and process HTML directly.

---

#### No JS-only content gates (25%)

| Status  | Meaning |
|---------|---------|
| PASS    | The sampled documentation page delivers substantive reference content (at least one API endpoint or code sample) in the server-rendered HTML, without requiring JavaScript execution. |
| PARTIAL | Some content is accessible without JS, but navigating to individual endpoint documentation requires JS-rendered routing. |
| FAIL    | The entire documentation body is rendered client-side; the server-rendered HTML contains no endpoint or parameter documentation. |

**Why it matters for agents.** An agent using a standard HTTP fetch cannot
execute JavaScript. If all documentation is behind a JS rendering step, the
agent cannot retrieve documentation programmatically.

---

#### Changelog discoverable (15%)

| Status  | Meaning |
|---------|---------|
| PASS    | A changelog, release notes, or "what's new" page is reachable at a well-known path on the docs domain (`/changelog`, `/releases`, `/release-notes`, `/whats-new`) or as a GitHub releases page with at least one release. |
| FAIL    | No changelog page is found at any probed path. |

**Why it matters for agents.** Agents that manage integrations need to track
API changes — deprecations, breaking changes, and new features. A discoverable
changelog page allows agents (or the developers directing them) to check for
relevant updates without subscribing to mailing lists or monitoring social media.

---

#### sitemap.xml present (10%)

| Status  | Meaning |
|---------|---------|
| PASS    | A GET request to `<docs_domain>/sitemap.xml` returns HTTP 200 and the response body contains at least one `<url>` entry. |
| FAIL    | The path returns a non-200 status, the body is not a valid sitemap, or no docs domain is configured. |

**Why it matters for agents.** A machine-readable sitemap allows agents and
documentation crawlers to enumerate all available documentation pages without
following hyperlinks. This is the standard mechanism for making a site
programmatically explorable.

---

## Dimension 3: SDK Ergonomics (15%)

### What it measures

This dimension checks whether the API provides official, well-documented SDKs
for the two most widely used programming languages in agent development (Python
and Node.js/TypeScript), and whether those SDKs are easy to get started with.
Signal checks are based on public package registry metadata and README content.

### Signals

#### npm package exists (25%)

| Status  | Meaning |
|---------|---------|
| PASS    | A package matching the `npm_package` field in the seed data (or a discoverable official package) exists on the npm registry and is not deprecated. |
| PARTIAL | A package exists but is deprecated or has not been published in the last 24 months. |
| FAIL    | No npm package is found. |

**Why it matters for agents.** Node.js/TypeScript is the dominant environment
for many agent frameworks. An official npm package reduces integration friction
and provides typed method signatures.

---

#### PyPI package exists (25%)

| Status  | Meaning |
|---------|---------|
| PASS    | A package matching the `pypi_package` field in the seed data (or a discoverable official package) exists on PyPI and is not yanked. |
| PARTIAL | A package exists but has not received a release in the last 24 months or all versions are yanked. |
| FAIL    | No PyPI package is found. |

**Why it matters for agents.** Python is the primary language for LLM-based
agent development. An official PyPI package with a stable API is the
lowest-friction integration path.

---

#### Install one-liner in README first 20 lines (20%)

| Status  | Meaning |
|---------|---------|
| PASS    | The README (fetched from the GitHub repository's default branch) contains an `npm install`, `pip install`, or `uv add` command within the first 20 lines. |
| PARTIAL | An install command exists in the README but appears after line 20. |
| FAIL    | No install command is found in the README. |

**Why it matters for agents.** Automated tooling that parses README files to
generate scaffolding or dependency lists expects install instructions to appear
at the top of the file, where they are most likely to be found without full
document parsing.

---

#### Typed (TS types or Python stubs) (15%)

| Status  | Meaning |
|---------|---------|
| PASS    | The npm package includes TypeScript type definitions (`.d.ts` files in the package or a `@types/` companion), or the PyPI package includes PEP 561-compliant type stubs (`py.typed` marker or bundled `.pyi` files). |
| PARTIAL | Types are available for one of the two languages but not the other (when both SDKs exist). |
| FAIL    | Neither SDK ships type information. |

**Why it matters for agents.** Type information allows code-generation models to
produce correct method signatures and parameter names. Without types, agents
must infer parameter shapes from prose documentation.

---

#### README quickstart ≤300 lines (15%)

| Status  | Meaning |
|---------|---------|
| PASS    | The README file is 300 lines or fewer, or a dedicated quickstart section that makes a complete API call fits within 300 lines from the top of the file. |
| PARTIAL | The README is between 301 and 600 lines. |
| FAIL    | The README is longer than 600 lines without a clear quickstart section in the first 300 lines. |

**Why it matters for agents.** A long README increases the token cost of
including it in an agent's context window. A concise quickstart helps both
human developers and automated tools get to a working integration faster.

---

#### Async client available (15%)

| Status  | Meaning |
|---------|---------|
| PASS    | Both the npm README and the PyPI package description mention async support (`async`, `asyncio`, `async/await`, `Promise`), or the package name includes `-async`. |
| PARTIAL | Only one of the two package ecosystems (npm or PyPI) mentions async support. |
| FAIL    | Neither ecosystem mentions async support. |
| SKIP    | No npm or PyPI package is configured. |

**Why it matters for agents.** Agent frameworks are typically built on async
runtimes. A synchronous-only SDK blocks the event loop, limiting concurrency
and causing timeouts in long-running agent workflows. Async client support is
a prerequisite for high-throughput agent integrations.

---

#### SDK versions in sync (10%)

| Status  | Meaning |
|---------|---------|
| PASS    | The latest npm version and latest PyPI version match at the major.minor level (patch differences are acceptable). |
| PARTIAL | The versions differ at the minor level but the major version is within 1. |
| FAIL    | The major versions diverge by more than 1, indicating the two ecosystems are not maintained in sync. |
| SKIP    | Only one package ecosystem is present, or versions could not be parsed. |

**Why it matters for agents.** Major version divergence between language SDKs
indicates that one ecosystem is lagging — new features or breaking changes may
not be reflected in both. Agents that operate across languages may encounter
behavior differences that make cross-language workflows unreliable.

---

## Dimension 4: Error UX (15%)

### What it measures

This dimension evaluates the quality of error responses returned by the API
at runtime. A well-structured error response allows an agent to identify
what went wrong, decide on a recovery strategy, and surface a useful message
to a human operator. Checks are performed by issuing known-bad requests to
the API's public endpoints and inspecting the response.

### Signals

#### Error response is JSON (25%)

| Status  | Meaning |
|---------|---------|
| PASS    | The API returns `Content-Type: application/json` (or `application/problem+json`) for a 4xx error response. |
| PARTIAL | The response body is valid JSON but the Content-Type header does not declare JSON. |
| FAIL    | The error response is HTML, plain text, or empty. |

**Why it matters for agents.** An agent cannot reliably parse a plain-text or
HTML error message. JSON error responses are the prerequisite for all other
error-quality signals.

---

#### Includes machine-readable code field (25%)

| Status  | Meaning |
|---------|---------|
| PASS    | The JSON error body includes a stable, non-numeric string field (commonly `code`, `error`, `error_code`, or `type`) that uniquely identifies the error condition. |
| PARTIAL | A code-like field is present but its value is the HTTP status code as a string, or the field name is unstable across endpoints. |
| FAIL    | No such field is present. |

**Why it matters for agents.** Human-readable `message` fields are not
reliably parseable. A stable error code allows an agent to branch on specific
failure conditions (e.g., `rate_limit_exceeded` vs. `invalid_parameter`)
without string matching.

---

#### Includes docs URL (20%)

| Status  | Meaning |
|---------|---------|
| PASS    | The JSON error body includes a URL field (commonly `docs_url`, `doc_url`, `help_url`, or a `links` object) that points to documentation specific to the error condition. |
| PARTIAL | A URL is included but points to a general troubleshooting page rather than the specific error. |
| FAIL    | No URL is included in the error body. |

**Why it matters for agents.** When an agent encounters an unrecognized error
code, a direct link to documentation allows it to retrieve context without
needing to search the docs site.

---

#### Names offending field for validation errors (15%)

| Status  | Meaning |
|---------|---------|
| PASS    | For a 400/422 validation error response, the body identifies the specific field(s) that failed validation, either as a top-level `param` or `field` key or as an array of per-field objects. |
| PARTIAL | Offending fields are named in the human-readable `message` text but not in a structured field. |
| FAIL    | The error response does not indicate which field caused the validation failure. |

**Why it matters for agents.** An agent generating API calls from a schema
needs to know which field to correct when a request fails validation. Without
field-level error attribution, the agent must re-attempt with guesswork.

---

#### Status code is semantically correct (15%)

| Status  | Meaning |
|---------|---------|
| PASS    | The HTTP status code returned matches the semantic meaning of the error: 400 for malformed requests, 401 for missing/invalid credentials, 403 for insufficient permissions, 404 for unknown resources, 422 for unprocessable content, 429 for rate limiting, 5xx for server errors. |
| PARTIAL | The status code is in the correct class (4xx vs. 5xx) but not the correct specific code. |
| FAIL    | The API returns 200 for error responses, or returns a semantically incorrect status code class. |

**Why it matters for agents.** Agent retry and escalation logic depends on the
HTTP status code class. Returning 200 for errors or conflating 401 and 403
causes agents to take incorrect recovery actions.

---

#### Request ID in error response (15%)

| Status  | Meaning |
|---------|---------|
| PASS    | The JSON error response body or response headers contain a field matching `request_id`, `requestId`, `trace_id`, `traceId`, `x-request-id`, or `correlation_id`. |
| FAIL    | The body is JSON but none of the expected correlation ID fields are present. |
| SKIP    | The probe returned no JSON body (HTML marketing page, network error, or empty response). |

**Why it matters for agents.** When an agent encounters an error, it must be
able to report the incident to human operators. A request ID or trace ID allows
the API provider to look up the exact request in their logs, dramatically
reducing debugging time in automated pipelines.

---

#### 4xx vs 5xx correctly distinguished (10%)

| Status  | Meaning |
|---------|---------|
| PASS    | A probe for a nonexistent resource returns HTTP 404 (not 400, not 500). |
| FAIL    | The probe returns any status code other than 404. |
| SKIP    | The response is HTML (indicating the probe hit a marketing site, not an API endpoint). |

**Why it matters for agents.** An agent's retry and escalation logic differs for
client errors (4xx — the agent should fix the request) versus server errors (5xx —
the agent should retry or escalate). Returning 400 for a not-found resource, or
500 for a bad request, confuses agents that use status codes to drive their error
recovery strategy. HTTP 404 specifically signals "this resource does not exist,"
which is the correct semantic for a probe to a nonexistent ID.

---

## Dimension 5: Auth Ergonomics (15%)

### What it measures

This dimension evaluates how easy it is for an agent or automated system to
configure authentication. It checks whether API key issuance is documented
programmatically, whether the OpenAPI spec accurately describes the key model,
and whether the permission model is enumerable without reading prose.

### Signals

#### Programmatic key issuance documented (35%)

| Status  | Meaning |
|---------|---------|
| PASS    | The documentation includes instructions for creating an API key via an API endpoint, a CLI tool, or a service account mechanism, without requiring human interaction in a web dashboard. |
| PARTIAL | API key creation is documented but requires a manual step in the dashboard (e.g., clicking a button to generate a key) with no programmatic alternative. |
| FAIL    | No documentation of key creation is found, or keys are only obtainable through a sales process. |

**Why it matters for agents.** Agents deployed in automated pipelines (CI/CD,
multi-agent orchestration) must be able to provision credentials without human
interaction. Dashboard-only key creation blocks non-interactive deployments.

---

#### Key model in securitySchemes (35%)

| Status  | Meaning |
|---------|---------|
| PASS    | The OpenAPI spec's `securitySchemes` object accurately describes the credential type(s) in use (e.g., `apiKey` with the correct `in` and `name` fields, or `http` with `scheme: bearer`). |
| PARTIAL | A `securitySchemes` entry exists but the type or placement does not match the actual credential mechanism (e.g., the spec says `apiKey` in `query` but the API requires it in the `Authorization` header). |
| FAIL    | `securitySchemes` is absent or empty. |

**Why it matters for agents.** Agents that auto-configure authentication from
the OpenAPI spec must have an accurate machine-readable description of the
credential format. A mismatch causes authentication failures that are
difficult to debug automatically.

---

#### Scopes/permissions enumerable (30%)

| Status  | Meaning |
|---------|---------|
| PASS    | All available permission scopes are listed in either the OpenAPI spec (`securitySchemes[*].flows[*].scopes`) or in a dedicated documentation page that is parseable (not JS-rendered). |
| PARTIAL | Some scopes are documented, but the documentation is incomplete or only covers a subset of available permissions. |
| FAIL    | Scopes or permission levels are not documented in any machine-accessible form. |

**Why it matters for agents.** An agent requesting least-privilege credentials
must be able to enumerate available scopes to request only what is needed.
Undocumented scopes force either over-permissioning (requesting broad access)
or failure (missing a required scope).

---

#### M2M / service account docs discoverable (15%)

| Status  | Meaning |
|---------|---------|
| PASS    | A documentation page for machine-to-machine or service account authentication is reachable at one of the standard paths: `/docs/service-accounts`, `/docs/machine-to-machine`, `/docs/m2m`, `/docs/api-keys/service`, or `/docs/oauth/client-credentials`. |
| FAIL    | None of the probed paths return HTTP 200. |
| SKIP    | No `docs_url` is configured. |

**Why it matters for agents.** Agents deployed in automated pipelines (CI/CD,
multi-agent orchestration) use machine-to-machine (M2M) or service account
credentials — not user-delegated OAuth flows. Documented M2M paths indicate
that the API provider has considered non-interactive, fully automated clients,
making it easier for agent builders to understand the correct credential strategy.

---

#### Webhook signing documented (15%)

| Status  | Meaning |
|---------|---------|
| PASS    | A documentation page at `/docs/webhooks`, `/webhooks`, or `/docs/events` returns HTTP 200 and the page body contains "webhook" alongside "signing", "secret", or "HMAC". |
| FAIL    | No matching page is found, or the page does not contain signing-related content. |
| SKIP    | No `docs_url` is configured. |

**Why it matters for agents.** Agents that consume webhook events must verify
the authenticity of incoming payloads to avoid spoofed events. Documented webhook
signing (HMAC, shared secrets) is the standard mechanism. Without it, an agent
cannot safely act on webhook data in an automated pipeline.

---

## Dimension 6: Discovery Surface (15%)

### What it measures

This dimension checks for artifact types specifically intended to help agents
and automated tools discover and understand an API: the presence of an
`AGENTS.md` file in the source repository, a reachable MCP server endpoint,
a `.well-known/ai-plugin.json` manifest, and a `robots.txt` that makes
explicit policy decisions about AI crawlers. These are emerging conventions;
partial credit is given for any present artifact.

### Signals

#### AGENTS.md at repo root (30%)

| Status  | Meaning |
|---------|---------|
| PASS    | A file named `AGENTS.md` exists at the root of the API's primary GitHub repository (checked via the GitHub raw content URL on the default branch). |
| PARTIAL | An `AGENTS.md` file exists but is under 100 bytes (likely a placeholder). |
| FAIL    | No `AGENTS.md` is found, or no GitHub repository is associated with the API. |

**Why it matters for agents.** `AGENTS.md` is a convention for API providers
to document agent-specific guidance: which endpoints are safe for automated
access, rate-limit expectations, recommended authentication patterns, and
links to machine-readable specs.

---

#### MCP server documented/reachable (25%)

| Status  | Meaning |
|---------|---------|
| PASS    | An MCP (Model Context Protocol) server URL is specified in the seed data and returns a valid MCP capabilities response, or MCP server documentation is linked from `AGENTS.md` or `llms.txt`. |
| PARTIAL | An MCP server URL is documented but the endpoint is unreachable or returns an unexpected response. |
| FAIL    | No MCP server is documented or reachable. |

**Why it matters for agents.** MCP servers expose API functionality as
structured tool definitions that LLM-based agents can call directly. A
reachable MCP server eliminates the need for agents to parse OpenAPI specs
and generate their own tool wrappers.

---

#### /.well-known/ai-plugin.json (20%)

| Status  | Meaning |
|---------|---------|
| PASS    | A GET request to `<homepage>/.well-known/ai-plugin.json` returns HTTP 200 with a JSON body containing at minimum a `name_for_model` field. |
| PARTIAL | The file returns 200 but does not conform to the plugin manifest schema (missing required fields). |
| FAIL    | The path returns a non-200 status. |

**Why it matters for agents.** The `ai-plugin.json` manifest is the OpenAI
plugin convention for self-describing API capabilities to AI systems. Its
presence indicates that the API provider has explicitly considered agent
integration.

---

#### robots.txt distinguishes AI crawlers (25%)

| Status  | Meaning |
|---------|---------|
| PASS    | The `robots.txt` file at the API's documentation root includes at least one directive that explicitly addresses AI crawlers by name (e.g., `User-agent: GPTBot`, `User-agent: ClaudeBot`, `User-agent: Googlebot-Extended`) with an `Allow` or `Disallow` rule. |
| PARTIAL | `robots.txt` exists but only contains generic `User-agent: *` rules without AI-specific entries. |
| FAIL    | `robots.txt` is absent or returns a non-200 status. |

**Why it matters for agents.** A `robots.txt` that explicitly addresses AI
crawlers communicates the API provider's intent regarding automated access.
`Allow` rules for AI crawlers signal that the documentation is intended to
be machine-consumed; `Disallow` rules signal that crawling is not sanctioned.
Either explicit policy is preferable to silence.

---

#### llms.txt has disallow rules (10%)

| Status  | Meaning |
|---------|---------|
| PASS    | The `llms.txt` file exists and contains at least one `disallow:` directive. |
| PARTIAL | The `llms.txt` file exists but contains no `disallow:` directives. |
| FAIL    | No `llms.txt` file is found at the homepage or docs domain. |
| SKIP    | The homepage is not reachable or not configured. |

**Why it matters for agents.** `disallow:` entries in `llms.txt` indicate that
the API provider has deliberately curated their agent surface — specifying which
endpoints or sections should not be accessed by automated tools. This deliberate
curation reduces the risk of agents accessing confidential or destructive
endpoints and signals a mature approach to agent integration.

---

#### Changelog feed (RSS/Atom) present (10%)

| Status  | Meaning |
|---------|---------|
| PASS    | An RSS or Atom feed for releases or changelog is reachable at `<homepage>/feed.xml`, `<homepage>/atom.xml`, `<homepage>/rss.xml`, `<homepage>/feed`, or as a GitHub releases Atom feed at `https://github.com/<org>/<repo>/releases.atom`. |
| FAIL    | No feed is found at any probed URL. |
| SKIP    | No homepage is configured. |

**Why it matters for agents.** A structured changelog feed allows automated
tooling to subscribe to API changes without polling a web page. Agents that
manage integrations can check the feed on a schedule to detect breaking changes,
new features, or deprecation notices — enabling proactive maintenance of
integration code.

---

## Reproducibility

AgentSurface is designed so that the same inputs always produce the same outputs.

### What is recorded

Every HTTP request made during a scan is stored as a `FetchRecord` containing:
- The request URL
- The HTTP status code
- The response size in bytes
- The UTC timestamp at fetch time
- The AgentSurface version that made the request

These records are embedded in the `provenance` field of every `Report` object
and written to the JSON output file. This means any score can be audited by
reviewing which URLs were fetched, what they returned, and when.

### Determinism

Given identical fetch results, the scoring functions are purely deterministic:

- `signal_score_to_float()` maps `SignalStatus` to a fixed float.
- `compute_dimension_score()` computes a weighted average with no random elements.
- `compute_overall_score()` applies `round(..., 1)` once at the final step.
- `compute_grade()` applies exact arithmetic with no floating-point branching
  other than `>=` comparisons against fixed thresholds.

There are no random seeds, no time-based branches in scoring logic, and no
external lookups during score computation. All non-determinism is isolated to
the network fetch layer.

### Test mode

When running under `pytest`, the test suite uses the `respx` library to intercept
all HTTP calls and replay pre-recorded fixtures from `tests/fixtures/`. Real
network sockets are blocked by a socket guard in `tests/conftest.py`. Fixtures
record a fixed timestamp so that time-dependent fields in provenance output are
stable across test runs.

---

## How to Reproduce

To reproduce any score in the AgentSurface dataset:

```bash
# 1. Clone the repository
git clone https://github.com/your-org/agentsurface.git
cd agentsurface

# 2. Install the package and its dependencies
uv pip install -e .

# 3. Run a scan for a specific API slug
agentsurface scan stripe
```

The scan fetches all public surfaces, computes scores, and writes output to
`data/reports/stripe.json` and `data/reports/stripe.md`.

To reproduce the full leaderboard:

```bash
agentsurface scan-all
agentsurface build-site
```

Output is written to `site/`.

Note that scores may differ from a previous run if the API provider has updated
their public surfaces since the prior scan. The `provenance` block in each JSON
report records the exact fetch timestamps so differences can be attributed to
specific URL changes.

---

## How to Dispute a Score

If you believe a score is incorrect — because a signal check produced a false
result, because the seed data contains a wrong URL, or because the scoring logic
does not correctly handle your API's implementation — open a GitHub issue with
evidence at:

**https://github.com/your-org/agentsurface/issues/new**

Include in the issue:

1. The API slug and the dimension or signal in dispute.
2. The signal status you received (PASS / PARTIAL / FAIL) and what you believe
   it should be.
3. Evidence: a URL returning the content in question, a copy of the relevant
   section of your OpenAPI spec, or a screenshot of the documentation.
4. The `provenance` block from the relevant `data/reports/<slug>.json` file,
   if available.

Maintainers will re-run the scan against the corrected inputs and update the
score. All changes to seed data or scoring logic that affect published scores
are logged in the repository's commit history.

---

## What This Framework Does NOT Measure

The following are explicitly out of scope for the ARI:

**Protocol coverage.** The framework only evaluates REST/HTTP APIs documented
with OpenAPI. GraphQL APIs, gRPC services, WebSocket APIs, and MQTT brokers are
not scored.

**Authenticated surfaces.** All checks operate on public endpoints and
unauthenticated documentation. The quality of responses behind authentication,
the correctness of permission enforcement, and the behavior of admin or
management APIs are not measured.

**Real-time performance.** Response latency, throughput, uptime, and SLA
compliance are not measured. A single fetch may or may not be representative
of typical API performance.

**API correctness.** The framework does not verify that the API behaves as
documented. It checks the existence and structure of documentation artifacts,
not the semantic correctness of the API implementation.

**UX of web dashboards.** The ergonomics of the developer dashboard, the
onboarding flow, and any web UI required for account management are not measured.

**Pricing and rate limits.** The generosity of free tiers, the clarity of
pricing pages, and published rate limit values are not measured.

**Security posture.** The framework does not evaluate TLS configuration, CORS
policies, input sanitization, or any other security property of the API.

**Coverage completeness.** The framework scores APIs based on a fixed set of
signals for each dimension. An API may have agent-friendly properties not
captured by any signal (e.g., a high-quality changelog or a sandbox environment)
that do not affect the score.

**Localization and accessibility.** Documentation language, internationalization
support, and web accessibility compliance of documentation sites are not
measured.

**SDK functionality.** The SDK ergonomics dimension checks for the existence and
packaging quality of official SDKs; it does not evaluate the correctness,
coverage, or API design quality of the SDK itself.
