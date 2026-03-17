#!/usr/bin/env bash
# discord_bridge.sh — start / stop / status for the Discord bridge (bot.py)
# Usage: ./scripts/discord_bridge.sh start | stop | status
# PID file: .state/discord_bridge.pid
# Log file: logs/discord-bridge.log
set -euo pipefail

WORKSPACE="$(cd "$(dirname "$0")/.." && pwd)"
DISCORD_DIR="$WORKSPACE/projects/discord-bridge"
ENV_FILE="$DISCORD_DIR/.env"
PID_FILE="$WORKSPACE/.state/discord_bridge.pid"
LOG_FILE="$WORKSPACE/logs/discord-bridge.log"

is_configured() {
  [[ -f "$ENV_FILE" ]]
}

is_running() {
  [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

cmd_status() {
  if ! is_configured; then
    echo "not configured"
    return 0
  fi
  if is_running; then
    echo "running"
  else
    echo "stopped"
  fi
}

cmd_stop() {
  if ! [[ -f "$PID_FILE" ]]; then
    echo "Discord bridge not running (no PID file)."
    return 0
  fi
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    kill -TERM "$PID" 2>/dev/null || true
    echo "Stopped Discord bridge (PID $PID)."
  fi
  rm -f "$PID_FILE"
}

cmd_start() {
  if ! is_configured; then
    echo "Discord bridge not configured: $ENV_FILE not found."
    return 0
  fi
  if is_running; then
    echo "Discord bridge already running (PID $(cat "$PID_FILE"))."
    return 0
  fi
  mkdir -p "$WORKSPACE/logs" "$WORKSPACE/.state"
  cd "$DISCORD_DIR"
  export CLAUDESPACE_ROOT="$WORKSPACE"
  python3 bot.py >> "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  echo "Discord bridge started (PID $(cat "$PID_FILE"))."
}

case "${1:-}" in
  start)  cmd_start ;;
  stop)   cmd_stop ;;
  status) cmd_status ;;
  *)      echo "Usage: $0 start | stop | status"; exit 1 ;;
esac
