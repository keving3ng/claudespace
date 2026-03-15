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

# --- Prune log files for cycles that never completed (no journal entry) ---
"$WORKSPACE/scripts/cleanup_failed_logs.sh" 2>/dev/null || true

# --- Read state ---
if [[ ! -f "$STATE_FILE" ]]; then
    log "ERROR: State file not found at $STATE_FILE. Was start.sh run?"
    exit 1
fi

cycles_remaining=$(python3 -c "import json; print(json.load(open('$STATE_FILE'))['cycles_remaining'])")

log "=== Run started | ${cycles_remaining} runs remaining in session ==="

# --- Check if done ---
if [[ "$cycles_remaining" -le 0 ]]; then
    log "Session complete (no runs remaining). Unloading launchd job."
    LAUNCHD_DOMAIN="gui/$(id -u)"
    launchctl bootout "$LAUNCHD_DOMAIN" "$PLIST" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
    exit 0
fi

# --- Decrement runs remaining (so failed runs still consume a slot) ---
python3 - <<EOF
import json, datetime
with open('$STATE_FILE', 'r') as f:
    state = json.load(f)
state['cycles_remaining'] -= 1
state['last_run_at'] = datetime.datetime.now().isoformat()
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f, indent=2)
EOF

# --- Run Claude ---
RUN_TS=$(date +%Y%m%d-%H%M%S)
CYCLE_LOG="$LOG_DIR/run-${RUN_TS}.log"
cd "$WORKSPACE"

# Timeout after 50 minutes so we don't bleed into the next cycle.
# On macOS, only gtimeout (brew install coreutils) is reliable; avoid bare "timeout" so we
# don't break when launchd has a different PATH or timeout isn't installed.
TIMEOUT_BIN=""
if [[ "$(uname -s)" = Darwin ]]; then
    TIMEOUT_BIN=$(command -v gtimeout 2>/dev/null || true)
else
    TIMEOUT_BIN=$(command -v timeout 2>/dev/null || true)
fi
# Only use timeout if we got an absolute path we can execute (avoids "command not found" under launchd)
[[ -z "$TIMEOUT_BIN" || "$TIMEOUT_BIN" != /* || ! -x "$TIMEOUT_BIN" ]] && TIMEOUT_BIN=""

log "Invoking Claude Code..."
log "  → Live output: tail -f $CYCLE_LOG"
if [[ -n "$TIMEOUT_BIN" ]]; then
    log "  → Timeout: 50 min (gtimeout)."
else
    log "  → No timeout; Claude runs until done."
fi
log "  → Waiting for Claude (this may take several minutes)..."

# Single source of truth: CLAUDE.md (non-negotiables, session protocol, journal format). Script only says "go."
CLAUDE_PROMPT="You're in an autonomous build run. Follow CLAUDE.md: run the non-negotiables and session protocol. Start by reading CLAUDE.md, then PROGRESS.md and JOURNAL.md."

CLAUDE_ARGS=(--dangerously-skip-permissions --print "$CLAUDE_PROMPT")

set +e
if [[ -n "$TIMEOUT_BIN" ]]; then
    "$TIMEOUT_BIN" 3000 "$CLAUDE_BIN" "${CLAUDE_ARGS[@]}" 2>&1 | tee -a "$CYCLE_LOG" >> "$LOG_DIR/runner.log"
else
    "$CLAUDE_BIN" "${CLAUDE_ARGS[@]}" 2>&1 | tee -a "$CYCLE_LOG" >> "$LOG_DIR/runner.log"
fi
CLAUDE_EXIT=${PIPESTATUS[0]}
set -e

if [[ $CLAUDE_EXIT -eq 0 ]]; then
    log "Claude finished successfully (exit 0)."
else
    log "WARNING: Claude exited with status $CLAUDE_EXIT (timeout or error). Continuing."
fi

# --- Git commit ---
log "Committing changes..."
cd "$WORKSPACE"
git add -A

if git diff --cached --quiet; then
    log "No changes to commit this run."
else
    git commit -m "Autonomous build — $(date '+%Y-%m-%d %H:%M')" \
        --author="Claude Code <claude@anthropic.com>"
    log "Changes committed."
fi

# --- Push to GitHub ---
log "Pushing to GitHub..."
git push origin main >> "$CYCLE_LOG" 2>&1 && log "Pushed to GitHub." || log "WARNING: git push failed (check SSH keys / network)."

# --- Discord notification ---
DISCORD_POST="$WORKSPACE/projects/discord-bridge/post.py"
DISCORD_ENV="$WORKSPACE/projects/discord-bridge/.env"
if [[ -f "$DISCORD_POST" ]] && [[ -f "$DISCORD_ENV" ]]; then
    # Extract NEXT_TASK from PROGRESS.md (first line of the NEXT_TASK value)
    NEXT_TASK=$(python3 -c "
import re, sys
try:
    text = open('$WORKSPACE/PROGRESS.md').read()
    m = re.search(r'\*\*NEXT_TASK:\*\*\s*(.*?)(?=\n##|\Z)', text, re.DOTALL)
    if m:
        line = m.group(1).strip().split('\n')[0][:120]
        print(line)
    else:
        print('(see PROGRESS.md)')
except Exception as e:
    print('(see PROGRESS.md)')
" 2>/dev/null || echo "(see PROGRESS.md)")
    CYCLE_NUM=$(python3 -c "
try:
    import re
    text = open('$WORKSPACE/PROGRESS.md').read()
    m = re.search(r'\*\*RUN_COUNT:\*\*\s*(\d+)', text)
    print(m.group(1) if m else '?')
except:
    print('?')
" 2>/dev/null || echo "?")
    MSG="**Cycle ${CYCLE_NUM} complete** — $(date '+%Y-%m-%d %H:%M')
**Next:** ${NEXT_TASK}"
    python3 "$DISCORD_POST" "$MSG" 2>/dev/null && log "Discord notification sent." || log "Discord notification skipped (webhook not configured or failed)."
fi

# --- Auto-stop when no runs remaining ---
cycles_remaining_now=$(python3 -c "import json; print(json.load(open('$STATE_FILE'))['cycles_remaining'])")
if [[ "$cycles_remaining_now" -le 0 ]]; then
    log "No runs remaining. Unloading launchd job."
    LAUNCHD_DOMAIN="gui/$(id -u)"
    launchctl bootout "$LAUNCHD_DOMAIN" "$PLIST" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
    log "Session complete."
fi

log "=== Run done ==="
