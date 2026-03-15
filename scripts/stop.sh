#!/usr/bin/env bash
# stop.sh — stop the running Claude build session
set -euo pipefail

WORKSPACE="/Users/kevingeng/code/claudespace"
LABEL="dev.kgeng.claude-builder"
PLIST_DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"
STATE_FILE="$WORKSPACE/.state/session.json"

echo "Stopping Claude builder session..."

# Zero out cycles so run_cycle.sh won't proceed if mid-run
if [[ -f "$STATE_FILE" ]]; then
    python3 - <<EOF
import json
with open('$STATE_FILE', 'r') as f:
    state = json.load(f)
state['cycles_remaining'] = 0
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f, indent=2)
print(f"  Cycles zeroed out.")
EOF
fi

LAUNCHD_DOMAIN="gui/$(id -u)"
if launchctl bootout "$LAUNCHD_DOMAIN" "$PLIST_DEST" 2>/dev/null || launchctl unload "$PLIST_DEST" 2>/dev/null; then
    echo "  launchd job unloaded."
else
    echo "  (job was not loaded)"
fi
echo "Done."
