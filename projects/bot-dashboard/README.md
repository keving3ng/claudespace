# Claude Builder — Web Control Panel

A local web UI to control and monitor the autonomous Claude build session.

## What it does

- **Status** — Progress bar, runs done/remaining, interval, last run time, launchd running/stopped
- **Controls** — Start session, Stop, Run one cycle now (background)
- **Logs** — Tail of `logs/runner.log` with auto-refresh
- **Progress / Journal** — Read-only view of `PROGRESS.md` and `JOURNAL.md`

Runs on **127.0.0.1 only** (localhost). No auth — intended for single-user local use.

## Run it

From the repo root or from this directory:

```bash
cd projects/bot-dashboard
pip install -q -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5050** in your browser.

To run in the background:

```bash
python app.py &
# or: nohup python app.py > /tmp/dashboard.log 2>&1 &
```

## API (for scripting)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | Session state + `launchd_running` |
| GET | `/api/logs?n=300` | Last N lines of runner.log |
| GET | `/api/progress` | PROGRESS.md content |
| GET | `/api/journal` | JOURNAL.md content |
| POST | `/api/start` | Start session (body: `{"cycles": 48, "run_now": true}`) |
| POST | `/api/stop` | Stop session |
| POST | `/api/run-now` | Run one cycle in background |

## Requirements

- Python 3.8+
- Flask
- Scripts and paths assume the repo root is the workspace (same as `scripts/start.sh`).
