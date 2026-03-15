#!/usr/bin/env bash
# start.sh — kick off a new autonomous Claude build session
# Usage: ./scripts/start.sh [--cycles N] [--now]
#   --cycles N   Number of hourly build cycles (default: 48)
#   --now        Run the first cycle immediately (default: true)
set -euo pipefail

WORKSPACE="/Users/kevingeng/code/claudespace"
LABEL="dev.kgeng.claude-builder"
PLIST_DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"
STATE_FILE="$WORKSPACE/.state/session.json"
CLAUDE_BIN="/Users/kevingeng/.local/bin/claude"
INTERVAL_SECONDS=3600  # 1 hour

# --- Parse args ---
CYCLES=48
RUN_NOW=true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --cycles) CYCLES="$2"; shift 2 ;;
        --no-run-now) RUN_NOW=false; shift ;;
        --interval) INTERVAL_SECONDS="$2"; shift 2 ;;  # e.g. --interval 300 for testing every 5m
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Claude Autonomous Builder — start.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Cycles:   $CYCLES"
echo "  Interval: ${INTERVAL_SECONDS}s ($(( INTERVAL_SECONDS / 60 )) min)"
echo "  Run now:  $RUN_NOW"
echo ""

# --- Safety check ---
if [[ ! -x "$CLAUDE_BIN" ]]; then
    echo "ERROR: claude not found at $CLAUDE_BIN"
    echo "Update CLAUDE_BIN in this script to the correct path."
    echo "Find it with: which claude"
    exit 1
fi

# --- Init git if needed ---
cd "$WORKSPACE"
if [[ ! -d .git ]]; then
    echo "Initializing git repository..."
    git init
    git add -A
    git commit -m "Initial commit" --author="Claude Code <claude@anthropic.com>"
fi

# --- Write state file ---
mkdir -p "$WORKSPACE/.state"
START_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
SESSION_ID=$(uuidgen | tr '[:upper:]' '[:lower:]' 2>/dev/null || date +%s)

python3 - <<EOF
import json
state = {
    "cycles_total": $CYCLES,
    "cycles_remaining": $CYCLES,
    "interval_seconds": $INTERVAL_SECONDS,
    "started_at": "$START_TIME",
    "session_id": "$SESSION_ID",
    "last_run_at": None,
    "last_cycle_num": 0
}
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f, indent=2)
print(f"  State written: {$CYCLES} cycles remaining")
EOF

# --- Write launchd plist ---
cat > "$PLIST_DEST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${WORKSPACE}/scripts/run_cycle.sh</string>
    </array>

    <!-- Fire every N seconds -->
    <key>StartInterval</key>
    <integer>${INTERVAL_SECONDS}</integer>

    <!-- Run immediately on load -->
    <key>RunAtLoad</key>
    <$([ "$RUN_NOW" = true ] && echo "true" || echo "false")/>

    <!-- Restart on crash, but not if it exits cleanly -->
    <key>KeepAlive</key>
    <false/>

    <!-- Logs -->
    <key>StandardOutPath</key>
    <string>${WORKSPACE}/logs/launchd-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${WORKSPACE}/logs/launchd-stderr.log</string>

    <!-- Environment: ensure common tool paths are available -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/Users/kevingeng/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>/Users/kevingeng</string>
    </dict>
</dict>
</plist>
PLIST_EOF

echo "  Plist written to: $PLIST_DEST"

# --- Unload any existing job ---
launchctl unload "$PLIST_DEST" 2>/dev/null || true

# --- Load the job ---
launchctl load "$PLIST_DEST"
echo "  launchd job loaded: $LABEL"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Session started!"
echo "  $CYCLES cycles × $(( INTERVAL_SECONDS / 60 )) min = ~$(( CYCLES * INTERVAL_SECONDS / 3600 )) hours total"
echo ""
echo "  Monitor:  ./scripts/status.sh"
echo "  Logs:     tail -f logs/runner.log"
echo "  Stop:     ./scripts/stop.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
