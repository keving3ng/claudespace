#!/usr/bin/env python3
"""
idea-forge — Weekend project idea generator tailored to Kevin's profile

Uses GitHub's trending repos as inspiration, then asks Claude to suggest
projects that fit Kevin's skills and interests. Saves history so you can
track what you've considered (and ignored).

Usage:
    forge                               # suggest ideas (default)
    forge suggest                       # generate ideas from trending repos
    forge suggest --lang python         # focus on Python ecosystem
    forge suggest --topic "discord bots" # ideas around a specific topic
    forge trending                      # show trending repos (no Claude)
    forge trending --lang typescript    # trending TypeScript repos
    forge spark <topic>                 # quick brainstorm on any topic
    forge history                       # show past suggestions
    forge history --limit 5             # last 5 saved sessions
    forge help
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent
FORGE_DIR = Path(__file__).parent
HISTORY_FILE = FORGE_DIR / "forge_history.json"

KEVIN_PROFILE = """Kevin Geng — full-stack software engineer at Faire (Toronto).
Tech stack: Python, TypeScript/React, Java/Kotlin/Spring Boot.
Active side projects:
  - matchamap.club — opinionated map for high-quality matcha cafes
  - kegbot — personal assistant CLI (Claude-powered daily briefings)
  - recipe-ai — cooking tools (ingredient suggestions, meal planning)
  - claudespace — autonomous Claude AI build lab (this repo)
Interests: personal automation, Discord bots, ML/AI experiments, maps/place
  data, board games, cooking, teaching tools, small elegant utilities.
Vibe: pragmatic builder, prefers 'fun + useful' over enterprise abstractions.
  Loves tools that earn daily use. Allergic to over-engineering."""

KEVIN_LANGS = ["python", "typescript", "javascript", "go", "java"]
DEFAULT_LANGS = ["python", "typescript"]

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


# ─── GitHub Search ────────────────────────────────────────────────────────────


def _github_request(url: str) -> dict | None:
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
                "⚠️  GitHub rate limit hit. Set GITHUB_TOKEN for higher limits.",
                file=sys.stderr,
            )
        elif e.code != 404:
            body = e.read().decode("utf-8", errors="replace")
            print(f"⚠️  GitHub API {e.code}: {body[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def fetch_trending_repos(lang: str, days: int = 30, per_page: int = 10) -> list[dict]:
    """
    Fetch repos created in the last `days` days for a language, sorted by stars.
    Approximates GitHub Trending (which has no official API).
    """
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    query = f"language:{lang} created:>{cutoff}"
    encoded_query = urllib.parse.quote(query)
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={encoded_query}&sort=stars&order=desc&per_page={per_page}"
    )
    data = _github_request(url)
    if not data or "items" not in data:
        return []

    return [
        {
            "name": r.get("full_name", ""),
            "description": (r.get("description") or "")[:120],
            "stars": r.get("stargazers_count", 0),
            "url": r.get("html_url", ""),
            "topics": r.get("topics", [])[:6],
            "language": r.get("language") or lang,
        }
        for r in data["items"]
    ]


# ─── Claude ───────────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 1500) -> str:
    """Thin Anthropic API wrapper."""
    if not ANTHROPIC_API_KEY:
        return (
            "⚠️  ANTHROPIC_API_KEY not set.\n"
            "Add it to projects/kegbot-claude/.env or repo root .env\n"
            "Run with trending/history commands which don't need Claude."
        )

    payload = json.dumps(
        {
            "model": "claude-opus-4-6",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")

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


# ─── History ──────────────────────────────────────────────────────────────────


def load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text())
    except Exception:
        return []


def save_to_history(entry: dict):
    history = load_history()
    history.append(entry)
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_trending(args: list[str]):
    """Show trending repos for a language — no Claude needed."""
    lang = _get_flag(args, "--lang") or "python"
    days = 30

    print(f"🔥 Trending {lang.title()} repos — created in the last {days} days\n")

    repos = fetch_trending_repos(lang, days=days, per_page=12)
    if not repos:
        print("⚠️  Couldn't fetch trending repos. Check network or GITHUB_TOKEN.")
        return

    for i, r in enumerate(repos, 1):
        stars = f"⭐ {r['stars']:,}"
        topics_str = ""
        if r["topics"]:
            topics_str = "  [" + ", ".join(r["topics"][:4]) + "]"
        print(f"  {i:>2}. {r['name']}")
        print(f"       {stars}   {r['description'][:75]}")
        if topics_str:
            print(f"       {topics_str}")
        print(f"       {r['url']}")
        print()


def cmd_suggest(args: list[str]):
    """Fetch trending repos and ask Claude for personalized project ideas."""
    langs = _get_langs(args, DEFAULT_LANGS)
    topic_override = _get_flag(args, "--topic")
    days = 30

    print("💡 idea-forge — generating weekend project ideas\n")

    # Fetch trending repos
    all_repos: list[dict] = []
    for lang in langs:
        print(f"   Fetching trending {lang.title()} repos (last {days}d)...")
        repos = fetch_trending_repos(lang, days=days, per_page=8)
        all_repos.extend(repos)

    # Deduplicate + sort by stars
    seen: set[str] = set()
    unique_repos: list[dict] = []
    for r in all_repos:
        if r["name"] not in seen:
            seen.add(r["name"])
            unique_repos.append(r)
    unique_repos.sort(key=lambda r: r["stars"], reverse=True)
    top_repos = unique_repos[:16]

    if top_repos:
        print(f"   Found {len(top_repos)} trending repos. Asking Claude...\n")
    else:
        print("   No trending repo data — using Claude's baseline knowledge.\n")

    # Build the repo block for the prompt
    repo_lines = ""
    for r in top_repos:
        repo_lines += f"- **{r['name']}** ({r['stars']:,}★, {r['language']}): {r['description']}"
        if r["topics"]:
            repo_lines += f"  [topics: {', '.join(r['topics'][:4])}]"
        repo_lines += "\n"

    topic_line = f"\nAdditional focus area: {topic_override}\n" if topic_override else ""
    today = date.today().isoformat()

    prompt = f"""You are idea-forge, a pragmatic weekend project advisor for Kevin Geng.

