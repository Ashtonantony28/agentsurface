# Tasks

<!-- Scenario B (greenfield). All tasks start [ ]. Files-touched is the disjoint-set
     check the orchestrator uses to decide what can run in parallel and what must be
     sequential. Tasks marked [FAN-OUT CANDIDATE] are good fits for a `claude -p`
     fan-out batch once the prerequisite is done. -->

## Phase 0 — Scaffolding (sequential, must complete before everything else)

- [x] TASK-001: Initialize Python project — `pyproject.toml`, package metadata, deps (`httpx`, `pydantic>=2`, `jinja2`, `pyyaml`, `click`, `pytest`, `respx`, `ruff`), `uv.lock`, `src/agentsurface/__init__.py` with `__version__ = "0.1.0"` — deps: none — files: `pyproject.toml`, `src/agentsurface/__init__.py`, `.gitignore`

- [x] TASK-002: Add LICENSE (MIT for code) and a top-level `LICENSE` file. Add CC-BY-4.0 notice header at the top of an empty `docs/framework.md` — deps: TASK-001 — files: `LICENSE`, `docs/framework.md`

## Phase 1 — Core data model and framework (sequential foundation)

- [x] TASK-003: Implement pydantic data model: `Signal`, `DimensionScore`, `Provenance`, `Report`, `Grade`. Include deterministic JSON serialization (sorted keys, fixed float precision). Include a `model_dump_json(indent=2, sort_keys=True)` helper — deps: TASK-001 — files: `src/agentsurface/models.py`

- [x] TASK-004: Implement `framework.py`: dimension definitions with weights (20/20/15/15/15/15), letter-grade mapping (A/B/C/D/F with +/- modifiers), and the `compute_grade(score: float) -> Grade` function. Pure functions, no I/O — deps: TASK-003 — files: `src/agentsurface/framework.py`

- [x] TASK-005: Implement `aggregate.py`: take a list of `DimensionScore` and produce the overall `Report.overall_score`. Weighted average, deterministic — deps: TASK-003, TASK-004 — files: `src/agentsurface/aggregate.py`

- [x] TASK-006: Write the open scoring framework spec to `docs/framework.md`. Self-contained explanation of each dimension, each signal, how scores roll up, how grades map, how to reproduce, how to dispute. Keep under 1500 lines — deps: TASK-004 — files: `docs/framework.md`

- [x] TASK-007: Write `docs/METHODOLOGY.md`: reproducibility, sampling decisions, per-domain not per-endpoint, dispute process — deps: TASK-006 — files: `docs/METHODOLOGY.md`

## Phase 2 — Shared infrastructure (sequential, blocks scanners)

- [x] TASK-008: Implement `http.py`: shared `httpx.AsyncClient` factory with timeouts, AgentSurface User-Agent, retry-with-backoff for 429/503, per-domain rate limiter (max 4 concurrent, 1 req/sec). Recorded in provenance — deps: TASK-001 — files: `src/agentsurface/http.py`

- [x] TASK-009: Implement `scanners/base.py`: `Scanner` ABC with `dimension_id`, `dimension_name`, `weight`, and `async def scan(target: Target) -> DimensionScore`. Include the `Target` dataclass (slug, name, category, homepage, docs_url, openapi_url, github_org, npm_package, pypi_package, mcp_server_url) — deps: TASK-003, TASK-008 — files: `src/agentsurface/scanners/__init__.py`, `src/agentsurface/scanners/base.py`

## Phase 3 — Six scanners [FAN-OUT CANDIDATE]

These six tasks are homogeneous (same recipe: implement a `Scanner` subclass with
N signals, each signal an async check returning pass/fail/partial with evidence),
they touch disjoint files, and the prerequisite (TASK-009) gives them everything
they need. **Schedule as one `claude -p` fan-out batch with concurrency 3.**

- [x] TASK-010: Implement `OpenAPIScanner` (dimension 1). Signals: spec discoverable, valid OAS 3.x, has `servers`, auth in `securitySchemes`, error response schemas, example coverage ≥50% — deps: TASK-009 — files: `src/agentsurface/scanners/openapi.py`

- [x] TASK-011: Implement `DocsScanner` (dimension 2). Signals: `/llms.txt` returns 200, `/llms-full.txt` or `.md` variants reachable, HTML content-density on sampled page, no JS-only gates — deps: TASK-009 — files: `src/agentsurface/scanners/docs.py`

- [x] TASK-012: Implement `SDKScanner` (dimension 3). Signals: official npm package, official pypi package, install one-liner in README first 20 lines (fetch via GitHub raw or npm/pypi metadata), typed, README quickstart length — deps: TASK-009 — files: `src/agentsurface/scanners/sdk.py`

- [x] TASK-013: Implement `ErrorsScanner` (dimension 4). Signals: probe a known-bad request shape (e.g., `GET /v1/customers/nonexistent_id_xxx` for Stripe-like APIs — read from `target.error_probes` if provided in seed list, else heuristic). Score: JSON response, machine code field, docs URL, names offending field, status code semantically correct — deps: TASK-009 — files: `src/agentsurface/scanners/errors.py`

