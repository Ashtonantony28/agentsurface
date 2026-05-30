# Project Plan — AgentSurface (Phase 1 wedge)

## Goal

Ship the public-benchmark wedge of AgentSurface: an **open scoring framework** plus an
**automated scanner** that grades developer-API products on how usable they are for AI
coding agents (Claude Code, Cursor, Codex, Cline, Aider), and a **static leaderboard
site** that publishes the scores for a curated seed list of ~50 popular developer APIs.

The MVP must satisfy three commercial requirements, not just technical ones:

1. **Be press-worthy on launch day.** "We scored every major developer API on how
   usable they are for AI agents — here is the leaderboard" is a one-line pitch that
   tech press picks up. The deliverable has to support that story without follow-up
   engineering.
2. **Generate qualified inbound.** Companies that score poorly should have a
   self-service path to learn what to fix (free) and a way to contact us for help
   (paid, Phase 2). The leaderboard must include an "embed this badge" feature so
   top scorers market for us.
3. **Be defensible and open.** The framework spec is published under CC-BY-4.0 so it
   becomes a standard others can cite. Score reproducibility (same inputs → same
   outputs) is non-negotiable.

This is the distribution wedge for the Phase 2 paid product (managed agent-surface
remediation: hosted `llms.txt` + `AGENTS.md` generation, MCP server provisioning,
error-rewriter middleware, agent-mode auth). Phase 2 and Phase 3 are documented for
context but are **out of scope** for this build.

## Context, market, and competitive landscape (locked)

This is in `PLAN.md` rather than just `README.md` because the orchestrator and any
human reviewer needs the why-this-matters framing to make good trade-offs during
execution. Five anchored facts:

- **The category is real and naming has begun.** Industry analysts now use the term
  "Business-to-Agent" (B2A) for the surfaces a company exposes to agents rather than
  to humans (docs, SDKs, errors, auth). IDE agents — Cursor, Windsurf, Claude Code,
  GitHub Copilot, Cline, Aider — already routinely fetch `/llms.txt` and
  `/llms-full.txt` when pointed at a documentation site.
- **The inflection has happened.** Karpathy publicly named December 2025 as the
  threshold where his personal coding mix flipped from ~80% human / ~20% agent to
  the inverse. MCP crossed 97M monthly SDK downloads and 10K+ public servers in
  December 2025, and was donated to the Linux Foundation's Agentic AI Foundation
  later that month. 41% of organisations in Stacklok's 2026 survey are in limited
  or broad MCP production.
- **Direct competitor is enterprise-only with a different motion.** Jentic (Dublin,
  founded 2024, $4.5M pre-seed, AWS GenAI Accelerator alum, AWS Marketplace listing)
  ships an open six-dimension API AI-Readiness framework and a white-glove
  enterprise scorecard with manual onboarding. They lean heavily on OpenAPI quality
  and enterprise governance. They are **not** doing self-serve PLG, do not cover
  docs / SDK / error UX as first-class dimensions, and do not publish a public
  leaderboard. The mid-market self-serve developer-tools layer is open.
- **Adjacent competitors validate the category but don't occupy this slot.**
  Stainless was acquired by Anthropic in May 2026 — a major signal that agent
  connectivity infrastructure is strategic, and the exact reason an **independent,
  cross-agent benchmark** is more credible than ever (companies won't accept a grade
  produced by a tool owned by one model vendor). Speakeasy ships SDK generation +
  MCP Gateway. Mintlify and Fern auto-generate `llms.txt` for docs they host.
  None publish a cross-API public leaderboard or score the full developer surface.
- **Pricing benchmarks for Phase 2 monetisation.** Comparable developer-tools
  PLG products price roughly: Mintlify Pro $250–300/mo, ReadMe Business $349/mo,
  Scalar paid from $150/mo, enterprise tiers $15–25K/yr. This sets the eventual
  Phase 2 anchor; Phase 1 is free.

## Architecture & key decisions (locked)

**Stack.** Pure Python 3.11+ for the engine and the static site generator. Single
toolchain, trivial to fan out across APIs, no JS build pipeline in Phase 1.

| Concern | Choice | Why |
|---|---|---|
| HTTP | `httpx` | Async-ready, modern, stable |
| Data model | `pydantic` v2 | Validation + JSON serialization in one |
| Templates | `jinja2` | Static HTML, no JS dependency |
| Config | `pyyaml` | Seed API list is YAML-edited frequently |
| Tests | `pytest` + `respx` | Recorded HTTP fixtures, no live network |
| CLI | `click` | Standard, scriptable |
| Package mgr | `uv` | Fast, lockfile, single binary |

