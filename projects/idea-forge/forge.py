#!/usr/bin/env python3
"""
forge — AI-powered project idea generator

Watches trending GitHub repos in Kevin's stack and suggests personalized
weekend project ideas. The recursive one: Claude suggesting what to build next.

Usage:
    forge suggest                  # Generate 5 fresh project ideas
    forge suggest --no-github      # Ideas without fetching trending repos
    forge history                  # Show past idea sessions
    forge history --all            # Show all sessions
    forge save <id>                # Bookmark an idea from the last session
    forge help
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

FORGE_DIR = Path(__file__).parent
REPO_ROOT = FORGE_DIR.parent.parent
IDEAS_FILE = FORGE_DIR / "ideas.json"

# Kevin's profile — baked into every prompt so ideas feel personal
KEVIN_PROFILE = """
Kevin Geng — @keving3ng — Full-stack software engineer at Faire in Toronto.
Stack: React, TypeScript, Java/Kotlin/Spring Boot, Python, AWS.
Active projects this year:
  - matchamap.club: opinionated matcha cafe finder (map + curation)
  - claudespace: autonomous Claude AI build lab (this is where I live)
  - kegbot: personal assistant CLI (briefings, weather, PR digest, tasks)
  - recipe-ai: ingredient-based recipe suggestions + pantry + meal plans
  - dev-insights: terminal GitHub heatmap + streak tracker
Past interests: ML/face recognition (TensorFlow/Keras), Discord bots,
personal finance data aggregation, transit status notifications,
board games, teaching/workshops.
Personality: builder, pragmatic, "fun + useful" > enterprise-boring.
Likes surprises. Opens his laptop hoping to find something unexpected.
""".strip()

# ─── Config ───────────────────────────────────────────────────────────────────

GITHUB_USERNAME = "keving3ng"
TRENDING_LANGUAGES = ["TypeScript", "Python"]

# ─── Env ──────────────────────────────────────────────────────────────────────


def load_env():
    for env_path in [
        FORGE_DIR / ".env",
        REPO_ROOT / ".env",
        REPO_ROOT / "projects" / "kegbot-claude" / ".env",
    ]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


# ─── GitHub API ───────────────────────────────────────────────────────────────


def _gh_request(url: str) -> dict | list | None:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "idea-forge/1.0",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  [github] HTTP {e.code}: {body[:120]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [github] Error: {e}", file=sys.stderr)
        return None


def fetch_trending_repos(language: str, days_back: int = 60, limit: int = 8) -> list[dict]:
    """
    Fetch recently-popular repos for a language using GitHub search.
    Filters for repos created in the last N*3 days with ≥200 stars.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back * 3)).strftime("%Y-%m-%d")
    q = urllib.parse.quote(f"language:{language} stars:>200 created:>{cutoff}")
    url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page={limit}"
    result = _gh_request(url)
    if not result or not isinstance(result, dict) or "items" not in result:
        return []
    return result["items"]


def fetch_user_repos(username: str) -> list[dict]:
    """Fetch Kevin's repos, sorted by most recently pushed."""
    url = f"https://api.github.com/users/{username}/repos?sort=pushed&per_page=30&type=owner"
    result = _gh_request(url)
    return result if isinstance(result, list) else []


