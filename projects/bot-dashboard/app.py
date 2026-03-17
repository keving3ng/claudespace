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
DISCORD_BRIDGE_DIR = WORKSPACE / "projects" / "discord-bridge"
DISCORD_PID_FILE = WORKSPACE / ".state" / "discord_bridge.pid"
DISCORD_LOG = WORKSPACE / "logs" / "discord-bridge.log"
DISCORD_BRIDGE_SCRIPT = WORKSPACE / "scripts" / "discord_bridge.sh"
KEGBOT_DIR = WORKSPACE / "projects" / "kegbot-claude"
KEGBOT_SCRIPT = KEGBOT_DIR / "kegbot.py"
MATCHAMAP_DIR = WORKSPACE / "projects" / "matchamap-tools"

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
    resp = send_from_directory(app.static_folder, "index.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


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


# ── Discord bridge ───────────────────────────────────────────────────────────

def _discord_status() -> str:
    """Run discord_bridge.sh status; return 'running' | 'stopped' | 'not configured'."""
    try:
        r = subprocess.run(
            ["bash", str(DISCORD_BRIDGE_SCRIPT), "status"],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return (r.stdout or "").strip() or "stopped"
    except Exception:
        return "stopped"


@app.route("/api/discord/status")
def api_discord_status():
    """Discord bridge: running, stopped, or not configured."""
    status = _discord_status()
    configured = (DISCORD_BRIDGE_DIR / ".env").exists()
    return jsonify({
        "running": status == "running",
        "configured": configured,
        "status": status,
    })


@app.route("/api/discord/start", methods=["POST"])
def api_discord_start():
    """Start the Discord bridge (bot.py)."""
    try:
        r = subprocess.run(
            ["bash", str(DISCORD_BRIDGE_SCRIPT), "start"],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=15,
        )
        return jsonify({
            "ok": True,
            "message": (r.stdout or "").strip() or "Started.",
            "stdout": r.stdout or "",
            "stderr": r.stderr or "",
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/discord/stop", methods=["POST"])
def api_discord_stop():
    """Stop the Discord bridge."""
    try:
        r = subprocess.run(
            ["bash", str(DISCORD_BRIDGE_SCRIPT), "stop"],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return jsonify({
            "ok": True,
            "message": (r.stdout or "").strip() or "Stopped.",
            "stdout": r.stdout or "",
            "stderr": r.stderr or "",
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/discord/logs")
def api_discord_logs():
    """Last N lines of discord-bridge.log (default 200)."""
    n = min(int(request.args.get("n", 200)), 2000)
    if not DISCORD_LOG.exists():
        return jsonify({"lines": [], "path": str(DISCORD_LOG)})
    try:
        with open(DISCORD_LOG) as f:
            lines = f.readlines()
        tail = lines[-n:] if len(lines) > n else lines
        return jsonify({"lines": tail, "path": str(DISCORD_LOG)})
    except Exception as e:
        return jsonify({"error": str(e), "lines": []}), 500


# ── Kegbot ────────────────────────────────────────────────────────────────────

@app.route("/api/kegbot/configured")
def api_kegbot_configured():
    """True if kegbot has .env or ANTHROPIC_API_KEY set."""
    env_file = KEGBOT_DIR / ".env"
    configured = env_file.exists() or bool(os.environ.get("ANTHROPIC_API_KEY"))
    return jsonify({"configured": configured})


@app.route("/api/kegbot/run", methods=["POST"])
def api_kegbot_run():
    """Run a kegbot command. Body: { "command": "briefing"|"prs"|..., "args": [] }."""
    payload = request.get_json(silent=True) or {}
    command = (payload.get("command") or "").strip()
    args = payload.get("args") or []
    if not command:
        return jsonify({"ok": False, "error": "Missing command"}), 400
    allowed = ("briefing", "prs", "matchamap", "tasks", "weather", "help")
    cmd_first = command.split()[0] if command else ""
    if cmd_first not in allowed:
        return jsonify({"ok": False, "error": f"Unknown command: {command}"}), 400
    argv = command.split() + list(args)
    timeout = 120 if command == "briefing" else (90 if command == "tasks" else 60)
    try:
        r = subprocess.run(
            [os.environ.get("python3", "python3"), str(KEGBOT_SCRIPT)] + argv,
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return jsonify({
            "ok": r.returncode == 0,
            "stdout": r.stdout or "",
            "stderr": r.stderr or "",
            "returncode": r.returncode,
        })
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": f"Timed out after {timeout}s", "stdout": "", "stderr": ""}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "stdout": "", "stderr": ""}), 500


# ── Matchamap tools ───────────────────────────────────────────────────────────

@app.route("/api/matchamap/quality-report", methods=["POST"])
def api_matchamap_quality_report():
    """Run quality_report.py on GeoJSON file(s). Body: { "paths": [] } or default *.geojson in matchamap-tools."""
    payload = request.get_json(silent=True) or {}
    paths = payload.get("paths") or []
    if not paths:
        geojson_files = sorted(MATCHAMAP_DIR.glob("*.geojson"))
        paths = [str(f) for f in geojson_files]
    if not paths:
        return jsonify({"ok": True, "stdout": "No .geojson files in matchamap-tools.", "stderr": "", "returncode": 0})
    script = MATCHAMAP_DIR / "quality_report.py"
    if not script.exists():
        return jsonify({"ok": False, "error": "quality_report.py not found", "stdout": "", "stderr": ""}), 500
    try:
        r = subprocess.run(
            [os.environ.get("python3", "python3"), str(script)] + paths,
            cwd=str(MATCHAMAP_DIR),
            capture_output=True,
            text=True,
            timeout=60,
        )
        return jsonify({
            "ok": r.returncode == 0,
            "stdout": r.stdout or "",
            "stderr": r.stderr or "",
            "returncode": r.returncode,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "stdout": "", "stderr": ""}), 500


@app.route("/api/matchamap/batch-export", methods=["POST"])
def api_matchamap_batch_export():
    """Run batch_export.py. Body: { "config": "cities.json" } optional."""
    payload = request.get_json(silent=True) or {}
    config = payload.get("config") or "cities.json"
    script = MATCHAMAP_DIR / "batch_export.py"
    config_path = MATCHAMAP_DIR / config
    if not script.exists():
        return jsonify({"ok": False, "error": "batch_export.py not found", "stdout": "", "stderr": ""}), 500
    if not config_path.exists():
        return jsonify({"ok": False, "error": f"Config not found: {config}", "stdout": "", "stderr": ""}), 400
    try:
        r = subprocess.run(
            [os.environ.get("python3", "python3"), str(script), str(config_path)],
            cwd=str(MATCHAMAP_DIR),
            capture_output=True,
            text=True,
            timeout=300,
        )
        return jsonify({
            "ok": r.returncode == 0,
            "stdout": r.stdout or "",
            "stderr": r.stderr or "",
            "returncode": r.returncode,
        })
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Timed out after 300s", "stdout": "", "stderr": ""}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "stdout": "", "stderr": ""}), 500


if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "5050"))
    app.run(host=host, port=port, debug=False, threaded=True)
