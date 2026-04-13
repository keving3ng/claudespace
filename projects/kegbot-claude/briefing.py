#!/usr/bin/env python3
"""
kegbot-claude/briefing.py — Daily briefing generator powered by Claude.

Fetches recent GitHub activity and generates a personalized morning briefing
via the Claude API. Zero runtime dependencies beyond stdlib.

Usage:
    python briefing.py                   # Print to terminal
    python briefing.py --discord         # Print + post to Discord
    python briefing.py --days 3          # Look back 3 days of GitHub history
    python briefing.py --no-github       # Skip GitHub, vibes-only mode
    python briefing.py --username alice  # Different GitHub username
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent
DISCORD_POST = REPO_ROOT / "projects" / "discord-bridge" / "post.py"


def load_env():
    """Load .env files without requiring python-dotenv."""
    for env_path in [Path(__file__).parent / ".env", REPO_ROOT / ".env"]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "keving3ng")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ─── GitHub ────────────────────────────────────────────────────────────────────


def fetch_github_events(username: str, days: int = 2) -> list[dict]:
    """Fetch recent public GitHub events for a user (no auth required)."""
    url = f"https://api.github.com/users/{username}/events/public?per_page=50"
    headers = {
        "User-Agent": "kegbot-claude/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            events = json.loads(resp.read())
    except Exception as e:
        print(f"[github] Could not fetch events: {e}", file=sys.stderr)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return [
        ev for ev in events
        if datetime.fromisoformat(ev["created_at"].replace("Z", "+00:00")) >= cutoff
    ]


def repo_activity_summary(events: list[dict]) -> str:
    """
    Derive a per-repo commit count from already-fetched events.
    Returns a compact multi-line string suitable for embedding in a prompt.
    """
    from collections import Counter
    repo_commits: Counter = Counter()
    for ev in events:
        if ev.get("type") == "PushEvent":
            repo = ev.get("repo", {}).get("name", "unknown")
            num = len(ev.get("payload", {}).get("commits", []))
            repo_commits[repo] += max(num, 1)

    if not repo_commits:
        return ""

    lines = []
    for repo, count in repo_commits.most_common():
        plural = "commits" if count != 1 else "commit"
        lines.append(f"  {repo}: {count} {plural}")
    return "\n".join(lines)


def summarize_events(events: list[dict]) -> str:
    """Turn raw GitHub events into a readable bullet list."""
    if not events:
        return "No recent GitHub activity found."

    lines = []
    seen_shas = set()

    for ev in events:
        etype = ev.get("type", "")
        repo = ev.get("repo", {}).get("name", "unknown")

        if etype == "PushEvent":
            for c in ev.get("payload", {}).get("commits", []):
                sha = c.get("sha", "")[:7]
                if sha and sha not in seen_shas:
                    seen_shas.add(sha)
                    msg = c.get("message", "").split("\n")[0][:80]
                    lines.append(f"- Pushed to {repo}: `{msg}` ({sha})")

        elif etype == "PullRequestEvent":
            action = ev.get("payload", {}).get("action", "")
            title = ev.get("payload", {}).get("pull_request", {}).get("title", "")[:80]
            lines.append(f"- PR {action} in {repo}: `{title}`")

        elif etype == "CreateEvent":
            ref_type = ev.get("payload", {}).get("ref_type", "")
            ref = ev.get("payload", {}).get("ref", "")
            if ref_type and ref_type != "repository":
                lines.append(f"- Created {ref_type} `{ref}` in {repo}")

        elif etype == "IssuesEvent":
            action = ev.get("payload", {}).get("action", "")
            title = ev.get("payload", {}).get("issue", {}).get("title", "")[:60]
            lines.append(f"- Issue {action} in {repo}: `{title}`")

        elif etype == "WatchEvent":
            lines.append(f"- Starred {repo}")

    if not lines:
        return "Activity found but nothing notable to surface."

    return "\n".join(lines[:15])  # cap for context window sanity


# ─── Weather ──────────────────────────────────────────────────────────────────


def fetch_weather_summary(location: str = "Toronto") -> str:
    """Fetch a compact weather string from wttr.in (no API key needed)."""
    encoded = urllib.parse.quote(location)
    url = f"https://wttr.in/{encoded}?format=j1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "kegbot-claude/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        current = data["current_condition"][0]
        desc = current["weatherDesc"][0]["value"]
        temp_c = current["temp_C"]
        feels_c = current["FeelsLikeC"]
        wind_kmph = current["windspeedKmph"]
        return f"{desc}, {temp_c}°C (feels like {feels_c}°C), wind {wind_kmph} km/h"
    except Exception as e:
        print(f"[weather] Could not fetch: {e}", file=sys.stderr)
        return ""


# ─── Claude API ───────────────────────────────────────────────────────────────


def generate_briefing(github_summary: str, days: int, weather_summary: str = "", activity_summary: str = "") -> str:
    """Call Claude API to generate the morning briefing."""
    if not ANTHROPIC_API_KEY:
        return (
            "⚠️  ANTHROPIC_API_KEY not set — add it to .env to get the AI briefing.\n\n"
            f"**GitHub Activity (raw — last {days} days):**\n{github_summary}"
        )

    today = datetime.now().strftime("%A, %B %d, %Y")

    weather_section = (
        f"\nCurrent weather in Toronto: {weather_summary}\n" if weather_summary else ""
    )

    activity_section = (
        f"\nRepo breakdown (commits in window):\n{activity_summary}\n" if activity_summary else ""
    )

    prompt = f"""You are kegbot, Kevin Geng's personal assistant. Generate a warm, sharp morning briefing.

