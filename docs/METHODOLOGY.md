<!--
SPDX-License-Identifier: CC-BY-4.0
Copyright (c) 2026 AgentSurface Contributors
This document is licensed under Creative Commons Attribution 4.0 International.
See https://creativecommons.org/licenses/by/4.0/
-->

# AgentSurface Methodology

This document explains the design decisions behind the Agent Readiness Index (ARI):
how scores are made reproducible, why specific sampling strategies were chosen, why
scoring is per-domain rather than per-endpoint, why the six dimensions were selected,
and what the framework deliberately does not measure.

---

## 1. Reproducibility Guarantee

AgentSurface is designed to produce deterministic output: given the same target
configuration and the same set of network responses, every run produces bit-identical
JSON.

### Score computation is purely functional

The scoring pipeline contains no random elements:

- `signal_score_to_float()` maps each `SignalStatus` (PASS / PARTIAL / FAIL / SKIP)
  to a fixed float (100.0 / 50.0 / 0.0 / skipped).
- `compute_dimension_score()` computes a weighted average with no random elements.
  When a signal is SKIP, its weight is redistributed proportionally among the
  remaining active signals; the redistribution is deterministic.
- `compute_overall_score()` applies `round(..., 1)` exactly once at the final
  aggregation step, not to intermediate values. Python's built-in `round()` uses
  banker's rounding (round half to even), which avoids systematic bias and is
  reproducible across platforms.
- `compute_grade()` applies exact arithmetic with `>=` comparisons against fixed
  numeric thresholds. There is no floating-point branching that could diverge
  across platforms.

All non-determinism is isolated to the network fetch layer. Once fetched content
is in memory, scoring is a pure function of that content.

### Provenance recording

Every HTTP request made during a scan is recorded as a `FetchRecord` containing:

- The request URL
- The HTTP status code returned
- The response body size in bytes
- The UTC timestamp at the moment of the fetch
- The AgentSurface version string that made the request

These records are embedded in the `provenance` field of every `Report` and written
to the JSON output file. Any published score can be audited by reviewing which URLs
were fetched, what they returned, and when.

### Test mode

When running under `pytest`, all HTTP calls are intercepted by the `respx` library,
which replays pre-recorded fixtures from `tests/fixtures/`. Real network sockets are
blocked by a socket guard in `tests/conftest.py`. Fixtures record a fixed timestamp
value so that time-dependent fields in the provenance output are stable across test
runs, enabling bit-identical test output.

The `--test-mode` flag can also be passed at the CLI level to pin timestamps to a
known value for comparison purposes outside of `pytest`.

### Float precision

All reported scores are rounded to **one decimal place**. This applies to dimension
scores, the overall ARI, and any values written to output files. Rounding is applied
once at the final aggregation step; intermediate calculations use full floating-point
precision. JSON output uses sorted keys throughout, making the serialized form
deterministic regardless of dict insertion order.

---

## 2. Sampling Decisions

Several signals check properties that could in principle be measured across an
entire API surface. In each case we sample a subset. This section justifies each
sampling choice.

### HTML content density: docs homepage only

We sample the documentation homepage (`docs_url` in the target configuration) rather
than crawling all documentation pages. A full-site crawl would:

- Multiply network cost by the number of pages (often hundreds).
- Require JS execution for single-page applications, which is out of scope.
- Return highly variable signal depending on which page is fetched.

The homepage is the most representative single page: it is the first page agents
and LLMs encounter, it is written to orient new consumers, and API providers
optimize it for clarity. The homepage content-density score is therefore the
highest-signal single-page proxy for overall docs accessibility.

### Error response quality: single heuristic probe

We probe one bad request (the first entry in `target.error_probes` if configured,
or a heuristic constructed from common patterns) rather than probing every
endpoint. The rationale: error response format is almost always consistent within
a single API. A team that decides to return `{"error": {"code": ..., "message":
...}}` for one endpoint applies that format everywhere. A team that returns plain
HTML errors does so consistently. Sampling one probe is sufficient for a reliable
estimate; probing every endpoint would multiply network load without materially
improving accuracy.

### SDK README: GitHub raw URL, not npm/pypi page

We fetch the README from the primary GitHub repository of the SDK package (via
the GitHub raw content CDN), not from the npm or PyPI package pages. GitHub raw
URLs are more stable (content is version-controlled), more complete (npm/PyPI
truncate or reformat READMEs), and return plain text rather than HTML that must
be stripped. The GitHub source is authoritative for the README content an agent
would see when searching for SDK documentation.

### OpenAPI example coverage: up to 20 operations sampled

