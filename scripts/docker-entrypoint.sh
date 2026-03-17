#!/usr/bin/env bash
# Docker entrypoint: start Discord bridge (if configured), then run Flask.
set -euo pipefail
WORKSPACE="${CLAUDESPACE_ROOT:-/app}"
export CLAUDESPACE_ROOT="$WORKSPACE"
PID_FILE="$WORKSPACE/.state/discord_bridge.pid"
LOG_FILE="$WORKSPACE/logs/discord-bridge.log"
BOT_DIR="$WORKSPACE/projects/discord-bridge"

mkdir -p "$WORKSPACE/.state" "$WORKSPACE/logs"

# Start Discord bot in background if token is set
if [[ -n "${DISCORD_BOT_TOKEN:-}" ]] && [[ "$DISCORD_BOT_TOKEN" != "your_bot_token_here" ]]; then
  if [[ -f "$BOT_DIR/bot.py" ]]; then
    cd "$BOT_DIR"
    python3 bot.py >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "[entrypoint] Discord bridge started (PID $(cat "$PID_FILE"))."
  fi
  cd "$WORKSPACE"
fi

# Run Flask (foreground)
exec python3 "$WORKSPACE/projects/bot-dashboard/app.py"
