#!/usr/bin/env python3
"""
forge — Weekend project idea generator tailored to Kevin

Analyzes trending GitHub repos in your tech stack and suggests personalized
weekend project ideas via Claude. Zero config required for trending; Claude
API key unlocks the ideas and plan commands.

Usage:
    forge trending                # Trending repos (Python + TypeScript by default)
    forge trending --lang python  # One language only
    forge trending --lang ts      # TypeScript alias
    forge trending --lang go      # Go
    forge trending --days 14      # Wider look-back window (default: 7)
    forge ideas                   # Claude-generated project ideas from trending
    forge ideas --lang python     # Focus on Python ecosystem
    forge ideas --days 14         # Wider trending window for more signal
    forge plan "<idea>"           # Rough implementation plan for a specific idea
    forge help
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent
DEFAULT_LANGS = ["python", "typescript"]

LANG_DISPLAY = {
    "python": "Python",
    "typescript": "TypeScript",
    "go": "Go",
    "rust": "Rust",
    "javascript": "JavaScript",
    "kotlin": "Kotlin",
}

LANG_ALIASES = {
    "ts": "typescript",
    "js": "javascript",
    "py": "python",
}

KEVIN_PROFILE = """Kevin Geng — full-stack software engineer at Faire (Toronto).
Stack: React, TypeScript, Python, Java/Kotlin/Spring Boot, AWS.
Active projects: matchamap.club (opinionated matcha cafe map), kegbot (personal
    assistant CLI), claudespace (autonomous Claude build lab).
Dormant but meaningful: face-recog (ML/CV), transact (personal finance data),
    discordbot (Discord integrations), cookbook (recipe collection).
Interests: personal automation, Discord bots, maps and place data, cooking tools,
    practical AI/ML, personal finance aggregation, terminal tools, web apps.
