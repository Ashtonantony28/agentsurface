# Sprint working agreement

## Finishing contract

SDK subagent (Task):
1. Save changes. 2. Append to STATUS.md (no overwrite):
   ### TASK-XXX (YYYY-MM-DD)
   - what changed (paths)
   - cross-task decisions
3. Flip task in TASKS.md to [x].

`claude -p` fan-out worker: write deliverable to the path you were told. Do NOT
touch STATUS.md or TASKS.md. Emit stdout JSON: `{"item":"<id>","files_changed":[...]}`.

## Output discipline

- No step narration. One sentence confirming completion. Deliverable is the code
  change plus the STATUS line (or stdout JSON for fan-out).

## Read efficiency

- Grep/Glob before Read. Use line ranges. Do not read PLAN.md, TASKS.md, or
  STATUS.md — the orchestrator briefed you.

## Project-specific rules

- All scanners scrape only public surfaces. No authenticated API calls.
- All HTTP calls go through `src/agentsurface/http.py` once it exists. Do not
  create ad-hoc httpx clients.
- All tests use `respx` fixtures under `tests/fixtures/`. Tests must not open real
  network sockets — `conftest.py` enforces this. If a test seems to need network,
  you forgot to record the fixture.
- JSON output is deterministic: sorted keys, fixed float precision (1 decimal for
  scores). The reproducibility property is part of the product, not optional.
- The framework spec (`docs/framework.md`) is licensed CC-BY-4.0; code is MIT.
  Preserve both license headers if you touch them.

## Safety

- Never print or commit credentials. The project does not require any.
- One task per worker.