# ─── Claude API ───────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 1500) -> str:
    if not ANTHROPIC_API_KEY:
        return "⚠️  ANTHROPIC_API_KEY not set."

    payload = json.dumps({
        "model": "claude-opus-4-6",
        "max_tokens": max_tokens,
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
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"[Claude API error {e.code}: {body[:200]}]"
    except Exception as e:
        return f"[Claude API error: {e}]"


# ─── Idea history ─────────────────────────────────────────────────────────────


def load_ideas() -> list[dict]:
    if not IDEAS_FILE.exists():
        return []
    try:
        return json.loads(IDEAS_FILE.read_text())
    except Exception:
        return []


def save_ideas_db(ideas: list[dict]):
    IDEAS_FILE.write_text(json.dumps(ideas, indent=2))


# ─── Formatting helpers ───────────────────────────────────────────────────────


def _trending_summary(repos: list[dict]) -> str:
    lines = []
    for r in repos:
        name = r.get("full_name", r.get("name", "?"))
        desc = (r.get("description") or "no description")[:80]
        stars = r.get("stargazers_count", 0)
        lang = r.get("language") or "?"
        lines.append(f"  - {name} ({lang}, ⭐{stars:,}) — {desc}")
    return "\n".join(lines) if lines else "  (none found)"


def _kevin_repos_summary(repos: list[dict]) -> str:
    lines = []
    for r in repos[:15]:
        name = r.get("name", "?")
        desc = (r.get("description") or "").strip()[:60]
        lang = r.get("language") or "?"
        private_tag = " [private]" if r.get("private") else ""
        desc_part = f": {desc}" if desc else ""
        lines.append(f"  - {name}{private_tag} ({lang}){desc_part}")
    return "\n".join(lines) if lines else "  (none found)"


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_suggest(args: list[str]):
    """Generate personalized project ideas via Claude + GitHub trending data."""
    skip_github = "--no-github" in args

    print("💡 idea-forge — generating project ideas...\n")

    trending_text = ""
    kevin_repos_text = ""

    if not skip_github:
        print("  Fetching trending repos in TypeScript + Python...")
        trending_repos: list[dict] = []
        for lang in TRENDING_LANGUAGES:
            repos = fetch_trending_repos(lang, days_back=60, limit=7)
            trending_repos.extend(repos)
            print(f"    {lang}: {len(repos)} trending repo(s)")

        trending_text = _trending_summary(trending_repos)

        print("  Fetching your GitHub repos...")
        kevin_repos = fetch_user_repos(GITHUB_USERNAME)
        kevin_repos_text = _kevin_repos_summary(kevin_repos)
        print(f"    Found {len(kevin_repos)} repo(s)")
        print()
    else:
        print("  Skipping GitHub fetch (--no-github)\n")

    today = datetime.now().strftime("%A, %B %d, %Y")

    prompt = f"""You are Claude, with a deep understanding of Kevin Geng's builder personality. Today is {today}.

## Kevin's Profile
{KEVIN_PROFILE}

## What Kevin Has Already Built (his GitHub repos, most recent first)
{kevin_repos_text if kevin_repos_text else "  (not fetched)"}

## What's Hot Right Now (GitHub trending — TypeScript + Python)
{trending_text if trending_text else "  (not fetched)"}

---

Generate exactly **5 personalized weekend project ideas** for Kevin.

Constraints:
- Each achievable in 1-2 weekends of focused work
- Fit his stack (TypeScript/React, Python — or Go if interesting)
- At least 2 ideas extend his *existing* projects (matchamap, kegbot, recipe-ai, dev-insights, claudespace)
- At least 1 is inspired by what's trending (but reshaped for Kevin's personality)
- At least 1 is pure fun — a game, toy, weird experiment, or whimsical hack
- Don't suggest anything he's already clearly built

Format each idea EXACTLY like this (keep the ---s):

---
**Idea N: [Project Name]**
*One punchy line that makes Kevin want to open his editor right now.*

Stack: [specific tools/languages]
Effort: [S = 1 day / M = weekend / L = 2 weekends]
Why Kevin: [one sentence on why this fits HIM specifically]

Build it:
- [specific step 1 — concrete, not vague]
- [specific step 2]
- [specific step 3]
---

Be bold. Be specific. "A CLI that..." is not enough — name the exact feature.
The best idea is one Kevin didn't know he wanted until he read it.
"""

    if not ANTHROPIC_API_KEY:
        print("⚠️  ANTHROPIC_API_KEY not set.")
        print("   Add it to projects/kegbot-claude/.env or repo root .env")
        return

    print("[claude] Thinking about what Kevin should build next...\n")
    ideas_text = claude_call(prompt, max_tokens=1800)

    print("═" * 65)
    print(ideas_text)
    print("═" * 65 + "\n")

    # Persist this session
    session = {
        "date": datetime.now(timezone.utc).isoformat(),
        "text": ideas_text,
        "langs": TRENDING_LANGUAGES,
        "saved": [],
    }
    ideas = load_ideas()
    ideas.append(session)
    if len(ideas) > 15:
        ideas = ideas[-15:]
    save_ideas_db(ideas)

    n = len(ideas)
    print(f"💾 Session {n} saved to {IDEAS_FILE.name}")
    print("   Use `forge save <1-5>` to bookmark a specific idea.")
    print("   Use `forge history` to revisit past sessions.\n")


def cmd_history(args: list[str]):
    """Show past idea generation sessions."""
    ideas = load_ideas()
    if not ideas:
        print("No idea history yet. Run `forge suggest` to generate some.\n")
        return

    show_all = "--all" in args
    n = len(ideas)
    print(f"📚 idea-forge history — {n} session(s)\n")

    for i, session in enumerate(ideas):
        idx = i + 1
        date_str = session.get("date", "?")[:10]
        saved = session.get("saved", [])
        saved_str = f"  ★ saved: {', '.join(str(s) for s in saved)}" if saved else ""
        marker = "→ " if idx == n else "  "
        print(f"{marker}Session {idx} — {date_str}{saved_str}")

    print()

    # Always show the latest session's output
    print("── Most recent ideas ──────────────────────────────────────")
    print(ideas[-1].get("text", "(no text)"))
    print("───────────────────────────────────────────────────────────\n")

    if not show_all and n > 1:
        print(f"  Tip: `forge history --all` to see all {n} sessions (not yet implemented — coming soon)")


def cmd_save(args: list[str]):
    """Bookmark a specific idea (1-5) from the most recent session."""
    ideas = load_ideas()
    if not ideas:
        print("No ideas yet. Run `forge suggest` first.")
        return

    if not args:
        print("Usage: forge save <1-5>")
        print("Example: forge save 3")
        return

    try:
        idea_num = int(args[0])
    except ValueError:
        print(f"❌ Expected a number, got: {args[0]}")
        return

    if idea_num < 1 or idea_num > 5:
        print(f"❌ Idea number must be between 1 and 5 (got {idea_num})")
        return

    latest = ideas[-1]
    saved = latest.get("saved", [])
    if idea_num not in saved:
        saved.append(idea_num)
        latest["saved"] = sorted(saved)
        save_ideas_db(ideas)
        print(f"★  Idea {idea_num} bookmarked. Run `forge history` to see your saved ideas.")
    else:
        print(f"  Idea {idea_num} is already saved.")


def cmd_help():
    print("""
💡 idea-forge — AI-powered project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    forge <command> [options]

COMMANDS

  suggest                    Generate 5 personalized weekend project ideas
    --no-github                Skip GitHub trending fetch (faster, offline)

  history                    Show past idea sessions (most recent in full)
    --all                      (coming soon)

  save <N>                   Bookmark idea N from the most recent session

  help                       Show this help

SETUP
    Requires ANTHROPIC_API_KEY in projects/kegbot-claude/.env (or root .env).
    Optionally add GITHUB_TOKEN for higher GitHub rate limits.

EXAMPLES
    forge suggest
    forge suggest --no-github
    forge history
    forge save 2

HOW IT WORKS
    1. Fetches trending repos in TypeScript + Python from GitHub Search API
    2. Fetches your existing repos (so Claude knows what gaps to fill)
    3. Asks Claude to generate 5 ideas tailored to your stack + personality
    4. Ideas lean toward: extending existing projects, fun experiments,
       things inspired by what's hot but shaped for Kevin's actual taste
    5. Sessions saved to ideas.json — bookmark the good ones

Built by Claude (Cycle 8). The meta one: an AI suggesting what the AI should
build next. The recursion is intentional and delightful.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "suggest": cmd_suggest,
    "history": cmd_history,
    "save": cmd_save,
    "help": lambda _: cmd_help(),
    "--help": lambda _: cmd_help(),
    "-h": lambda _: cmd_help(),
}


def main():
    argv = sys.argv[1:]

    if not argv:
        cmd_suggest([])
        return

    command = argv[0]
    rest = argv[1:]

    if command not in COMMANDS:
        print(f"❓ Unknown command: {command}")
        print("Run `forge help` for available commands.")
        sys.exit(1)

    COMMANDS[command](rest)


if __name__ == "__main__":
    main()
