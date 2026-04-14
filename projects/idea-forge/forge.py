#!/usr/bin/env python3
"""
idea-forge — AI weekend project idea generator

Scans trending GitHub repos in your languages, cross-references your existing
work, and asks Claude to suggest 4 project ideas you'd actually want to build.

Zero deps beyond stdlib. Requires ANTHROPIC_API_KEY for AI generation.

Usage:
    forge                       # generate project ideas (default)
    forge ideas [--save]        # generate + optionally save ideas
    forge trending              # show trending repos, no AI
    forge saved                 # show previously saved ideas
    forge help
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent
HERE = Path(__file__).parent
IDEAS_FILE = HERE / "ideas.json"

KEVIN_USERNAME = "keving3ng"
LANGUAGES = ["python", "typescript", "java"]

KEVIN_CONTEXT = """
Kevin Geng — full-stack software engineer at Faire (Toronto).
Stack: React, TypeScript, Java/Spring Boot, Python, AWS.
Active side projects: matchamap.club (matcha cafe map), kegbot (personal assistant CLI),
recipe-ai (ingredient → recipe suggestions), dev-insights (terminal GitHub heatmap).
Interests: cooking, ML/AI, Discord bots, personal automation, maps/geodata, gaming.
Vibe: pragmatic builder who likes tools that solve real personal problems with personality.
He is not intimidated by APIs, has experience with ML/CV, and appreciates good UX even in CLIs.
"""

ANTHROPIC_MODEL = "claude-opus-4-6"

# ─── Env ──────────────────────────────────────────────────────────────────────


def load_env():
    for env_path in [
        HERE / ".env",
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


def _github_get(url: str) -> dict | list | None:
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
        if e.code == 403:
            print(
                "⚠️  GitHub rate limit hit. Add GITHUB_TOKEN to .env for 5000 req/hr.",
                file=sys.stderr,
            )
        elif e.code != 422:
            body = e.read().decode("utf-8", errors="replace")
            print(f"⚠️  GitHub API {e.code}: {body[:150]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def fetch_trending(language: str, days_ago: int = 7, per_page: int = 8) -> list[dict]:
    """Fetch recently-created repos trending by stars in a given language."""
    since = (date.today() - timedelta(days=days_ago)).isoformat()
    query = f"language:{language}+created:>{since}"
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={query}&sort=stars&order=desc&per_page={per_page}"
    )
    result = _github_get(url)
    if not isinstance(result, dict):
        return []
    return [
        {
            "name": r["full_name"],
            "stars": r["stargazers_count"],
            "description": (r.get("description") or "").strip(),
            "language": r.get("language") or language,
            "topics": r.get("topics", []),
        }
        for r in result.get("items", [])
    ]


def fetch_kevin_repos() -> list[dict]:
    """Fetch Kevin's non-fork public repos sorted by most recently pushed."""
    result = _github_get(
        f"https://api.github.com/users/{KEVIN_USERNAME}/repos?per_page=50&sort=pushed"
    )
    if not isinstance(result, list):
        return []
    return [
        {
            "name": r["name"],
            "description": (r.get("description") or "").strip(),
            "language": r.get("language") or "?",
            "pushed_at": (r.get("pushed_at") or "")[:10],
        }
        for r in result
        if not r.get("fork")
    ]


# ─── Claude API ───────────────────────────────────────────────────────────────