Style: pragmatic builder. Values daily-useful over impressive-demo. Likes stdlib
    solutions, clean CLIs, and tools that make him smile when he opens his laptop."""

# ─── Env ──────────────────────────────────────────────────────────────────────


def load_env():
    for env_path in [
        Path(__file__).parent / ".env",
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


# ─── GitHub Search API ────────────────────────────────────────────────────────


def _gh_request(url: str) -> dict | None:
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
        # 422 = search query issue (often just means no results in range)
        if e.code not in (422, 404):
            print(f"[github] HTTP {e.code}: {body[:120]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[github] Error: {e}", file=sys.stderr)
        return None


def search_trending_repos(lang: str, days: int = 7, per_page: int = 8) -> list[dict]:
    """
    Search for repos created in the last N days, sorted by stars.
    This is a good approximation of "trending" — what just got exciting.
    """
    since = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    q = urllib.parse.quote(f"language:{lang} created:>{since}")
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={q}&sort=stars&order=desc&per_page={per_page}"
    )

    data = _gh_request(url)
    if not data or "items" not in data:
        return []

    return [
        {
            "name": r["full_name"],
            "url": r["html_url"],
            "stars": r["stargazers_count"],
            "description": (r.get("description") or "")[:120],
            "topics": r.get("topics", [])[:5],
            "lang": LANG_DISPLAY.get(lang, lang),
            "created": r["created_at"][:10],
        }
        for r in data["items"]
    ]


# ─── Claude API ───────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 1000) -> str:
    if not ANTHROPIC_API_KEY:
        return "⚠️  ANTHROPIC_API_KEY not set — can't generate ideas without Claude.\nSet it in .env or: export ANTHROPIC_API_KEY=your_key_here"

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
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"[Claude API error {e.code}: {body[:200]}]"
    except Exception as e:
        return f"[Claude API error: {e}]"


# ─── Arg parsing helpers ──────────────────────────────────────────────────────


def parse_langs(args: list[str]) -> list[str]:
    if "--lang" in args:
        idx = args.index("--lang")
        if idx + 1 < len(args):
            lang = args[idx + 1].lower()
            lang = LANG_ALIASES.get(lang, lang)
            return [lang]
    return DEFAULT_LANGS


def parse_days(args: list[str], default: int = 7) -> int:
    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                return int(args[idx + 1])
            except ValueError:
                pass
    return default


# ─── Formatting ───────────────────────────────────────────────────────────────


def _format_repo_block(r: dict) -> str:
    topics = ", ".join(r["topics"]) if r["topics"] else ""
    lines = [
        f"  ★ {r['stars']:>5}  [{r['lang']}]  {r['name']}  (created {r['created']})",
        f"           {r['description'] or '(no description)'}",
    ]
    if topics:
        lines.append(f"           topics: {topics}")
    lines.append(f"           {r['url']}")
    return "\n".join(lines)


def _repos_as_context(repos: list[dict], max_repos: int = 12) -> str:
    if not repos:
        return "(no trending repos fetched)"
    lines = []
    for r in repos[:max_repos]:
        topics_str = ", ".join(r["topics"]) if r["topics"] else "none"
        lines.append(
            f"- [{r['lang']}] {r['name']} (★{r['stars']}, created {r['created']})\n"
            f"  {r['description'] or 'no description'}\n"
            f"  topics: {topics_str}"
        )
    return "\n\n".join(lines)


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_trending(args: list[str]):
    langs = parse_langs(args)
    days = parse_days(args)

    print(f"🔥 forge trending — last {days} days\n")

    all_repos: list[dict] = []
    for lang in langs:
        display = LANG_DISPLAY.get(lang, lang)
        print(f"  Searching {display}...", end="", flush=True)
        repos = search_trending_repos(lang, days=days)
        print(f" {len(repos)} found")
        all_repos.extend(repos)

    if not all_repos:
        print(
            "\n⚠️  No trending repos found.\n"
            "   Try --days 14, or --days 30 for a wider window.\n"
            "   GitHub search rate limit: 10 req/min without auth, 30 with GITHUB_TOKEN."
        )
        return

    # Sort all by stars, descending
    all_repos.sort(key=lambda r: r["stars"], reverse=True)

    print(f"\n{'─' * 68}")
    print(f"  Trending GitHub repos — last {days} days\n")
    for r in all_repos:
        print(_format_repo_block(r))
        print()
    print(f"{'─' * 68}")
    print(f"\n  {len(all_repos)} repos  ·  Run `forge ideas` to generate project ideas from these")
    print()


def cmd_ideas(args: list[str]):
    langs = parse_langs(args)
    days = parse_days(args, default=14)

    print(f"💡 forge ideas — generating weekend project ideas for Kevin\n")

    all_repos: list[dict] = []
    for lang in langs:
        display = LANG_DISPLAY.get(lang, lang)
        print(f"  Fetching trending {display}...", end="", flush=True)
        repos = search_trending_repos(lang, days=days, per_page=6)
        print(f" {len(repos)} found")
        all_repos.extend(repos)

    all_repos.sort(key=lambda r: r["stars"], reverse=True)
    repo_context = _repos_as_context(all_repos)

    prompt = f"""You are an AI project idea generator. Your task is to suggest weekend project ideas tailored specifically to this developer:

{KEVIN_PROFILE}

Here are the currently trending GitHub repos in his tech stack (repos created in the last ~{days} days, sorted by stars):

{repo_context}

Based on the trending ecosystem AND Kevin's specific interests, suggest exactly 5 weekend project ideas.

For each idea, use this format:

**[Project Name]** — one sentence hook (the thing that makes you go "oh that would be fun")
- *Why Kevin*: one sentence on why this fits him specifically (not generic "developers will love")
- *Stack*: what he'd actually use (TypeScript/React, Python, etc.)
- *The build*:
  - Step 1 (concrete)
  - Step 2 (concrete)
  - Step 3 (concrete)
- *Inspired by*: [repo name] or "Kevin's profile"

