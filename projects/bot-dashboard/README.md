# Claude Builder — Web Control Panel

A local web UI to control and monitor the autonomous Claude build session and the Discord bridge.

## What it does

- **Status** — Progress bar, runs done/remaining, interval, last run time, launchd running/stopped
- **Controls** — Start session, Stop, Run one cycle now (background)
- **Discord Bridge** — Status (running/stopped/not configured), Start/Stop, and Discord log tab
- **Kegbot** — Run Briefing, PR digest, Matchamap status, Tasks, Weather from the UI; output in Tool output
- **Matchamap tools** — Quality report (on *.geojson in matchamap-tools), Batch export (cities.json)
- **Logs** — Runner log, Discord bridge log, Progress, Journal (tabs)
- **Progress / Journal** — Read-only view of `PROGRESS.md` and `JOURNAL.md`

Runs on **127.0.0.1 only** (localhost) unless you set `FLASK_HOST=0.0.0.0` (e.g. in Docker). No auth — intended for single-user local use.

## One-click start (recommended)

From the **repo root**:

```bash
./scripts/dashboard.sh
```

This starts the **Discord bridge** (if `projects/discord-bridge/.env` exists and is configured) and then the **control panel**. Open **http://127.0.0.1:5050** in your browser.

## Run it (dashboard only)

From the repo root or from this directory:

```bash
cd projects/bot-dashboard
pip install -q -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5050** in your browser.

## API (for scripting)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | Session state + `launchd_running` |
| GET | `/api/debug` | Workspace paths and whether state/log files exist (for diagnostics) |
| GET | `/api/logs?n=300` | Last N lines of runner.log |
| GET | `/api/progress` | PROGRESS.md content |
| GET | `/api/journal` | JOURNAL.md content |
| POST | `/api/start` | Start session (body: `{"cycles": 48, "run_now": true}`) |
| POST | `/api/stop` | Stop session |
| POST | `/api/run-now` | Run one cycle in background |
| GET | `/api/discord/status` | Discord bridge: `running`, `configured`, `status` |
| POST | `/api/discord/start` | Start Discord bridge |
| POST | `/api/discord/stop` | Stop Discord bridge |
| GET | `/api/discord/logs?n=200` | Last N lines of discord-bridge.log |
| GET | `/api/kegbot/configured` | Whether kegbot .env is set |
| POST | `/api/kegbot/run` | Run kegbot command (body: `{"command": "briefing"\|"prs"\|"matchamap status"\|"tasks"\|"weather", "args": []}`) |
| POST | `/api/matchamap/quality-report` | Run quality_report.py (body: `{"paths": []}` optional) |
| POST | `/api/matchamap/batch-export` | Run batch_export.py (body: `{"config": "cities.json"}` optional) |

## Running with Docker (Unraid or any host)

One container runs both the **Discord bridge** (if configured) and the **control panel**.

From the **repo root**:

```bash
docker build -t claudespace-dashboard .
docker run -d -p 5050:5050 -v "$(pwd)/.state:/app/.state" -v "$(pwd)/logs:/app/logs" --name claudespace claudespace-dashboard
```

Or with Docker Compose:

```bash
docker compose up -d
```

Then open **http://localhost:5050** (or your host IP). To enable the Discord bridge inside the container, pass Discord env vars (e.g. `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID`, `DISCORD_KEVIN_USER_ID`, `DISCORD_WEBHOOK_URL`) or add `env_file: - projects/discord-bridge/.env` to `docker-compose.yml` and create that file from `projects/discord-bridge/README.md`.

**Unraid:** Use the Docker Compose Manager plugin and point it at this repo’s `docker-compose.yml`, or add the image as a custom container with port 5050 and the same env/volumes. Mount `.state` and `logs` to a Unraid path so data persists.

## Troubleshooting

- **`ValueError: unsupported hash type blake2b` (and blake2s)** — Common with pyenv Python on macOS when the Python build’s OpenSSL doesn’t support blake2. The dashboard usually still starts and works; the errors are from hashlib at import time. To fix properly: reinstall Python with Homebrew OpenSSL, e.g. `LDFLAGS="-L$(brew --prefix openssl)/lib" CPPFLAGS="-I$(brew --prefix openssl)/include" pyenv install 3.12.12`. Or use system Python: `python3` from `/usr/bin` if you prefer.
- **`/api/debug` returns 404** — Restart the dashboard (Ctrl+C, then `./scripts/dashboard.sh` again) so the running process loads the latest code.

## Requirements

- Python 3.8+
- Flask
- Scripts and paths assume the repo root is the workspace (same as `scripts/start.sh`).
