# AgentSurface

AgentSurface is an open scoring framework and automated scanner that grades developer API products on how usable they are for AI coding agents such as Claude Code, Cursor, Codex, Cline, and Aider. As the B2A (business-to-agent) category grows, the quality of an API's documentation, schema, SDK, and error messages directly determines whether an agent can use it reliably without human intervention. AgentSurface quantifies that quality as an Agent Readiness Index (0–100, graded A through F) across six dimensions, and publishes a static leaderboard covering roughly 50 popular developer APIs.

## Install

```
uv pip install -e .
```

Requires Python 3.11+.

## Quick start

Scan a single API and view its grade:

```
$ agentsurface scan stripe
✓ Scored stripe: A (91.2)
```

Report files are written to `data/reports/stripe.json` and `data/reports/stripe.md`.

Scan all APIs in the seed list and build the static leaderboard site:

```
$ agentsurface scan-all && agentsurface build-site
Scored 50/50 APIs. index.json written to data/reports
Site built → site/
```

Open `site/index.html` in a browser to view the leaderboard.

## Scoring framework

Each API receives a weighted average score across six dimensions. The result is the Agent Readiness Index (ARI, 0–100).

| Dimension          | Weight | What is measured                                            |
|--------------------|--------|-------------------------------------------------------------|
| OpenAPI quality    | 20%    | Schema completeness, versioning, machine-readable format    |
| Docs accessibility | 20%    | Structured content, search, code examples, LLM-fetchable   |
| SDK ergonomics     | 15%    | Idiomatic SDK availability, typed clients, async support    |
| Error UX           | 15%    | Consistent error shapes, codes, human-readable messages     |
| Auth ergonomics    | 15%    | Clear auth flow, sandbox keys, OAuth discoverability        |
| Discovery surface  | 15%    | Changelog, OpenAPI endpoint hints, sitemap, llms.txt        |

Grades: A (90–100), B (75–89), C (60–74), D (45–59), F (<45).

Full methodology and rubric: [docs/framework.md](docs/framework.md) (CC-BY-4.0).

## What's NOT yet measured

The following are out of scope for Phase 1:

- GraphQL-only and gRPC-only APIs
- Private or internal APIs
- Authenticated endpoints (Phase 1 scans public surfaces only)
- Real-time re-scoring (the leaderboard is a static build, not a live feed)
- Non-English documentation (English only)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, testing, adding APIs, and the PR checklist.

The scoring framework specification (`docs/framework.md`) is licensed CC-BY-4.0. Contributions to that file are accepted under the same license.

## License

Code: MIT. See [LICENSE](LICENSE).

Framework specification (`docs/framework.md`): CC-BY-4.0.