**Repository layout.**
```
agentsurface/
├── pyproject.toml
├── uv.lock                       # committed; reproducible installs
├── README.md
├── LICENSE                       # MIT for code
├── docs/
│   ├── framework.md              # the open scoring framework spec, CC-BY-4.0
│   └── METHODOLOGY.md            # how scores are computed, edge cases, FAQs
├── data/
│   ├── seed_apis.yaml            # curated list of ~50 APIs to score
│   └── reports/                  # generated JSON per API (gitignored)
├── src/agentsurface/
│   ├── __init__.py
│   ├── models.py                 # pydantic: Signal, DimensionScore, Report, Grade
│   ├── framework.py              # weights, thresholds, 0–100 → A/B/C/D/F mapping
│   ├── http.py                   # shared httpx client with timeouts, UA, retries
│   ├── scanners/
│   │   ├── __init__.py           # registry: name → Scanner class
│   │   ├── base.py               # Scanner ABC, fixture-loading helpers
│   │   ├── openapi.py            # dimension 1: OpenAPI quality
│   │   ├── docs.py               # dimension 2: docs accessibility (llms.txt, etc.)
│   │   ├── sdk.py                # dimension 3: SDK ergonomics
│   │   ├── errors.py             # dimension 4: error UX
│   │   ├── auth.py               # dimension 5: auth ergonomics
│   │   └── discovery.py          # dimension 6: discovery surface
│   ├── runner.py                 # `agentsurface scan <slug>` — scores one API
│   ├── aggregate.py              # roll dimension scores into the overall index
│   ├── report.py                 # write per-API JSON + Markdown
│   ├── site.py                   # render leaderboard + per-API + framework pages
│   ├── badge.py                  # SVG "Agent Readiness: B+" badge generator
│   └── cli.py                    # click entrypoint: scan, scan-all, build-site
├── templates/
│   ├── base.html.j2
│   ├── index.html.j2             # leaderboard
│   ├── api.html.j2               # per-API report
│   ├── framework.html.j2         # rendered framework spec
│   └── submit.html.j2            # "submit your API" page (mailto: in MVP)
├── tests/
│   ├── fixtures/                 # recorded HTTP responses per scanner
│   ├── test_models.py
│   ├── test_aggregate.py
│   ├── test_scanner_*.py         # one file per scanner
│   ├── test_runner_e2e.py
│   └── test_site.py
├── .github/workflows/ci.yml      # lint (ruff) + test (pytest, no network)
└── site/                         # generated static site output (gitignored)
```

**Scoring framework (locked at six dimensions).** Each dimension is 0–100; the
overall **Agent Readiness Index** is a weighted average rounded to one decimal.
Letter grades: 90–100 = A, 75–89 = B, 60–74 = C, 40–59 = D, 0–39 = F. Plus/minus
modifiers (`A+`, `B-`) are computed from the position within the band: top third =
`+`, bottom third = `-`.

| # | Dimension | Weight | What's measured (concrete signals) |
|---|---|---|---|
| 1 | OpenAPI quality | 20% | Spec discoverable from docs root, valid OAS 3.x, has `servers`, auth defined in `securitySchemes` (not just prose), responses include error schemas, ≥50% endpoints have examples |
| 2 | Docs accessibility | 20% | `/llms.txt` returns 200, `/llms-full.txt` exists OR `.md` versions reachable, HTML pages have ≤20% non-content markup by byte count on a sampled page, no JS-only content gates |
| 3 | SDK ergonomics | 15% | Official SDK on npm AND pypi (or one of two with documented reason), README has install one-liner in first 20 lines, typed (TS types or Python stubs), README under 300 lines for quickstart section |
| 4 | Error UX | 15% | Sampled error responses are JSON, include a stable machine code field, include a docs URL, name the offending field for validation errors, status codes are semantically correct |
| 5 | Auth ergonomics | 15% | API key obtainable without human-only flow (programmatic signup OR documented service-account path), key model documented in OpenAPI `securitySchemes`, scopes/permissions enumerable |
| 6 | Discovery surface | 15% | `AGENTS.md` at repo root, hosted MCP server documented OR present, `.well-known/ai-plugin.json` OR equivalent, robots policy that distinguishes AI crawlers from search crawlers |

Each scanner emits a list of `Signal` objects (id, label, weight-within-dimension,
pass/fail/partial, evidence URL, notes). The dimension score is the weighted average
of its signals. This means we can show a reviewer **exactly** why a score is what it
is — critical for credibility and for the "what to fix" path.

**Reproducibility.** Every scanner records the URLs it fetched and the timestamps
of those fetches into the report's provenance block. Re-running against the same
recorded fixtures yields byte-identical JSON output (deterministic field ordering,
fixed timestamp in test mode).

