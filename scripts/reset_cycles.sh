#!/usr/bin/env bash
# reset_cycles.sh — set or top up "runs remaining" after wasted/failed cycles
# Usage: ./scripts/reset_cycles.sh [N]     → set remaining to N (default 48)
#        ./scripts/reset_cycles.sh --add N → add N to current remaining
set -euo pipefail

WORKSPACE="/Users/kevingeng/code/claudespace"
STATE_FILE="$WORKSPACE/.state/session.json"

if [[ ! -f "$STATE_FILE" ]]; then
    echo "No session state. Run ./scripts/start.sh first."
    exit 1
fi

if [[ "${1:-}" = "--add" ]]; then
    ADD="${2:?Usage: reset_cycles.sh --add N}"
    python3 -c "
import json
with open('$STATE_FILE', 'r') as f:
    s = json.load(f)
old = s['cycles_remaining']
s['cycles_remaining'] = old + $ADD
with open('$STATE_FILE', 'w') as f:
    json.dump(s, f, indent=2)
print(f'  Added $ADD runs. Remaining: {old} → {s[\"cycles_remaining\"]}')
"
else
    N="${1:-48}"
    python3 - <<EOF
import json
with open('$STATE_FILE', 'r') as f:
    s = json.load(f)
s['cycles_remaining'] = $N
with open('$STATE_FILE', 'w') as f:
    json.dump(s, f, indent=2)
print(f"  Runs remaining set to $N")
EOF
fi

echo "  Run ./scripts/status.sh to confirm."