Kevin's profile:
{KEVIN_PROFILE}

Today is {today}. Here's what's trending on GitHub right now in his tech stack:
{repo_lines if repo_lines else "(no trending data — use your knowledge of the current ecosystem)"}
{topic_line}
Generate exactly **3 weekend project ideas** for Kevin.

Rules:
- Each idea must be achievable in a weekend (1-2 days of solo coding)
- Draw *inspiration* from what's trending — remix, don't clone
- Make it personally Kevin's: connect to his interests, stack, or existing projects where natural
- Be opinionated and concrete. If an approach is mediocre, skip it.

Format each idea exactly like this:

**[Name]** — one punchy name

**Pitch:** One sentence. What is it?

**Why Kevin:** One sentence on why this fits him (his stack, existing projects, or interests).

**Plan:**
- Step 1
- Step 2
- Step 3
- Step 4 (add a 5th only if genuinely necessary)

**Twist:** One unexpected feature or design choice that makes it interesting.

**Complexity:** Easy (1 day) / Medium (weekend) / Stretch (3-4 days)

---

Keep each idea under 200 words. Separate ideas with `---`. No preamble, no conclusion."""

    print("[claude] Generating ideas...\n")
    result = claude_call(prompt, max_tokens=1800)

    print("─" * 65)
    print(result)
    print("─" * 65)
    print()

    # Save to history
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "suggest",
        "langs": langs,
        "topic": topic_override,
        "trending_sample": [r["name"] for r in top_repos[:5]],
        "ideas": result,
    }
    save_to_history(entry)
    print("✅ Saved to forge_history.json")
    print()


def cmd_spark(args: list[str]):
    """Quick brainstorm on a specific topic — no trending data needed."""
    # Strip any flags
    topic_parts = [a for a in args if not a.startswith("--")]
    topic = " ".join(topic_parts).strip()

    if not topic:
        print("Usage: forge spark <topic>")
        print("Example: forge spark 'transit notifications'")
        return

    print(f"✨ idea-forge spark — brainstorming: '{topic}'\n")

    prompt = f"""You are idea-forge, Kevin's weekend project advisor.

Kevin's profile:
{KEVIN_PROFILE}

Topic: {topic}

Generate **2 quick project ideas** for Kevin around this topic.
Keep each idea under 120 words. Be specific and opinionated — weekend scope only, no enterprise architecture.

Format each idea exactly like:

