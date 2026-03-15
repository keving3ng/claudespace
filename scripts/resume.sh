#!/usr/bin/env bash
# resume.sh — (re)load the launchd job without resetting session state (use after reboot or Load failed: 5)
set -euo pipefail

WORKSPACE="/Users/kevingeng/code/claudespace"
LABEL="dev.kgeng.claude-builder"
PLIST_DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"

if [[ ! -f "$PLIST_DEST" ]]; then
    echo "No plist at $PLIST_DEST. Run ./scripts/start.sh first."
    exit 1
fi

LAUNCHD_DOMAIN="gui/$(id -u)"
launchctl bootout "$LAUNCHD_DOMAIN" "$PLIST_DEST" 2>/dev/null || launchctl unload "$PLIST_DEST" 2>/dev/null || true

if launchctl bootstrap "$LAUNCHD_DOMAIN" "$PLIST_DEST" 2>/dev/null; then
    echo "Job loaded (bootstrap). Run ./scripts/status.sh to confirm."
else
    launchctl load "$PLIST_DEST"
    echo "Job loaded (load). Run ./scripts/status.sh to confirm."
fi