Rules:
- Feel personal and specific to Kevin — not generic dev tools
- At least one idea should connect to his existing projects (matchamap, kegbot, cookbook)
- At least one idea must involve Claude/AI in an interesting way
- At least one idea should be "small enough to ship in a Sunday afternoon"
- Tone: excited but practical. These are real ideas, not wish lists.
- Do not add preamble or summary. Start with idea 1.
"""

    print(f"\n[claude] Thinking about what Kevin should build next...\n")
    ideas = claude_call(prompt, max_tokens=1400)

    print("─" * 68)
    print(ideas)
    print("─" * 68)
    print()
    print("  Run `forge plan \"<project name>\"` to get a rough implementation plan for any of these.")
    print()


def cmd_plan(args: list[str]):
    # Idea is everything that isn't a flag
    idea_parts = [a for a in args if not a.startswith("-")]
    idea = " ".join(idea_parts).strip().strip('"').strip("'")

    if not idea:
        print("❓  Usage: forge plan \"<idea title or description>\"")
        print("    Example: forge plan \"matcha cafe quality ranker\"")
        sys.exit(1)

    print(f"🗺  forge plan — implementation plan for: {idea}\n")

    prompt = f"""You are a senior software engineer planning a weekend project for Kevin Geng.

{KEVIN_PROFILE}

Project to plan: **{idea}**

Write a concrete, practical implementation plan. This is a reference card for a real build, not a spec doc.

Format exactly as follows:

**Overview**: 1-2 sentences — what it is and the core value

**Tech stack**: Specific, from Kevin's world

**Implementation (5 steps)**:
1. ...
2. ...
3. ...
4. ...
5. ...

**File tree** (rough sketch, 5-8 files max):
```
project-name/
├── ...
```

**The delight factor**: The one thing that makes this worth building over a weekend

**Gotchas**: 2 things that will surprise you mid-build

**Time estimate**: Honest — "Sunday afternoon", "full weekend", or "two weekends"

Keep it tight. Under 350 words. No fluff. This is the kind of plan you actually build from.
"""

    plan = claude_call(prompt, max_tokens=800)

    print("─" * 68)
    print(plan)
    print("─" * 68)
    print()


def cmd_help():
    print(
        """
💡 forge — Weekend project idea generator tailored to Kevin
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    forge <command> [options]

COMMANDS

  trending                   Trending GitHub repos in Kevin's stack
    --lang LANG                Filter: python, typescript (ts), go, rust, js
    --days N                   Look-back window in days (default: 7)

  ideas                      Claude-generated project ideas from trending
    --lang LANG                Focus on one language ecosystem
    --days N                   Trending window (default: 14)

  plan "<idea>"              Rough implementation plan for a specific idea

  help                       This help text

EXAMPLES
    forge trending
    forge trending --lang go --days 14
    forge ideas
    forge ideas --lang python
    forge plan "Discord bot that summarizes my GitHub week"
    forge plan "matcha cafe quality ranker with a CLI"

SETUP
    No config required for `trending`. Searches GitHub public API (60 req/hr).
    GITHUB_TOKEN in .env raises limit to 5000 req/hr.
    ANTHROPIC_API_KEY in .env enables `ideas` and `plan` commands.

HOW TRENDING WORKS
    "Trending" here = repos created in the last N days, sorted by stars.
    Not identical to github.com/trending (which uses daily view velocity),
    but a solid signal for what the ecosystem just got excited about.

NOTES
    idea-forge is itself a project suggested by a previous cycle of forge.
    There's something recursive about that. Built by Claude, for Claude.

Built by Claude (Cycle 8). Meta: an AI suggesting what an AI should build.
"""
    )


# ─── Main ─────────────────────────────────────────────────────────────────────


COMMANDS = {
    "trending": cmd_trending,
    "ideas": cmd_ideas,
    "plan": cmd_plan,
    "help": lambda _: cmd_help(),
    "--help": lambda _: cmd_help(),
    "-h": lambda _: cmd_help(),
}


def main():
    argv = sys.argv[1:]

    if not argv:
        cmd_help()
        return

    command = argv[0]
    rest = argv[1:]

    if command not in COMMANDS:
        print(f"❓  Unknown command: {command!r}")
        print("    Run `forge help` to see available commands.")
        sys.exit(1)

    COMMANDS[command](rest)


if __name__ == "__main__":
    main()
