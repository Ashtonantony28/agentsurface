"""AgentSurface orchestrator.

Generated for: Scenario B (greenfield) / Autonomous profile / Sprint mode.

Reads PLAN.md, TASKS.md, STATUS.md every cycle and dispatches the next task(s).
On a Claude Max 5x subscription via `claude setup-token` — never an API key.
See README of the parent handoff doc for the design rationale.
"""

import asyncio
import os
import sys
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AgentDefinition,
    AssistantMessage,
    TextBlock,
    ResultMessage,
)

# ── PROFILE: Autonomous + Sprint, set per STEP 0.5 / STEP 0.6 ──────────
PERMISSION_MODE        = "bypassPermissions"   # Autonomous. Use "acceptEdits" for Governed.
AUTO_LOOP              = True                  # Autonomous. False = one cycle then stop for review.
MAX_TURNS              = 160                   # Hard cap per orchestrator cycle.
ALLOW_FANOUT           = True                  # True = orchestrator may use `claude -p` fan-out for homogeneous batches. False in Governed.
FANOUT_CONCURRENCY     = 3                     # Max parallel `claude -p` processes. 3 is the safe ceiling for Max 5x.
FANOUT_PER_INVOC_TURNS = 30                    # --max-turns for each fan-out worker.
# ───────────────────────────────────────────────────────────────────────


def check_auth() -> None:
    """Refuse to run on a metered API key (which silently overrides OAuth).
    Applies to both SDK calls and any `claude -p` invocations the orchestrator
    launches — both honor the same precedence."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(
            "ANTHROPIC_API_KEY is set and would override your Claude subscription.\n"
            "Run:  unset ANTHROPIC_API_KEY   then re-run.\n"
            "Authenticate the subscription with:  claude setup-token"
        )
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        print(
            "Note: CLAUDE_CODE_OAUTH_TOKEN not in env. If you haven't run "
            "`claude setup-token`, do so before running unattended."
        )


# Orchestrator system prompt — KEEP LEAN. 5-minute cache TTL means this gets
# re-billed on most cycle gaps; worker-applicable rules live in CLAUDE.md.
_FANOUT_STATE = "ENABLED" if ALLOW_FANOUT else "DISABLED"
ORCHESTRATOR_SYSTEM = """
You orchestrate; you do NOT implement. Optimize for correctness first, then for
minimum rate-limit consumption.

Each cycle:
1. Read PLAN.md, TASKS.md, STATUS.md. Read nothing else unless a decision requires it.
2. Evaluate the latest STATUS.md entries against PLAN.md's definition of done.
3. Select next task(s) whose dependencies are complete.
4. Choose a dispatch mode (see below) and dispatch.
5. Reconcile results into STATUS.md and TASKS.md.

DISPATCH MODE — pick by shape of work:

(A) `Task` SUBAGENT — for one task at a time, or 2–4 heterogeneous tasks needing
    coordination. Use `implementer` (Sonnet), `reviewer` (Haiku), or `auditor` (Haiku).
    Tight feedback loop; respects permission_mode.

(B) FAN-OUT `claude -p` SCRIPT — for N >= 3 HOMOGENEOUS items with the same recipe
    and DISJOINT output paths (test per source file, scanner per dimension, JSDoc per
    module, audit finding per directory). Fan-out is __FANOUT_STATE__ in this config.

    TASKS.md flags fan-out candidates explicitly. In particular:
      - TASK-010..TASK-015 (six scanner implementations) are a fan-out candidate
        once TASK-009 (Scanner base) is done.
      - TASK-026 (per-scanner tests) is a fan-out candidate once the scanners
        and TASK-025 (conftest) are done.

    When using fan-out:
    - Use the Write tool to create `.orchestrate/fanout_<task>.sh`.
    - Use the Bash tool to execute it.
    - Concurrency cap: __FANOUT_CONCURRENCY__. Per-invocation `--max-turns __FANOUT_PER_INVOC_TURNS__`.
    - Each invocation gets the embedded PLAN.md slice plus its ONE item.
    - Each invocation writes its WORK PRODUCT (code, tests, docs) to disk. Do NOT
      have parallel invocations write to STATUS.md — race condition. Each writes
      a small JSON result file under `.orchestrate/results/<id>.json`.
    - After the batch completes, YOU read the result files and write ONE STATUS.md
      entry per item, sequentially.

    Script template (adapt items and prompt; bash `${...}` syntax intentional):
    Use a bash script that:
      - sets `set -uo pipefail` and creates `.orchestrate/results/`
      - defines a `run_one` function that runs `claude -p "<embedded slice>"`
        with flags `--allowedTools "Read,Edit,Glob,Grep,Write"`,
        `--max-turns __FANOUT_PER_INVOC_TURNS__`,
        `--dangerously-skip-permissions`, `--output-format json`,
        redirecting stdout to `.orchestrate/results/<id>.json` and exit code to
        `.orchestrate/results/<id>.exit`
      - iterates over the item list, launching `run_one "$item" "$id" &` in
        background, and uses `wait -n` when running jobs reach __FANOUT_CONCURRENCY__
      - ends with `wait` to drain remaining background jobs

(C) SEQUENTIAL `claude -p` PIPELINE — for multi-stage work where stage K's
    JSON output feeds stage K+1 (audit -> triage -> fix). Use sparingly; each
    stage pays its own ~20k startup.

GENERAL RULES (all modes):
- Brief workers by EMBEDDING the relevant PLAN.md slice as a quoted block plus
  exact file paths. Never tell a worker to "read PLAN.md."
