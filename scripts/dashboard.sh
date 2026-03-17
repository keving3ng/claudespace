#!/usr/bin/env bash
# One-click start: Discord bridge (if configured) + web control panel (localhost:5050)
set -euo pipefail
WORKSPACE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WORKSPACE/projects/bot-dashboard"
# Only run pip if Flask isn't installed (avoids repeated hashlib/blake2 noise on some pyenv setups)
python3 -c "import flask" 2>/dev/null || pip install -q -r requirements.txt
# Ensure discord-bridge deps if we might start the bot
if [[ -f "$WORKSPACE/projects/discord-bridge/.env" ]]; then
  python3 -c "import discord" 2>/dev/null || (cd "$WORKSPACE/projects/discord-bridge" && pip install -q -r requirements.txt)
fi
# Start Discord bridge if configured (no-op if not configured or already running)
"$WORKSPACE/scripts/discord_bridge.sh" start || true
exec python3 app.py
