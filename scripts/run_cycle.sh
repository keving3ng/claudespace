#!/usr/bin/env bash
# run_cycle.sh — runs one autonomous build cycle, called by launchd every hour
set -euo pipefail

WORKSPACE="/Users/kevingeng/code/claudespace"
STATE_FILE="$WORKSPACE/.state/session.json"
LOG_DIR="$WORKSPACE/logs"
CLAUDE_BIN="/Users/kevingeng/.local/bin/claude"
LABEL="dev.kgeng.claude-builder"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"

mkdir -p "$LOG_DIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_DIR/runner.log"; }

# --- Read state ---
if [[ ! -f "$STATE_FILE" ]]; then
    log "ERROR: State file not found at $STATE_FILE. Was start.sh run?"
    exit 1
fi

cycles_remaining=$(python3 -c "import json; print(json.load(open('$STATE_FILE'))['cycles_remaining'])")
cycle_num=$(python3 -c "import json; d=json.load(open('$STATE_FILE')); print(d['cycles_total'] - d['cycles_remaining'] + 1)")

log "=== Cycle ${cycle_num} | ${cycles_remaining} cycles remaining ==="

# --- Check if done ---
if [[ "$cycles_remaining" -le 0 ]]; then
    log "All cycles complete. Unloading launchd job."
    launchctl unload "$PLIST" 2>/dev/null || true
    exit 0
fi

# --- Decrement counter ---
python3 - <<EOF
import json, datetime
with open('$STATE_FILE', 'r') as f:
    state = json.load(f)
state['cycles_remaining'] -= 1
state['last_run_at'] = datetime.datetime.now().isoformat()
state['last_cycle_num'] = state['cycles_total'] - state['cycles_remaining']
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f, indent=2)
EOF

# --- Run Claude ---
log "Invoking Claude Code..."

CLAUDE_PROMPT="You are running autonomous build cycle ${cycle_num} of $(python3 -c "import json; print(json.load(open('$STATE_FILE'))['cycles_total'])") for Kevin Geng.

STEP 1: Read these files in order:
- $WORKSPACE/CLAUDE.md  (your master instructions and project roadmap)
- $WORKSPACE/PROGRESS.md  (current state, what was last built, and NEXT_TASK)

STEP 2: Execute the NEXT_TASK described in PROGRESS.md. Write real, working code to $WORKSPACE/projects/. Be creative and build something Kevin will actually find useful. Each cycle should produce at least one meaningful new file or significant improvement.

STEP 3: Update $WORKSPACE/PROGRESS.md — increment RUN_COUNT by 1, add a row to Session Log describing what you built this cycle, update NEXT_TASK with the logical next step.

Be a pragmatic builder. Write code that actually works. Have fun with it."

cd "$WORKSPACE"

# Timeout after 50 minutes so we don't bleed into the next cycle
timeout 3000 "$CLAUDE_BIN" \
    --dangerously-skip-permissions \
    --print \
    "$CLAUDE_PROMPT" \
    >> "$LOG_DIR/cycle-${cycle_num}.log" 2>&1 || {
    log "WARNING: Claude exited with non-zero status (may have timed out or errored). Continuing."
}

# --- Git commit ---
log "Committing changes..."
cd "$WORKSPACE"
git add -A

if git diff --cached --quiet; then
    log "No changes to commit this cycle."
else
    # Pull the last session log line from PROGRESS.md for a meaningful commit message
    last_entry=$(grep "^| $((cycle_num))" "$WORKSPACE/PROGRESS.md" 2>/dev/null | head -1 | sed 's/.*| //' | cut -c1-80 || echo "build work")
    git commit -m "Cycle ${cycle_num}: ${last_entry}" \
        --author="Claude Code <claude@anthropic.com>" \
        || git commit -m "Build cycle ${cycle_num} — $(date '+%Y-%m-%d %H:%M')" \
            --author="Claude Code <claude@anthropic.com>"
    log "Changes committed."
fi

# --- Push to GitHub ---
log "Pushing to GitHub..."
git push origin main >> "$LOG_DIR/cycle-${cycle_num}.log" 2>&1 && log "Pushed to GitHub." || log "WARNING: git push failed (check SSH keys / network)."

# --- Auto-stop if final cycle ---
cycles_remaining_now=$(python3 -c "import json; print(json.load(open('$STATE_FILE'))['cycles_remaining'])")
if [[ "$cycles_remaining_now" -le 0 ]]; then
    log "Final cycle complete!"
    launchctl unload "$PLIST" 2>/dev/null || true
    log "launchd job unloaded. Session complete."
fi

log "=== Cycle ${cycle_num} done ==="