**No live network in tests.** All scanner tests use `respx` to intercept httpx
calls and replay from `tests/fixtures/`. CI runs offline. This is enforced by a
`pytest` plugin that fails any test that opens a real socket.

## Definition of done

The Phase 1 MVP is done when **all** of these are true:

- `agentsurface scan stripe` produces `data/reports/stripe.json` AND
  `data/reports/stripe.md`, exit 0, no network errors logged.
- `agentsurface scan-all` iterates every API in `data/seed_apis.yaml`, writes a
  report for each, and produces a `data/reports/index.json` summary.
- `agentsurface build-site` writes `site/index.html`, `site/framework.html`,
  `site/submit.html`, `site/badge/<slug>.svg`, and `site/api/<slug>.html` for every
  scored API. Site is fully static and renders correctly via `file://`.
- `data/seed_apis.yaml` contains **≥ 40 entries** across these categories:
  payments, infrastructure, communications, identity/auth, data/storage, AI/ML,
  e-commerce, devtools/observability. Each entry has: slug, display name, category,
  homepage URL, docs URL, optional OpenAPI URL, optional GitHub org, optional npm
  package, optional pypi package.
- Each of the 6 scanners has unit tests using recorded fixtures, covering the pass
  path AND at least one signal-fail path. `pytest` passes with no network.
- `docs/framework.md` is self-contained: a reader who has never seen the project
  understands what each dimension measures, why, how signals roll up, and how the
  letter grade is computed.
- `docs/METHODOLOGY.md` covers: how to reproduce scores, why HTML content-density
  is sampled rather than full-page, why we score per-domain and not per-endpoint,
  the appeals/correction process (open a GitHub issue with evidence).
- `README.md` includes: one-paragraph pitch, install (`uv pip install -e .`),
  run-one-API example, build-site example, contributor section, license note, and
  a "what's NOT yet measured" section setting expectations.
- The leaderboard page sorts by overall score, lets you filter by category, links
  to each per-API report, and shows the `<img>` snippet to embed the badge.
- A `submit.html` page exists with a clean `mailto:` form for companies to request
  scoring or contest a score.
- The framework spec page is rendered to `site/framework.html` from
  `docs/framework.md` via the same template system.
- License: MIT for code, CC-BY-4.0 for `docs/framework.md`, both noted in
  `LICENSE` and at the top of the framework doc.

## Constraints & regulations

**No special regulations.** The orchestrator runs in Autonomous profile and may
self-loop until `TASKS.md` is exhausted.

Implicit guardrails (these are also encoded in `CLAUDE.md`):

- No credentials in any committed file, log, or output. The scanners are read-only
  against public surfaces only — no authenticated API calls in Phase 1.
- No live network calls in tests. CI runs with networking disabled at the socket
  level; a violation is a test failure.
- No file deletion outside the project root. No edits to anything inside
  `tests/fixtures/` after the fixture is committed (fixtures are inputs, not
  outputs).
- All HTTP requests must set a clear `User-Agent: AgentSurface-Scanner/0.1
  (+https://github.com/your-org/agentsurface)` so target sites can identify us.
- Scanner-level rate limits: max 4 concurrent requests to a single domain, max 1
  per second per domain. Respect `robots.txt` AND `llms.txt` disallow rules.

## Out of scope (Phase 1)

- **The paid SaaS product (Phase 2).** Hosted `llms.txt` / `AGENTS.md` generation,
  MCP server provisioning, error-rewriter middleware, agent-mode auth, CI
  integration that fails PRs on score regression.
- **Agent analytics (Phase 3).** Cross-API behavioural data on which agents
  attempt what.
- **A backend, a database, user accounts, a submission API.** A `mailto:` link is
  sufficient for MVP inbound capture.
- **Authenticated probes.** Phase 1 inspects only what is publicly observable to
  an unauthenticated visitor.
- **Real-time re-scoring.** The leaderboard is a static build, refreshed by
  re-running `agentsurface scan-all && agentsurface build-site`.
- **Scoring private/internal APIs**, GraphQL-only APIs, gRPC-only APIs. These are
  Phase 2 add-on dimensions.
- **A formal appeals system.** "Open a GitHub issue with evidence" is the v1.
- **i18n.** English-only.

## Stretch (only if every Definition-of-Done item is complete and the window has time)

- Add `GET /api/<slug>.json` and `GET /index.json` to the static site for
  programmatic consumers.
- Add a "delta since last scan" indicator on the leaderboard (requires storing
  prior reports under `data/reports_history/<date>/`).
- Add a `RSS` feed of newly scored or significantly changed APIs.
