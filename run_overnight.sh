#!/bin/bash
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a overnight.log; }
log "=== Run started ==="
while grep -q '^\- \[ \]' TASKS.md 2>/dev/null; do
    log "Open tasks found — starting cycle..."
    python orchestrate.py >> overnight.log 2>&1 || true
    if grep -q '^\- \[ \]' TASKS.md 2>/dev/null; then
        log "Tasks remain. Sleeping 5h30m for window reset..."
        sleep 19800
        log "Waking — next cycle."
    fi
done
log "=== All tasks complete ==="
