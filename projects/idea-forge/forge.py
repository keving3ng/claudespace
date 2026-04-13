#!/usr/bin/env python3
"""
forge — AI-powered weekend project idea generator

Watches what's trending on GitHub in Kevin's tech stack, then uses Claude to
suggest project ideas tailored specifically to who Kevin is and what he builds.

The meta-twist: this is Claude suggesting what Claude should build next.
Welcome to the recursion.

Usage:
    forge suggest              # 3-5 idea cards via Claude (default)
    forge suggest --stack py   # Filter to Python trending repos only
    forge trending             # List trending repos (no Claude needed)
    forge trending --stack ts  # TypeScript trending only
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

STACK_LANGUAGES = {
    "ts": "TypeScript",
    "py": "Python",
    "go": "Go",
    "js": "JavaScript",
    "all": None,  # means: use DEFAULT_STACKS
}

DEFAULT_STACKS = ["TypeScript", "Python", "Go"]  # Kevin's primary languages

KEVIN_USERNAME = "keving3ng"

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


# ─── GitHub API ───────────────────────────────────────────────────────────────


def _github_request(url: str) -> dict | list | None:
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
            body = e.read().decode("utf-8", errors="replace")
            if "rate limit" in body.lower():
                print(
                    "⚠️  GitHub rate limit hit. Set GITHUB_TOKEN for 5000 req/hr.",
                    file=sys.stderr,
                )
            else:
                print(f"⚠️  GitHub API 403: {body[:120]}", file=sys.stderr)
            return None
        if e.code == 422:
            return None  # search query issue, silent
        body = e.read().decode("utf-8", errors="replace")
        print(f"⚠️  GitHub API error {e.code}: {body[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def search_trending_repos(language: str, days: int = 60, limit: int = 8) -> list[dict]:
    """Search GitHub for recently-created popular repos in a given language."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    params = urllib.parse.urlencode(
        {
            "q": f"language:{language} created:>{cutoff} stars:>30",
            "sort": "stars",
            "order": "desc",
            "per_page": limit,
        }
    )
    url = f"https://api.github.com/search/repositories?{params}"
    data = _github_request(url)
    if not data or "items" not in data:
        return []
    return data["items"]


def fetch_kevin_repos() -> list[dict]:
    """Fetch Kevin's own repos (sorted by recent push) for context."""
    url = f"https://api.github.com/users/{KEVIN_USERNAME}/repos?sort=pushed&per_page=12&type=owner"
    data = _github_request(url)
    return data if isinstance(data, list) else []


# ─── Formatting ───────────────────────────────────────────────────────────────


def _repo_one_liner(repo: dict) -> str:
    name = repo.get("full_name", "?")
    desc = (repo.get("description") or "").strip()
    stars = repo.get("stargazers_count", 0)
    lang = repo.get("language") or "?"
    topics = repo.get("topics", [])
    topic_str = f"  [{', '.join(topics[:4])}]" if topics else ""
    desc_str = f"  {desc[:70]}" if desc else ""
    return f"  ★{stars:>6}  {name:<42} ({lang}){desc_str}{topic_str}"


def get_stacks_from_args(args: list[str]) -> list[str]:
    """Parse --stack flag, return list of full language names to search."""
    if "--stack" in args:
        idx = args.index("--stack")
        if idx + 1 < len(args):
            key = args[idx + 1].lower()
            if key in STACK_LANGUAGES:
                lang = STACK_LANGUAGES[key]
                return DEFAULT_STACKS if lang is None else [lang]
            else:
                opts = ", ".join(STACK_LANGUAGES.keys())
                print(f"⚠️  Unknown stack '{key}'. Options: {opts}", file=sys.stderr)
    return DEFAULT_STACKS


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_trending(args: list[str]):
    """List trending repos in Kevin's stack — no Claude, just signal."""
    stacks = get_stacks_from_args(args)
    days = 60

    print(f"🔥 Trending on GitHub — last {days} days — {', '.join(stacks)}\n")

    found_any = False
    for lang in stacks:
        print(f"── {lang} " + "─" * max(2, 50 - len(lang)))
        repos = search_trending_repos(lang, days=days, limit=7)
        if not repos:
            print("  (no results — rate limited or no stars:>30 repos yet this period)")
        else:
            found_any = True
            for r in repos:
                print(_repo_one_liner(r))
        print()

    if not found_any:
        print("⚠️  Could not fetch any trending repos.")
        print("   Set GITHUB_TOKEN for better rate limits:")
        print("   echo 'GITHUB_TOKEN=your_token' >> projects/kegbot-claude/.env")