**[Name]** — one sentence pitch

**Plan:**
- Step 1
- Step 2
- Step 3

**Kevin angle:** Why it fits him (one sentence).

**Complexity:** Easy (1 day) / Medium (weekend) / Stretch (3-4 days)

Separate the two ideas with `---`."""

    result = claude_call(prompt, max_tokens=900)

    print("─" * 65)
    print(result)
    print("─" * 65)
    print()

    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "spark",
        "topic": topic,
        "ideas": result,
    }
    save_to_history(entry)
    print("✅ Saved to forge_history.json")


def cmd_history(args: list[str]):
    """Show past idea generation sessions."""
    limit = 5
    if "--limit" in args:
        idx = args.index("--limit")
        if idx + 1 < len(args):
            try:
                limit = int(args[idx + 1])
            except ValueError:
                pass

    history = load_history()
    if not history:
        print("No history yet. Run `forge suggest` to generate some ideas.")
        return

    recent = history[-limit:]
    print(f"📚 idea-forge history — {len(recent)} of {len(history)} session(s)\n")

    for entry in reversed(recent):
        ts = entry.get("timestamp", "")[:16].replace("T", " ")
        etype = entry.get("type", "unknown")

        if etype == "spark":
            header = f"✨  spark — '{entry.get('topic', '?')}'  [{ts}]"
        else:
            langs = ", ".join(entry.get("langs", []))
            topic = entry.get("topic")
            topic_str = f"  +topic: {topic}" if topic else ""
            sample = entry.get("trending_sample", [])
            sample_str = f"  (inspired by: {', '.join(sample[:3])})" if sample else ""
            header = f"💡  suggest — [{langs}]{topic_str}{sample_str}  [{ts}]"

        print("─" * 65)
        print(header)
        print()
        ideas = entry.get("ideas", "")
        if len(ideas) > 700:
            print(ideas[:700] + "\n... [truncated — full text in forge_history.json]")
        else:
            print(ideas)
        print()


def cmd_help():
    print("""
💡 idea-forge — Weekend project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Analyzes what's trending on GitHub in your stack, then asks Claude to
generate personalized weekend project ideas that fit your skills and taste.

USAGE
    forge <command> [options]

COMMANDS

  suggest                    Generate ideas from trending repos (default)
    --lang LANG                Focus on a language: python, typescript, go
    --topic TOPIC              Also apply a topic focus area

  trending                   Show trending repos (no Claude needed)
    --lang LANG                Language to check (default: python)

  spark <topic>              Quick brainstorm on any topic
                             Example: forge spark 'transit notifications'

  history                    Show past idea sessions
    --limit N                  Show last N sessions (default: 5)

  help                       This help text

SETUP
    Needs ANTHROPIC_API_KEY for suggest/spark commands.
    Optional GITHUB_TOKEN for better trending data (60→5000 req/hr).
    Add either to: projects/kegbot-claude/.env  or  repo root .env

EXAMPLES
    forge
    forge suggest
    forge suggest --lang typescript
    forge suggest --topic 'personal finance tools'
    forge trending --lang go
    forge spark 'recipe recommendation with ML'
    forge spark 'transit status bot'
    forge history
    forge history --limit 3

ALSO AVAILABLE VIA
    kegbot ideas               delegates to forge suggest
    kegbot ideas spark <topic>
    kegbot ideas trending

Built by Claude (Cycle 8). Because the best project is the one you
haven't thought of yet — but will ship this weekend.
""")


# ─── Arg helpers ──────────────────────────────────────────────────────────────


def _get_flag(args: list[str], flag: str) -> str | None:
    if flag in args:
        idx = args.index(flag)
        if idx + 1 < len(args):
            return args[idx + 1]
    return None


def _get_langs(args: list[str], default: list[str]) -> list[str]:
    lang = _get_flag(args, "--lang")
    if lang:
        return [lang.lower()]
    return default


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "suggest": cmd_suggest,
    "trending": cmd_trending,
    "spark": cmd_spark,
    "history": cmd_history,
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

    if command == "spark":
        cmd_spark(rest)
        return

    if command not in COMMANDS:
        print(f"❓ Unknown command: {command}")
        print("Run `forge help` for available commands.")
        sys.exit(1)

    COMMANDS[command](rest)


if __name__ == "__main__":
    main()
