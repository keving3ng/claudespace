#!/usr/bin/env bash
# Start the web control panel (localhost:5050)
set -euo pipefail
WORKSPACE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WORKSPACE/projects/bot-dashboard"
pip install -q -r requirements.txt
exec python app.py