- [x] TASK-014: Implement `AuthScanner` (dimension 5). Signals: programmatic key-issuance documented, key model in `securitySchemes`, scopes enumerable. Heuristic + docs-search hybrid; conservative scoring when uncertain — deps: TASK-009 — files: `src/agentsurface/scanners/auth.py`

- [x] TASK-015: Implement `DiscoveryScanner` (dimension 6). Signals: `AGENTS.md` at repo root via GitHub API, MCP server URL reachable if specified, `.well-known/ai-plugin.json`, robots.txt distinguishes AI crawlers — deps: TASK-009 — files: `src/agentsurface/scanners/discovery.py`

## Phase 4 — Runner, reporting, CLI (sequential, blocks site)

- [x] TASK-016: Implement `runner.py`: load `Target` from `data/seed_apis.yaml`, run all 6 scanners (concurrently with `asyncio.gather`), aggregate into a `Report`. Single API by slug — deps: TASK-005, TASK-010..TASK-015 — files: `src/agentsurface/runner.py`

- [x] TASK-017: Implement `report.py`: write `Report` to `data/reports/<slug>.json` and `data/reports/<slug>.md`. Markdown report includes the score table, signal-level breakdown, and "how to improve" recommendations derived from failed signals — deps: TASK-016 — files: `src/agentsurface/report.py`

- [x] TASK-018: Implement `cli.py` with click subcommands: `scan <slug>`, `scan-all`, `build-site`. Wire to `runner` / `report` / `site`. Add `python -m agentsurface` entry — deps: TASK-016, TASK-017 — files: `src/agentsurface/cli.py`, `src/agentsurface/__main__.py`

- [x] TASK-019: Implement `scan-all` orchestration: read every entry from `seed_apis.yaml`, run sequentially with a small concurrency cap, write `data/reports/index.json` (slug → overall_score + grade + timestamp) — deps: TASK-018 — files: `src/agentsurface/cli.py` (extend)

## Phase 5 — Seed data (independent, can run in parallel with Phase 3 or 4)

- [x] TASK-020: Curate the seed API list of ≥40 entries spread across all 8 categories (payments, infra, comms, identity/auth, data/storage, AI/ML, e-commerce, devtools/observability). For each: slug, name, category, homepage, docs_url, optional openapi_url, github_org, npm_package, pypi_package. Suggested seed names (research current docs URLs at write time): Stripe, Twilio, SendGrid, Resend, Plaid, Shopify, Square, Supabase, Clerk, Auth0, WorkOS, Vercel, Cloudflare, Linear, Notion, Slack, Discord, Intercom, OpenAI, Anthropic, Cohere, Pinecone, Weaviate, Mistral, Replicate, HuggingFace, Stability, AssemblyAI, Deepgram, ElevenLabs, GitHub, GitLab, Sentry, Datadog, PostHog, LaunchDarkly, Algolia, Mux, Cloudinary, Segment, Snyk, Atlas, Render, Fly.io — deps: TASK-001 — files: `data/seed_apis.yaml`

## Phase 6 — Static site (sequential, depends on reports existing)

- [x] TASK-021: Implement Jinja2 templates — `base.html.j2` with minimal CSS (single `<style>` block, no external dependencies, dark/light via `prefers-color-scheme`), `index.html.j2` (leaderboard table, sortable via tiny vanilla JS, category filter), `api.html.j2` (per-API breakdown), `framework.html.j2`, `submit.html.j2` — deps: TASK-001 — files: `templates/base.html.j2`, `templates/index.html.j2`, `templates/api.html.j2`, `templates/framework.html.j2`, `templates/submit.html.j2`

- [x] TASK-022: Implement `badge.py`: generate a static SVG badge per API. Shields.io style; embeds API slug, overall grade, hex colour by grade. Output to `site/badge/<slug>.svg`. Include the `<img>` snippet shown on each per-API page — deps: TASK-004 — files: `src/agentsurface/badge.py`

- [x] TASK-023: Implement `site.py`: render leaderboard from `data/reports/*.json`, render per-API pages, render framework from `docs/framework.md` (use `markdown` package — add to deps), render submit page, copy/generate badges. Output to `site/` — deps: TASK-017, TASK-021, TASK-022 — files: `src/agentsurface/site.py`, `pyproject.toml` (add `markdown` dep)

- [x] TASK-024: Wire `build-site` CLI subcommand to `site.py` — deps: TASK-018, TASK-023 — files: `src/agentsurface/cli.py` (extend)

## Phase 7 — Tests [FAN-OUT CANDIDATE]

Once scanners are implemented, **per-scanner tests are a homogeneous fan-out batch**:
same shape (record an httpx fixture for one known-good API and one known-bad API,
assert signal pass/fail), disjoint output paths. Schedule as a single `claude -p`
batch with concurrency 3.

