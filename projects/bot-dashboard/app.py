#!/usr/bin/env python3
"""
Claude Builder — Web control panel.
Serves status, start/stop/run-now, and log tail. Bind to 127.0.0.1 only.
"""
import json
import os
import subprocess
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

# Repo root: this file is projects/bot-dashboard/app.py
WORKSPACE = Path(__file__).resolve().parent.parent.parent
STATE_FILE = WORKSPACE / ".state" / "session.json"
LOG_DIR = WORKSPACE / "logs"
RUNNER_LOG = LOG_DIR / "runner.log"
PROGRESS_PATH = WORKSPACE / "PROGRESS.md"
JOURNAL_PATH = WORKSPACE / "JOURNAL.md"
LABEL = "dev.kgeng.claude-builder"

APP_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(APP_DIR / "static"), template_folder=str(APP_DIR / "templates"))


def _launchd_running() -> bool:
    try:
        uid = os.getuid()
        domain = f"gui/{uid}"
        r = subprocess.run(
            ["launchctl", "print", f"{domain}/{LABEL}"],
            cwd=str(WORKSPACE),
            capture_output=True,
            timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/debug")
def api_debug():
    """Return workspace and paths so you can verify the server is reading the right place."""
    return jsonify({
        "workspace": str(WORKSPACE),
        "state_file": str(STATE_FILE),
        "state_exists": STATE_FILE.exists(),
        "runner_log": str(RUNNER_LOG),
        "runner_log_exists": RUNNER_LOG.exists(),
    })


@app.route("/api/status")
def api_status():
    """Session state + launchd running or not."""
    data = {"launchd_running": _launchd_running(), "session": None}
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                data["session"] = json.load(f)
        except Exception as e:
            data["session_error"] = str(e)
    else:
        data["session_error"] = f"State file not found: {STATE_FILE}"
    return jsonify(data)


@app.route("/api/logs")
def api_logs():
    """Last N lines of runner.log (default 300)."""
    n = min(int(request.args.get("n", 300)), 2000)
    if not RUNNER_LOG.exists():
        return jsonify({"lines": [], "path": str(RUNNER_LOG)})
    try:
        with open(RUNNER_LOG) as f:
            lines = f.readlines()
        tail = lines[-n:] if len(lines) > n else lines
        return jsonify({"lines": tail, "path": str(RUNNER_LOG)})
    except Exception as e:
        return jsonify({"error": str(e), "lines": []}), 500


@app.route("/api/progress")
def api_progress():
    """PROGRESS.md content."""
    if not PROGRESS_PATH.exists():
        return jsonify({"content": "", "error": "PROGRESS.md not found"})
    try:
        return jsonify({"content": PROGRESS_PATH.read_text()})
    except Exception as e:
        return jsonify({"content": "", "error": str(e)}), 500


@app.route("/api/journal")
def api_journal():
    """JOURNAL.md content (last N chars or full)."""
    if not JOURNAL_PATH.exists():
        return jsonify({"content": "", "error": "JOURNAL.md not found"})
    try:
        content = JOURNAL_PATH.read_text()
        max_chars = request.args.get("max")
        if max_chars:
            n = int(max_chars)
            content = content[-n:] if len(content) > n else content
        return jsonify({"content": content})
    except Exception as e:
        return jsonify({"content": "", "error": str(e)}), 500


@app.route("/api/start", methods=["POST"])
def api_start():
    """Start the builder (launchd + first cycle)."""
    payload = request.get_json(silent=True) or {}
    cycles = payload.get("cycles", 48)
    run_now = payload.get("run_now", True)
    args = ["bash", str(WORKSPACE / "scripts" / "start.sh"), "--cycles", str(cycles)]
    if not run_now:
        args.append("--no-run-now")
    try:
        r = subprocess.run(
            args,
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=120,
        )
        return jsonify({
            "ok": r.returncode == 0,
            "stdout": r.stdout or "",
            "stderr": r.stderr or "",
            "returncode": r.returncode,
        })
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "start.sh timed out"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """Stop the builder (unload launchd, zero cycles)."""
    try:
        r = subprocess.run(
            ["bash", str(WORKSPACE / "scripts" / "stop.sh")],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=15,
        )
        return jsonify({
            "ok": r.returncode == 0,
            "stdout": r.stdout or "",
            "stderr": r.stderr or "",
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/run-now", methods=["POST"])
def api_run_now():
    """Run one cycle in the background (does not wait)."""
    try:
        subprocess.Popen(
            ["bash", str(WORKSPACE / "scripts" / "run_cycle.sh")],
            cwd=str(WORKSPACE),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return jsonify({"ok": True, "message": "Cycle started in background."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False, threaded=True)
