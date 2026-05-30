# Contributing to AgentSurface

## Dev environment setup

Clone the repository and install with dev dependencies:

```
uv pip install -e ".[dev]"
```

This installs the package in editable mode along with pytest, respx, ruff, and
pytest-asyncio.

## Running tests

```
pytest -q
```

Tests use pre-recorded HTTP fixtures and do not open real network sockets. The
`conftest.py` session fixture patches `socket.socket` to raise a `RuntimeError`
if any test attempts a live TCP connection (AF_INET or AF_INET6). If you see
that error, you forgot to record a fixture.

## Adding a new scanner test

1. Record the HTTP responses your scanner needs as files under
   `tests/fixtures/<scanner_name>/` (e.g., `openapi.json`, `robots.txt`).
2. In your test file (`tests/test_scanner_<name>.py`), use `respx` to mock the
   HTTP calls and return the fixture bytes.
3. Use the `make_target` fixture from `conftest.py` to create a `Target` instance.
4. Assert on the returned `DimensionScore` fields.

## Adding a new API to the seed list

Edit `data/seed_apis.yaml`. Each entry requires:

```yaml
- slug: myapi            # unique lowercase identifier
  name: My API           # display name
  category: payments     # one of the defined category slugs
  homepage: https://myapi.example.com
  docs_url: https://docs.myapi.example.com
```

Optional fields: `openapi_url`, `sdk_urls` (list), `changelog_url`.

## Re-generating reports and the site

```
agentsurface scan-all && agentsurface build-site
```

Output: `data/reports/index.json` and per-API JSON/Markdown reports, then
`site/` with the static leaderboard.

## Linting

```
ruff check src/ tests/
```

All PRs must pass ruff with no errors. Do not use `# noqa` to suppress without
a comment explaining why.

## PR expectations

- All tests must pass (`pytest -q`).
- No live network sockets in tests (the conftest guard will catch violations).
- No credentials, tokens, or secrets in any committed file.
- New scanners must include at least one test with a recorded fixture.
- Keep line length within the project limit (100 characters, enforced by ruff).

## Disputing a score

If you believe a score for an API is inaccurate, open a GitHub issue with:

- The API slug and current score.
- Evidence (public URL, schema, or documentation) showing what the scanner
  missed or measured incorrectly.

The maintainers will re-run the scanner against the evidence and, if confirmed,
update the fixture and re-publish the report. This is the Phase 1 appeals
process.

## License

All code contributions are made under the MIT license.

Contributions to `docs/framework.md` (the scoring specification) are made under
CC-BY-4.0. By submitting a pull request that modifies `docs/framework.md` you
agree to license that contribution under CC-BY-4.0.