- [x] TASK-025: Add `tests/conftest.py` with the no-network socket guard, the
  `Target` factory, and shared fixture-loading helpers. Add `tests/test_models.py`
  and `tests/test_aggregate.py` (pure-function tests, no fixtures needed) — deps: TASK-005 — files: `tests/conftest.py`, `tests/test_models.py`, `tests/test_aggregate.py`

- [x] TASK-026: Add per-scanner tests `tests/test_scanner_openapi.py`,
  `test_scanner_docs.py`, `test_scanner_sdk.py`, `test_scanner_errors.py`,
  `test_scanner_auth.py`, `test_scanner_discovery.py`, each with at least one
  pass-path and one fail-path fixture under `tests/fixtures/<scanner>/`. **This
  task is the natural fan-out parent**: dispatch as 6 disjoint sub-items, one
  scanner per `claude -p` invocation — deps: TASK-010..TASK-015, TASK-025 — files: `tests/test_scanner_*.py`, `tests/fixtures/**`

- [x] TASK-027: Add `tests/test_runner_e2e.py` and `tests/test_site.py`. End-to-end
  scan against fully-fixtured target, then build-site, then assert key strings in
  the output HTML — deps: TASK-024, TASK-026 — files: `tests/test_runner_e2e.py`, `tests/test_site.py`

## Phase 8 — Final polish (sequential close)

- [x] TASK-028: Write `README.md` (pitch, install with `uv`, run-one-API example,
  build-site example, contributing, license, "not yet measured" section). Add
  `CONTRIBUTING.md`. Add `.github/workflows/ci.yml` running `ruff check` and
  `pytest -q` on push, networking disabled — deps: TASK-027 — files: `README.md`, `CONTRIBUTING.md`, `.github/workflows/ci.yml`

## Phase 2 — Bug fixes, live runs, enhancements

- [x] TASK-101: Fix 6 pre-existing test failures in test_scanner_auth, test_scanner_discovery, test_scanner_errors. Exact bugs: (1) Target() calls missing slug/name/category; (2) .signal_id/.outcome -> .id/.status; (3) fetch_records=[]; (4) error scanner heuristic probe URL derives from docs_url not homepage. Run pytest -q to confirm green — deps: none — files: `tests/test_scanner_auth.py`, `tests/test_scanner_discovery.py`, `tests/test_scanner_errors.py`

- [x] TASK-102: Run agentsurface scan against 5 representative APIs (stripe, twilio, supabase, openai, clerk) using live network. Log any scanner crashes or empty signal lists to STATUS.md. Do not fix scanner bugs yet — just document what breaks — deps: TASK-101 — files: `data/reports/*.json`, `data/reports/*.md`

- [x] TASK-103: Fix any scanner bugs revealed by TASK-102 live runs. Re-run the 5 scans to confirm clean output — deps: TASK-102 — files: `src/agentsurface/scanners/*.py`

- [x] TASK-104: Run agentsurface scan-all against all 48 seed APIs. Then run agentsurface build-site. Confirm site/index.html renders and all 48 per-API pages exist — deps: TASK-103 — files: `data/reports/*`, `site/*`

- [x] TASK-105: Improve static site UX: add sort-by-category and sort-by-score controls using vanilla JS (no external deps), add a sticky header, make the leaderboard table mobile-responsive with horizontal scroll, add og:title/og:description/og:image meta tags to base template — deps: TASK-104 — files: `templates/base.html.j2`, `templates/index.html.j2`

- [x] TASK-106: Improve per-API report page (templates/api.html.j2): add a visual score bar per dimension (CSS only), add a 'What to fix first' section that surfaces the 3 lowest-scoring signals with direct links to the evidence, add a copy-to-clipboard button for the badge embed snippet — deps: TASK-104 — files: `templates/api.html.j2`

- [x] TASK-107: Add scan result caching to runner.py: if data/reports/<slug>.json exists and is less than 24h old, skip re-scanning and use cached result unless --force flag is passed — deps: TASK-104 — files: `src/agentsurface/runner.py`, `src/agentsurface/cli.py`

- [x] TASK-108: Add .github/workflows/deploy.yml: on push to main, run agentsurface scan-all then agentsurface build-site then deploy site/ to GitHub Pages via actions/deploy-pages — deps: TASK-104 — files: `.github/workflows/deploy.yml`

- [x] TASK-109: Improve scanner signal depth — add 2 new signals to each of the 6 scanners based on gaps found in TASK-102 live runs. Document the new signals in docs/framework.md — deps: TASK-103 — files: `src/agentsurface/scanners/*.py`, `docs/framework.md`

- [x] TASK-110: Improve the Markdown report template in report.py: add an executive summary sentence at the top (one line: grade, top strength, top weakness), add a timestamp and scanner version footer, ensure all evidence_url fields are clickable links — deps: TASK-104 — files: `src/agentsurface/report.py`

- [x] TASK-111: Final sweep — run pytest -q (confirm still green after scanner changes), run ruff check src/ tests/ (fix any new errors), run agentsurface build-site once more, write a final STATUS.md summary of Phase 2 completion — deps: TASK-110 — files: all modified