Kevin is:
- Full-stack software engineer at Faire in Toronto (React, TypeScript, Python, Java/Spring)
- Building matchamap.club — an opinionated matcha cafe finder
- Running an autonomous Claude AI build lab (claudespace) that writes code while he sleeps
- Into cooking, personal automation, Discord bots, and ML/AI
- Pragmatic, likes things that are both fun AND useful

Today is {today}.{weather_section}

His GitHub activity in the last {days} day(s):
{github_summary}{activity_section}

Write a morning briefing that:
1. Opens with a one-liner: funny OR motivating, never cheesy or corporate
2. In 2–3 sentences, reflects back what he's been building — show you noticed
3. Suggests ONE concrete small thing he could do today (specific, actionable, based on his activity)
4. Closes in 1 sentence — genuine, not a cheerleader
{("5. Weave in the weather naturally — one sentence, only if it's relevant or funny (e.g. bad weather = good day to stay in and code)" if weather_summary else "")}

Constraints: under 200 words total. Use markdown. Be real. If there's no GitHub activity, be honest about it and make it interesting anyway."""

    payload = json.dumps({
        "model": "claude-opus-4-6",
        "max_tokens": 400,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"[Claude API error {e.code}: {body[:200]}]\n\n**Raw activity:**\n{github_summary}"
    except Exception as e:
        return f"[Claude API error: {e}]\n\n**Raw activity:**\n{github_summary}"


# ─── Discord ──────────────────────────────────────────────────────────────────


def post_to_discord(content: str):
    """Post briefing to Discord via discord-bridge/post.py."""
    if not DISCORD_POST.exists():
        print(f"[discord] post.py not found at {DISCORD_POST}", file=sys.stderr)
        return

    import subprocess
    try:
        subprocess.run(
            [sys.executable, str(DISCORD_POST), content[:1900]],
            timeout=15,
            check=False,
        )
    except Exception as e:
        print(f"[discord] post failed: {e}", file=sys.stderr)


# ─── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="kegbot morning briefing via Claude")
    parser.add_argument("--discord", action="store_true", help="Also post to Discord")
    parser.add_argument("--days", type=int, default=2, help="Days of GitHub history (default: 2)")
    parser.add_argument("--no-github", dest="no_github", action="store_true", help="Skip GitHub fetch")
    parser.add_argument("--username", default=GITHUB_USERNAME, help="GitHub username")
    parser.add_argument("--weather", action="store_true", help="Include current weather in briefing")
    parser.add_argument("--location", default="Toronto", help="Weather location (default: Toronto)")
    parser.add_argument("--activity", action="store_true", help="Include per-repo activity breakdown in briefing")
    args = parser.parse_args()

    print("🍵 kegbot-claude — morning briefing\n")

    # 1. GitHub activity
    if args.no_github:
        github_summary = "GitHub activity skipped."
        event_count = 0
    else:
        print(f"[github] Fetching {args.username}'s activity (last {args.days} days)...")
        events = fetch_github_events(args.username, days=args.days)
        event_count = len(events)
        github_summary = summarize_events(events)
        print(f"[github] {event_count} event(s) found.")

    # 2. Weather (optional)
    weather_summary = ""
    if args.weather:
        print(f"[weather] Fetching for {args.location}...")
        weather_summary = fetch_weather_summary(args.location)
        if weather_summary:
            print(f"[weather] {weather_summary}")
    print()

    # 3. Optional per-repo activity breakdown (derived from already-fetched events)
    activity_summary = ""
    if args.activity and not args.no_github:
        activity_summary = repo_activity_summary(events if not args.no_github else [])

    # 4. Generate briefing
    print("[claude] Generating briefing...")
    briefing = generate_briefing(github_summary, days=args.days, weather_summary=weather_summary, activity_summary=activity_summary)

    # 5. Print
    print("\n" + "─" * 60)
    print(briefing)
    print("─" * 60 + "\n")

    # 6. Discord
    if args.discord:
        print("[discord] Posting...")
        post_to_discord(f"☀️ **Morning Briefing**\n\n{briefing}")
        print("[discord] Done.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