- NEVER dispatch the same task or same slice to two workers in parallel.
- Never parallelize two workers editing the same file.
- BATCH small sequential tasks that touch overlapping files into ONE worker. For
  example, TASK-001 and TASK-002 can ship as a batched spec — both touch the
  project root and TASK-002 is a one-file addition.
- Route by cost: Sonnet for building, Haiku for read-only review/audit.
  Escalate to Opus ONLY for ambiguous architecture, Scenario A reconciliation,
  or plan reconciliation passes.

After workers return:
- Confirm TASKS.md was updated (you may need to flip [ ]->[x] for fan-out items).
- Write a concise evaluation per task to STATUS.md.
- Every 5 completed tasks: dispatch `reviewer` to verify STATUS claims match code.
- When STATUS.md exceeds ~3000 tokens / ~12 KB: COMPACT — move entries older
  than the last 5 tasks to STATUS_archive.md.

Obey every constraint in PLAN.md and CLAUDE.md. Never print or commit credentials.
Never auto-run an action that is both irreversible and destructive — pause.
""".replace("__FANOUT_STATE__", _FANOUT_STATE) \
   .replace("__FANOUT_CONCURRENCY__", str(FANOUT_CONCURRENCY)) \
   .replace("__FANOUT_PER_INVOC_TURNS__", str(FANOUT_PER_INVOC_TURNS))


WORKER_PROMPT = """
You implement ONE task (or one batched spec). The orchestrator has briefed you with
everything you need. Do not read PLAN/TASKS/STATUS — they will not give you anything
the orchestrator didn't already include. Implement, then follow the finishing
contract in CLAUDE.md. Be terse: no step narration, one sentence of chat confirming
completion.
"""

REVIEWER_PROMPT = """
Read-only verification. Read the most recent STATUS.md entries and the actual code
they describe. Produce a concise structured assessment: what is correct, what is
missing or wrong, what correction tasks are needed. Do not modify code.
"""

AUDITOR_PROMPT = """
Read-only inventory of the existing codebase. Produce a factual snapshot in
STATUS.md: what exists, what works, what is half-done. Use Grep/Glob to navigate;
do not read whole directories. Do not modify code other than appending to STATUS.md.
"""

AGENTS = {
    "implementer": AgentDefinition(
        description="Implements one development task or a batched spec: writes code, edits files, runs tests.",
        prompt=WORKER_PROMPT,
        tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        model="sonnet",
    ),
    "auditor": AgentDefinition(
        description="Read-only. Inventories the existing codebase and writes a factual baseline to STATUS.md.",
        prompt=AUDITOR_PROMPT,
        tools=["Read", "Glob", "Grep", "Edit"],   # Edit only to append STATUS.md
        model="haiku",
    ),
    "reviewer": AgentDefinition(
        description="Read-only. Verifies STATUS.md claims match the real code.",
        prompt=REVIEWER_PROMPT,
        tools=["Read", "Glob", "Grep"],
        model="haiku",
    ),
}


async def run_cycle(prompt: str) -> bool:
    """Run one orchestrator cycle. Returns True on success, False if the run was
    cut short by a rate-limit / session-window exhaustion (in which case a resume
    marker has been written and the caller should stop)."""
    options = ClaudeAgentOptions(
        system_prompt=ORCHESTRATOR_SYSTEM,
        model="claude-sonnet-4-6",          # Sonnet default. Escalate per-prompt only when needed.
        allowed_tools=["Read", "Edit", "Write", "Bash", "Task"],  # Bash+Write needed for fan-out scripts
        agents=AGENTS,
        permission_mode=PERMISSION_MODE,
        setting_sources=["project"],        # loads CLAUDE.md into orchestrator and workers
        max_turns=MAX_TURNS,
        cwd=".",
    )
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(block.text)
            elif isinstance(message, ResultMessage):
                print("\n── cycle complete ──")
        return True
    except Exception as e:
        # Heuristic: detect session-pool exhaustion or rate-limit errors. The SDK
        # surfaces these as exceptions whose string contains 'rate', 'quota',
        # 'limit', or HTTP 429. On a hit, write a resume marker to STATUS.md and
        # exit cleanly so the next run picks up where we stopped.
        msg = str(e).lower()
        if any(s in msg for s in ("rate", "quota", "limit", "429", "exceeded", "turns", "maximum")):
            from datetime import datetime
            marker = (
                f"\n\n## RESUME MARKER ({datetime.utcnow().isoformat()}Z)\n"
                f"- session window or rate limit hit mid-cycle\n"
                f"- error: {e!r}\n"
                f"- next `python orchestrate.py` invocation will resume from current TASKS/STATUS state\n"
            )
            try:
                with open("STATUS.md", "a") as f:
                    f.write(marker)
            except OSError:
                pass
            print(
                "\n── session limit hit. State written to STATUS.md. "
                "Re-run after your 5-hour window resets. ──"
            )
            return False
        raise


def has_open_tasks() -> bool:
    try:
        with open("TASKS.md") as f:
            return "- [ ]" in f.read()
    except FileNotFoundError:
        return False


async def main(goal: str | None):
    check_auth()
    first = goal or (
        "Read PLAN.md, TASKS.md, STATUS.md. Evaluate progress and dispatch the "
        "next appropriate task(s). Brief workers with embedded slices, not file pointers."
    )
    if not await run_cycle(first):
        return
    if AUTO_LOOP:
        while has_open_tasks():
            await asyncio.sleep(3)
            ok = await run_cycle(
                "Read PLAN.md, TASKS.md, STATUS.md. Evaluate latest results and "
                "dispatch the next task(s). Compact STATUS.md if it has grown past "
                "~3000 tokens."
            )
            if not ok:
                return


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--goal-file":
        goal = open(sys.argv[2]).read().strip()
    else:
        goal = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    asyncio.run(main(goal))