We sample up to 20 operations from the OpenAPI spec rather than evaluating every
operation. Most APIs apply consistent discipline about examples across their entire
spec: a team that adds examples to request bodies does so for all endpoints; a team
that omits examples does so uniformly. Sampling 20 operations provides a reliable
estimate of overall example coverage while keeping parse time and memory usage
bounded for very large specs (e.g., Stripe's spec contains over 400 operations).
The sample is taken from the first 20 operations in spec-document order to ensure
determinism.

---

## 3. Per-Domain, Not Per-Endpoint Scoring

AgentSurface scores a developer product — a domain or brand — not individual
endpoints.

### What this means

A single ARI score represents the entire public API surface of a given provider.
The leaderboard ranks providers, not endpoints. The unit of comparison is "how
agent-ready is Stripe?" not "how agent-ready is `POST /v1/charges`?".

### Why this is the right granularity for agents

Agents interact with an API as a whole surface. They fetch the OpenAPI spec once
and use it to understand the full API. They follow the authentication pattern
described in the top-level `securitySchemes`. They use the docs homepage to orient
themselves. A single missing error schema ruins the agent experience for that
endpoint just as badly whether it is endpoint 1 or endpoint 50 in a 400-operation
spec.

The weighted-average signal scores already capture this: a spec where 60% of
operations define error schemas scores PARTIAL on that signal, not a mix of PASS
and FAIL per endpoint.

### Per-endpoint tools already exist

Per-endpoint granularity is appropriate for API linting tools such as
[Spectral](https://stoplight.io/open-source/spectral), which report per-rule
violations for every operation in a spec. AgentSurface is not a linter; it is a
readiness index. The dimension-level score is the appropriate unit for the
leaderboard and for API producer prioritization decisions.

---

## 4. Why These Six Dimensions

The six dimensions were chosen because each corresponds to a distinct friction
point that agents encounter when consuming a developer API. Each dimension is
independently observable from public surfaces and independently actionable by
API producers.

### OpenAPI Quality (20%)

Agents use the OpenAPI spec as their primary source of truth about an API's
structure. A machine-readable, valid, well-annotated spec allows an agent to
discover endpoints, construct valid requests, identify authentication requirements,
and handle failure modes — all without consulting prose documentation. The spec
is the machine-readable contract; without it, the agent is guessing. This is the
highest-weight dimension alongside Docs Accessibility because it directly enables
or blocks automated integration.

### Docs Accessibility (20%)

Even agents that have an OpenAPI spec need to consult documentation for context:
rate limits, pagination patterns, webhook setup, sandbox environments. If
documentation is entirely JS-rendered, agents cannot retrieve it. The `llms.txt`
convention directly reduces the token cost of loading documentation into a
context window. Docs accessibility and OpenAPI quality are complementary: a
perfect spec with inaccessible docs still leaves gaps for agents.

### SDK Ergonomics (15%)

Agents frequently generate code — scaffolding, glue code, integration scripts.
A well-typed official SDK reduces hallucination: the agent can reference correct
method signatures, parameter names, and return types rather than inferring them
from prose. An untyped SDK forces the agent to guess parameter shapes, which
produces incorrect code that fails at runtime. The conciseness of the quickstart
also affects context-window cost when the agent reads SDK documentation.

### Error UX (15%)

Agents need machine-parseable errors to retry and self-correct. An agent that
receives an HTML error page cannot determine whether to retry the request, adjust
a parameter, or report a permanent failure. A well-structured JSON error with a
stable code field, a docs URL, and field-level attribution allows the agent to
branch on specific failure conditions, retrieve targeted documentation, and
correct the specific field that failed — all autonomously.

### Auth Ergonomics (15%)

Agents must provision credentials programmatically. An agent deployed in a CI/CD
pipeline or a multi-agent orchestration system cannot click through a web
dashboard to generate an API key. If key issuance is only possible through a
manual dashboard step, the API is not deployable in non-interactive environments.
The accuracy of `securitySchemes` in the OpenAPI spec is also critical: an agent
that auto-configures auth from the spec will fail silently if the spec describes
the wrong credential placement.

### Discovery Surface (15%)

Agents need to know an API exists and how to interact with it programmatically.
The emerging conventions for agent discovery — `AGENTS.md`, MCP servers,
`ai-plugin.json`, and AI-aware `robots.txt` — signal that an API provider has
explicitly considered agent integration. An MCP server eliminates the need for
an agent to parse OpenAPI specs and generate tool wrappers entirely. `AGENTS.md`
documents agent-specific guidance that does not fit into the OpenAPI spec. These
artifacts have direct, measurable impact on agent integration effort.

---

## 5. Known Limitations

### No authenticated probes

All checks operate on public endpoints and unauthenticated documentation. Signals
that require credentials — the quality of responses behind authentication, the
behavior of permission enforcement, the correctness of admin or management APIs —
are not measured. An API can score well on ARI while having poor authenticated
behavior.

### No GraphQL, gRPC, or other protocols

The framework only evaluates REST/HTTP APIs discoverable via OpenAPI. GraphQL
APIs, gRPC services, WebSocket APIs, and MQTT brokers are not scored in Phase 1.
The OpenAPI Quality dimension scores FAIL for these API types even if the API is
otherwise excellent. Protocol coverage extensions are planned for future phases.

### Static snapshot

A score represents the API surface at the specific timestamps recorded in the
provenance block. APIs improve over time; a score that was accurate at scan time
may not reflect the current state of the API. The scheduled scan cadence and the
provenance timestamps allow consumers to assess how recent a score is.

### Heuristic signals

Several signals use text-search heuristics rather than deterministic machine-
readable checks. Examples:

- "Programmatic key issuance documented" searches documentation text for phrases
  associated with API-based key creation. It can produce false positives (a page
  that describes key creation in a web dashboard using similar language) and false
  negatives (documented in a non-standard location).
- "No JS-only content gates" is inferred from the ratio of visible text to total
  HTML; a page that happens to have dense HTML comments can inflate the score.
- "Scopes/permissions enumerable" uses structural heuristics on the OpenAPI spec
  and documentation; non-standard permission documentation formats may be missed.

Heuristic signals are labeled as such in the signal definitions in
`docs/framework.md`. When in doubt, open a dispute (see section 6).

### JS-rendered documentation

The content-density and JS-gate signals use raw HTTP fetches of HTML. Single-page
applications (SPAs) that perform server-side rendering may return different HTML
than client-side-only SPAs, causing the same visual documentation to score
differently depending on the rendering strategy. APIs using fully server-side-
rendered documentation may score higher on this signal than APIs using equivalent
client-rendered documentation, even if the end-user experience is identical.

---

## 6. Dispute and Correction Process

Scores are based on automated checks of public surfaces. Automated checks can be
wrong. The dispute process provides a path for API producers and community members
to correct false results.

### How to open a dispute

Open a GitHub issue at:

**https://github.com/your-org/agentsurface/issues/new**

Use the label `score-dispute`.

### What to include

1. The API slug and the specific dimension or signal in dispute.
2. The signal status you received (PASS / PARTIAL / FAIL) and the status you
   believe it should be.
3. Evidence in one of the following forms:
   - A URL that demonstrates the signal should pass (e.g., a URL to your
     `llms.txt` file, your OpenAPI spec, or your `AGENTS.md`).
   - A `curl` command that demonstrates the correct behavior (e.g., a curl to
     your error endpoint showing the JSON structure).
   - A permalink to the relevant section of your official documentation showing
     the behavior in question.
4. Optionally: the `provenance` block from `data/reports/<slug>.json` to help
   maintainers identify which fetch produced the incorrect result.

### What happens next

Maintainers will review the evidence. If the evidence is accepted:

- The scan fixtures for the affected API will be updated to reflect the correct
  response.
- The scan will be re-run against the updated fixtures and the score will be
  corrected.
- The correction will be recorded in the repository's commit history.

Score corrections are reflected in the next scheduled scan run and are visible
in the leaderboard immediately after the site is rebuilt. All changes to seed
data or scoring logic that affect published scores are logged in the repository
commit history with a reference to the dispute issue.

---

## 7. How to Reproduce a Score Locally

### Prerequisites

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/) (the project uses uv for dependency management)
- Git

### Steps

```bash
git clone https://github.com/your-org/agentsurface
cd agentsurface
uv pip install -e .
agentsurface scan stripe
```

Output is written to:
- `data/reports/stripe.json` — machine-readable report with provenance block
- `data/reports/stripe.md` — human-readable markdown report with signal breakdown

### Reproducing published scores exactly

Published scores are produced using the fixture set checked in under
`tests/fixtures/`. To reproduce using the same fixtures:

```bash
pytest tests/ -q
```

The test suite uses `respx` to replay fixtures and blocks real network sockets via
the socket guard in `tests/conftest.py`. Fixture timestamps are pinned, so output
matches the published provenance blocks exactly.

See `tests/fixtures/README.md` for documentation on the fixture format and how
to add or update fixtures.

### Re-scanning against live network

To run a fresh scan that makes real network requests (results may differ from
published scores if the API surface has changed):

```bash
agentsurface scan stripe --live
```

The `--live` flag bypasses fixture replay and makes real HTTP calls. The resulting
report will have current fetch timestamps in the provenance block. Differences
between a live scan and the published score can be attributed to specific URL
changes by comparing the provenance blocks.

### Reproducing the full leaderboard

```bash
agentsurface scan-all
agentsurface build-site
```

Output is written to `site/`. The leaderboard is at `site/index.html`.
