#!/usr/bin/env bash
# status.sh — show current session status
set -euo pipefail

WORKSPACE="/Users/kevingeng/code/claudespace"
LABEL="dev.kgeng.claude-builder"
STATE_FILE="$WORKSPACE/.state/session.json"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Claude Builder — Session Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# State file
if [[ -f "$STATE_FILE" ]]; then
    python3 - <<EOF
import json, datetime
with open('$STATE_FILE') as f:
    s = json.load(f)
done = s['cycles_total'] - s['cycles_remaining']
pct = int(done / s['cycles_total'] * 100) if s['cycles_total'] > 0 else 0
bar_filled = int(pct / 5)
bar = '█' * bar_filled + '░' * (20 - bar_filled)
print(f"  Progress: [{bar}] {pct}%")
print(f"  Cycles:   {done}/{s['cycles_total']} complete, {s['cycles_remaining']} remaining")
print(f"  Interval: {s.get('interval_seconds', 3600)//60} min per cycle")
print(f"  Started:  {s.get('started_at', 'unknown')}")
print(f"  Last run: {s.get('last_run_at') or 'not yet'}")
EOF
else
    echo "  No active session. Run ./scripts/start.sh to begin."
fi

echo ""

# launchd status
if launchctl list "$LABEL" &>/dev/null; then
    echo "  launchd: ✓ RUNNING"
else
    echo "  launchd: ✗ not loaded"
fi

echo ""

# Recent git log
echo "  Recent commits:"
git -C "$WORKSPACE" log --oneline -8 2>/dev/null | sed 's/^/    /' || echo "    (no commits yet)"

echo ""
echo "  Logs: tail -f $WORKSPACE/logs/runner.log"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