def call_claude(prompt: str, max_tokens: int = 2000) -> str | None:
    if not ANTHROPIC_API_KEY:
        return None

    payload = json.dumps(
        {
            "model": ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"⚠️  Claude API {e.code}: {body[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Claude API error: {e}", file=sys.stderr)
        return None


# ─── Idea persistence ─────────────────────────────────────────────────────────


def load_ideas() -> list[dict]:
    if IDEAS_FILE.exists():
        try:
            return json.loads(IDEAS_FILE.read_text())
        except Exception:
            return []
    return []


def save_ideas_to_file(entry: dict):
    existing = load_ideas()
    existing.append(entry)
    IDEAS_FILE.write_text(json.dumps(existing, indent=2, default=str))


# ─── Commands ─────────────────────────────────────────────────────────────────

LANG_LABELS = {
    "python": "Python 🐍",
    "typescript": "TypeScript 🟦",
    "java": "Java ☕",
}


def cmd_trending(args: list[str]):
    """Show trending repos across Kevin's stack — no AI, just the raw signal."""
    days = 7
    print(f"🔭 Trending GitHub repos — last {days} days\n")

    for lang in LANGUAGES:
        repos = fetch_trending(lang, days_ago=days, per_page=6)
        label = LANG_LABELS.get(lang, lang)
        print(f"  ── {label} ─────────────────────────────────────────")
        if not repos:
            print("  (no results or rate limited)\n")
            continue
        for r in repos:
            stars = r["stars"]
            desc = r["description"][:65] if r["description"] else "(no description)"
            print(f"  ⭐ {stars:>5}  {r['name']}")
            print(f"           {desc}")
        print()


def cmd_ideas(args: list[str]):
    """Generate AI project ideas based on trending repos + Kevin's profile."""
    do_save = "--save" in args
    days = 7

    print("🔭 Scanning what's trending...")
    trending: dict[str, list[dict]] = {}
    for lang in LANGUAGES:
        repos = fetch_trending(lang, days_ago=days, per_page=8)
        trending[lang] = repos
        print(f"   {LANG_LABELS.get(lang, lang)}: {len(repos)} repos found")

    print("👤 Loading Kevin's repo context...")
    kevin_repos = fetch_kevin_repos()

    if not ANTHROPIC_API_KEY:
        print("\n⚠️  ANTHROPIC_API_KEY not set — showing raw trending data instead.")
        print("   Add it to .env to unlock AI-powered idea generation.\n")
        cmd_trending(args)
        return

    # Build prompt inputs
    trending_lines = []
    for lang, repos in trending.items():
        for r in repos:
            if r["description"]:
                trending_lines.append(f"  [{lang}] {r['name']} (⭐{r['stars']}): {r['description']}")

    kevin_repo_lines = []
    for r in sorted(kevin_repos, key=lambda x: x["pushed_at"], reverse=True)[:12]:
        desc = r["description"] or "no description"
        kevin_repo_lines.append(f"  {r['name']} ({r['language']}): {desc}")

    prompt = f"""You are a creative technical advisor helping a developer decide what to build next.

About the developer:
{KEVIN_CONTEXT.strip()}

Kevin's recent repos (most recently pushed first):
{chr(10).join(kevin_repo_lines) if kevin_repo_lines else "  (unavailable)"}

Trending on GitHub this week:
{chr(10).join(trending_lines[:28]) if trending_lines else "  (unavailable)"}

Generate exactly 4 weekend project ideas for Kevin. Requirements:
- Buildable solo in 1-2 focused days
- Fits his stack (TypeScript/React, Python, Java/Spring) or is a fun stretch
- Feels genuinely personal to Kevin, not generic filler
- Can draw *inspiration* from trending repos but must NOT be a clone
- At least one idea should be a genuine surprise — something Kevin wouldn't have thought of himself

Format each idea exactly like this:

## [Creative project name with personality]
**What it is:** 1-2 sentences. Be specific, not vague.
**Why Kevin:** A concrete reason based on his actual history and interests.
**The interesting part:** What's technically fun or surprising about building it.
**Weekend scope:** Exactly what you'd ship in 2 days (be concrete: commands, screens, outputs).
**Stack:** Suggested tech.

No preamble. Start directly with the first ## heading.
"""

    print("🤖 Asking Claude for ideas...\n")
    response = call_claude(prompt, max_tokens=2200)

    if not response:
        print("⚠️  No response from Claude. Check ANTHROPIC_API_KEY in .env.")
        return

    today = date.today().isoformat()
    print("═" * 62)
    print(f"  idea-forge — {today}")
    print("═" * 62)
    print()
    print(response)
    print()
    print("═" * 62)

    if do_save:
        entry = {
            "date": today,
            "ideas_text": response,
            "languages_scanned": LANGUAGES,
            "trending_count": {lang: len(repos) for lang, repos in trending.items()},
        }
        save_ideas_to_file(entry)
        print(f"\n💾 Saved to {IDEAS_FILE.name}")
    else:
        print("\n  Tip: run `forge ideas --save` to keep these for later")

    print()


def cmd_saved(args: list[str]):
    """Display previously saved idea sessions."""
    ideas = load_ideas()
    if not ideas:
        print("\n📭 No saved ideas yet. Run `forge ideas --save` to generate some.\n")
        return

    print(f"\n💡 Saved idea sessions ({len(ideas)} total)\n")
    for i, entry in enumerate(reversed(ideas), 1):
        session_num = len(ideas) - i + 1
        print("─" * 62)
        print(f"Session {session_num} — {entry.get('date', '?')}")
        print("─" * 62)
        print(entry.get("ideas_text", "(no text)"))
        print()


def cmd_help():
    print("""
💡 idea-forge — Weekend project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    forge [command]

COMMANDS
  ideas [--save]    AI-generated project ideas from trending repos (default)
  trending          Show trending GitHub repos, no AI
  saved             Previously saved idea sessions
  help              This help text

HOW IT WORKS
  1. Fetches trending repos in Python, TypeScript, Java (GitHub search API)
  2. Gets your public repos for context
  3. Asks Claude to suggest 4 weekend projects tailored to your stack + interests
  4. Ideas are concrete, scoped, and (hopefully) genuinely exciting

SETUP
  Add ANTHROPIC_API_KEY to your .env for AI generation.
  Optionally add GITHUB_TOKEN for higher GitHub rate limits (60 → 5000/hr).

  .env lives at any of:
    projects/idea-forge/.env
    projects/kegbot-claude/.env
    .env  (repo root)

EXAMPLES
    forge                       # generate ideas
    forge ideas --save          # generate and save to ideas.json
    forge trending              # just show trending, no Claude
    forge saved                 # review past sessions

Built by Claude (Cycle 8). Because "what should I build this weekend?" is a
question that deserves a better answer than staring at a blank terminal.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "ideas": cmd_ideas,
    "trending": cmd_trending,
    "saved": cmd_saved,
    "help": lambda _: cmd_help(),
    "--help": lambda _: cmd_help(),
    "-h": lambda _: cmd_help(),
}


def main():
    argv = sys.argv[1:]

    if not argv or (argv[0] not in COMMANDS):
        if argv and argv[0] not in COMMANDS:
            print(f"❓ Unknown command: {argv[0]}")
            print("Run `forge help` for available commands.")
            sys.exit(1)
        cmd_ideas(argv)
        return

    command = argv[0]
    rest = argv[1:]
    COMMANDS[command](rest)


if __name__ == "__main__":
    main()