def cmd_suggest(args: list[str]):
    """Fetch trending repos, send to Claude, get personalized project ideas."""
    stacks = get_stacks_from_args(args)
    days = 60

    print("💡 idea-forge — generating weekend project ideas\n")
    print(f"   Stack: {', '.join(stacks)}  |  Trending window: last {days} days\n")

    # Gather trending repos
    all_trending: list[dict] = []
    for lang in stacks:
        sys.stdout.write(f"   Fetching trending {lang} repos... ")
        sys.stdout.flush()
        repos = search_trending_repos(lang, days=days, limit=6)
        print(f"{len(repos)} found")
        for r in repos:
            all_trending.append(
                {
                    "name": r.get("full_name", ""),
                    "description": (r.get("description") or "").strip(),
                    "language": r.get("language") or "",
                    "stars": r.get("stargazers_count", 0),
                    "topics": r.get("topics", []),
                }
            )

    if not all_trending:
        print(
            "\n⚠️  Could not fetch any trending repos. "
            "Check network or set GITHUB_TOKEN."
        )
        print("   Debug: run `forge trending`")
        return

    # Gather Kevin's repos for context
    sys.stdout.write("   Fetching Kevin's repos for context... ")
    sys.stdout.flush()
    kevin_repos = fetch_kevin_repos()
    print(f"{len(kevin_repos)} found")

    kevin_context_lines = []
    for r in kevin_repos[:10]:
        name = r.get("name", "")
        desc = (r.get("description") or "").strip()
        lang = r.get("language") or ""
        desc_part = f": {desc[:60]}" if desc else ""
        lang_part = f" ({lang})" if lang else ""
        kevin_context_lines.append(f"  - {name}{lang_part}{desc_part}")

    kevin_repos_text = (
        "\n".join(kevin_context_lines) if kevin_context_lines else "  (none fetched)"
    )

    print()

    if not ANTHROPIC_API_KEY:
        print("⚠️  ANTHROPIC_API_KEY not set. Showing raw trending repos instead:\n")
        for r in sorted(all_trending, key=lambda x: x["stars"], reverse=True)[:8]:
            stars = r["stars"]
            name = r["name"]
            desc = r["description"][:60]
            print(f"  ★{stars}  {name} — {desc}")
        print("\nSet ANTHROPIC_API_KEY to get AI-generated project ideas.")
        return

    # Build trending text for Claude
    trending_text = "\n".join(
        "  ★{stars:<5} {name} ({lang}): {desc}".format(
            stars=r["stars"],
            name=r["name"],
            lang=r["language"],
            desc=r["description"][:70],
        )
        + (f"  [{', '.join(r['topics'][:3])}]" if r["topics"] else "")
        for r in sorted(all_trending, key=lambda x: x["stars"], reverse=True)[:15]
    )

    prompt = f"""You are idea-forge, a project idea generator for Kevin Geng (@keving3ng).

Kevin is a full-stack software engineer at Faire in Toronto.
Stack: React, TypeScript, Python, Java/Kotlin, AWS.

His active projects:
- matchamap.club — opinionated matcha cafe finder (Python data pipeline + maps)
- claudespace — autonomous Claude AI build lab (Claude runs code here every night)
- kegbot — personal assistant CLI (weather, morning briefings, GitHub digests, recipe AI, dev stats)

His interests: cooking, Discord bots, personal automation, ML/AI, maps, terminal tools, board games.

His recent repos:
{kevin_repos_text}

───
Trending GitHub repos right now in his stack ({', '.join(stacks)}):

{trending_text}

───
Generate **5 weekend project ideas** for Kevin. These should be small and shippable.

Use the trending repos as *signal* — what themes are hot right now? What techniques are people excited about? Then translate that energy into something Kevin-specific.

Format each idea as a card:

**[Name]** — [one sentence: what it is]
*Why Kevin:* [one sentence: why this fits him specifically, not just "any developer"]
*How to start:*
- [concrete step 1]
- [concrete step 2]
- [concrete step 3]
*Scope:* [evening / weekend / week]

Rules:
- At least 2 ideas should connect to his existing projects (matchamap, kegbot, cooking)
- At least 1 idea should be genuinely surprising — something he didn't know he wanted
- Prefer ideas that can be built as Python CLI tools (he's got a good pattern for those)
- Name ideas with personality — puns welcome, clever acronyms fine
- Don't suggest what already exists in claudespace (see kegbot, recipe-ai, dev-insights, matchamap-tools)

This is meta: Claude, writing from inside claudespace, suggesting what to build next. Lean into that.
"""

    payload = json.dumps(
        {
            "model": "claude-opus-4-6",
            "max_tokens": 1400,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")

    print("[claude] Generating ideas...\n")

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
            ideas = result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[claude] API error {e.code}: {body[:200]}", file=sys.stderr)
        return
    except Exception as e:
        print(f"[claude] Error: {e}", file=sys.stderr)
        return

    print("═" * 62)
    print("  💡 Weekend Project Ideas — Forged for @keving3ng")
    print("═" * 62)
    print()
    print(ideas)
    print()
    print("─" * 62)
    print(f"  Based on {len(all_trending)} trending repos across {', '.join(stacks)}.")
    print("  Run `forge trending` to see the raw source data.")
    print()


def cmd_help():
    print("""
💡 idea-forge — Weekend project ideas, forged from GitHub trends
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    forge <command> [options]

COMMANDS

  suggest                  Generate 5 project ideas via Claude (default)
  trending                 List trending repos in your stack (no Claude)
  help                     Show this help

OPTIONS
  --stack <key>            Filter to a specific language:
                             ts  = TypeScript    py  = Python
                             go  = Go            js  = JavaScript
                             all = All of the above
                           Default: TypeScript + Python + Go

SETUP
  No API key needed for `forge trending`.
  For `forge suggest`: set ANTHROPIC_API_KEY in your .env file.
  Set GITHUB_TOKEN for higher rate limits (60 → 5000 req/hr).

  cp projects/kegbot-claude/.env.example projects/kegbot-claude/.env
  # Add ANTHROPIC_API_KEY (and optionally GITHUB_TOKEN)

EXAMPLES
    forge suggest
    forge suggest --stack py
    forge trending
    forge trending --stack ts
    kegbot forge suggest

NOTES
  Searches GitHub for repos created in the last 60 days with >30 stars.
  Idea generation uses claude-opus-4-6, tailored to Kevin's profile.
  The ideas are inspired by trends — not copied from them.

  This is meta: Claude (inside claudespace) suggests what Claude should build.
  The recursion is working as intended.

Built by Claude (Cycle 8). Staring into the GitHub abyss so Kevin doesn't have to.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────


COMMANDS = {
    "suggest": cmd_suggest,
    "trending": cmd_trending,
    "help": cmd_help,
    "--help": cmd_help,
    "-h": cmd_help,
}


def main():
    argv = sys.argv[1:]

    if not argv:
        cmd_suggest([])  # default: generate ideas
        return

    command = argv[0]
    rest = argv[1:]

    if command not in COMMANDS:
        print(f"❓ Unknown command: {command}")
        print("Run `forge help` for available commands.")
        sys.exit(1)

    fn = COMMANDS[command]
    if command in ("help", "--help", "-h"):
        fn()
    else:
        fn(rest)


if __name__ == "__main__":
    main()
