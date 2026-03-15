#!/usr/bin/env bash
# cleanup_failed_logs.sh — remove log files for cycles that never completed (no journal entry)
# Uses JOURNAL.md as source of truth: only cycles with a "## Cycle N" entry are considered successful.
set -euo pipefail

WORKSPACE="/Users/kevingeng/code/claudespace"
JOURNAL="$WORKSPACE/JOURNAL.md"
LOG_DIR="$WORKSPACE/logs"

if [[ ! -f "$JOURNAL" ]]; then
    echo "No JOURNAL.md; nothing to clean."
    exit 0
fi

# Cycle numbers that have a journal entry (e.g. "## Cycle 0 (Setup)" or "## Cycle 2 —")
completed_cycles=$(grep -E '^## Cycle [0-9]+' "$JOURNAL" | sed -E 's/^## Cycle ([0-9]+).*/\1/' | sort -n -u)
removed=0

for log in "$LOG_DIR"/cycle-*.log; do
    [[ -e "$log" ]] || continue
    base=$(basename "$log" .log)
    num="${base#cycle-}"
    if [[ "$num" =~ ^[0-9]+$ ]]; then
        if echo "$completed_cycles" | grep -q "^${num}$"; then
            : # keep it
        else
            echo "Removing $log (no journal entry for Cycle $num)"
            rm -f "$log"
            ((removed++)) || true
        fi
    fi
done

[[ $removed -eq 0 ]] || echo "Cleaned up $removed failed-cycle log(s)."