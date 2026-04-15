#!/usr/bin/env python3
"""
idea-forge — AI project idea generator tailored to Kevin's stack

Watches trending GitHub repos in Python, TypeScript, and Go, then uses
Claude to synthesize weekend project ideas that would actually suit Kevin:
full-stack, pragmatic, fun, and implementable in 1-3 sessions.

Zero new dependencies. Needs ANTHROPIC_API_KEY for `suggest`. `trending`
works without a key.

Usage:
    idea-forge trending                   # show raw trending repos (no Claude)
    idea-forge trending --lang py         # filter: py, ts, go, java
    idea-forge suggest                    # Claude-generated project ideas
    idea-forge suggest --lang ts          # ideas focused on one stack
    idea-forge suggest --count 3          # how many ideas (default: 5)
    idea-forge help
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

KEVIN_CONTEXT = """
Kevin Geng is a full-stack software engineer (React, TypeScript, Python, Java/Spring Boot).
He is building matchamap.club — a curated matcha cafe map app.
He likes: cooking, Discord bots, personal automation, maps/place data, AI tools, terminal CLIs.
He runs a personal assistant called kegbot. He has a cookbook repo.
He's into pragmatic tools that are delightful and immediately useful — not overengineered.
Weekend project sweet spot: something shippable in 1-3 focused sessions.
"""

LANG_MAP = {
    "py": "Python",
    "python": "Python",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "go": "Go",
    "java": "Java",
    "js": "JavaScript",
    "javascript": "JavaScript",
}

DEFAULT_LANGS = ["Python", "TypeScript", "Go"]
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-opus-4-6"

# ─── Env loading ──────────────────────────────────────────────────────────────


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
        if e.code == 422:
            return None  # bad query, skip gracefully
        body = e.read().decode("utf-8", errors="replace")
        print(f"⚠️  GitHub API error {e.code}: {body[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def fetch_trending(language: str, days: int = 30, per_page: int = 8) -> list[dict]:
    """
    Fetch recently-created repos with significant stars for a given language.
    Returns a list of repo metadata dicts.
    """
    since = (date.today() - timedelta(days=days)).isoformat()
    lang_encoded = urllib.request.quote(language)
    url = (
        f"https://api.github.com/search/repositories"
        f"?q=language:{lang_encoded}+created:>{since}+stars:>20"
        f"&sort=stars&order=desc&per_page={per_page}"
    )
    result = _github_request(url)
    if not result or "items" not in result:
        return []
    return result["items"]


# ─── Claude API ───────────────────────────────────────────────────────────────


def call_claude(prompt: str) -> str:
    if not ANTHROPIC_API_KEY:
        return "[No ANTHROPIC_API_KEY set — run `export ANTHROPIC_API_KEY=...`]"

    payload = {
        "model": MODEL,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=data,
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
        return f"[Claude API error {e.code}: {body[:300]}]"
    except Exception as e:
        return f"[Request failed: {e}]"


# ─── Formatting ───────────────────────────────────────────────────────────────


def format_repo(repo: dict, index: int) -> str:
    name = repo.get("full_name", "unknown/unknown")
    desc = repo.get("description") or "(no description)"
    stars = repo.get("stargazers_count", 0)
    lang = repo.get("language") or "?"
    url = repo.get("html_url", "")
    topics = ", ".join(repo.get("topics", [])[:4]) or "—"
    return (
        f"  {index}. {name}  [{lang}]  ★{stars:,}\n"
        f"     {desc[:90]}\n"
        f"     Topics: {topics}\n"
        f"     {url}"
    )


def build_trending_summary(repos_by_lang: dict[str, list[dict]]) -> str:
    """Format trending repos into a compact text block for the Claude prompt."""
    lines = []
    for lang, repos in repos_by_lang.items():
        if not repos:
            continue
        lines.append(f"\n### Trending {lang} repos (last 30 days):")
        for r in repos[:6]:
            name = r.get("full_name", "")
            desc = (r.get("description") or "")[:80]
            stars = r.get("stargazers_count", 0)
            topics = ", ".join(r.get("topics", [])[:3])
            lines.append(f"  - {name} ★{stars}  {desc}  [{topics}]")
    return "\n".join(lines)


# ─── Commands ─────────────────────────────────────────────────────────────────


def parse_lang(args: list[str]) -> list[str]:
    for flag in ("--lang", "-l"):
        if flag in args:
            idx = args.index(flag)
            if idx + 1 < len(args):
                raw = args[idx + 1].lower()
                mapped = LANG_MAP.get(raw)
                return [mapped] if mapped else DEFAULT_LANGS
    return DEFAULT_LANGS


def parse_count(args: list[str], default: int = 5) -> int:
    for flag in ("--count", "-n"):
        if flag in args:
            idx = args.index(flag)
            if idx + 1 < len(args):
                try:
                    return max(1, min(10, int(args[idx + 1])))
                except ValueError:
                    pass
    return default


def cmd_trending(args: list[str]):
    langs = parse_lang(args)

    print(f"🔍 Fetching trending repos for: {', '.join(langs)}...\n")

    for lang in langs:
        repos = fetch_trending(lang)
        if not repos:
            print(f"  [{lang}] No trending repos found (rate limit or no results)")
            continue

        print(f"┌─ Trending {lang} (last 30 days) {'─' * (40 - len(lang))}")
        for i, repo in enumerate(repos, start=1):
            print(format_repo(repo, i))
            print()
        print()


def cmd_suggest(args: list[str]):
    langs = parse_lang(args)
    count = parse_count(args)

    if not ANTHROPIC_API_KEY:
        print("⚠️  ANTHROPIC_API_KEY not set. Set it in .env or environment.")
        print("   Showing raw trending repos instead:\n")
        cmd_trending(args)
        return

    print(f"🔍 Fetching trending repos for: {', '.join(langs)}...")
    repos_by_lang: dict[str, list[dict]] = {}
    for lang in langs:
        repos = fetch_trending(lang)
        repos_by_lang[lang] = repos

    total = sum(len(v) for v in repos_by_lang.values())
    print(f"   Found {total} trending repos across {len(langs)} language(s)")
    print(f"🤖 Asking Claude for {count} project ideas...\n")

    trending_block = build_trending_summary(repos_by_lang)

    prompt = f"""You are a creative technical advisor for a developer called Kevin.

## Kevin's profile:
{KEVIN_CONTEXT.strip()}

## Currently trending GitHub repos in Kevin's stack:
{trending_block}

## Your task:
Look at the trending repos above and identify interesting patterns, emerging tools, or gaps.
Then suggest exactly {count} weekend project ideas that Kevin would genuinely enjoy building.

For each idea:
1. **Name + one-line pitch** — catchy, specific, no buzzwords
2. **Inspired by** — which trending repo(s) sparked this idea (just the name, no URL)
3. **Why Kevin** — one sentence on why this fits his interests specifically
4. **Stack** — what he'd use (be specific: Python CLI? React + Next.js? etc.)
5. **Weekend scope** — "1 weekend", "2 weekends", or "3 weekends"
6. **First step** — the single most concrete thing to do to get started

Format as a numbered list. Be direct and opinionated. Skip generic ideas — Kevin doesn't need
another todo-app or weather widget. Aim for "I can't believe nobody built this yet" energy.

If the trending repos don't spark anything interesting, invent ideas that fit the general
spirit of what's trending (the themes, not the specific repos).
"""

    result = call_claude(prompt)

    print("✨ idea-forge — Project Ideas for Kevin\n")
    print("═" * 60)
    print(result)
    print("═" * 60)
    print(f"\n  Generated by Claude ({MODEL}) from {total} trending repos")
    print(f"  Run `idea-forge trending` to see the raw repo data\n")


def cmd_help():
    print("""
✨ idea-forge — AI project idea generator tailored to Kevin's stack
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    idea-forge <command> [options]

COMMANDS

  trending                   Show raw trending GitHub repos
  suggest                    Claude-generated project ideas (needs API key)
  help                       Show this help

OPTIONS
  --lang <lang>              Language filter: py, ts, go, java
  -l <lang>                  Shorthand for --lang
  --count <N>                Number of ideas to generate (default: 5, max: 10)
  -n <N>                     Shorthand for --count

SETUP
  1. Set ANTHROPIC_API_KEY in your .env file (or kegbot-claude/.env)
  2. Optionally set GITHUB_TOKEN for higher GitHub rate limits
  3. Run `idea-forge suggest` and be delighted

EXAMPLES
    idea-forge trending
    idea-forge trending --lang ts
    idea-forge suggest
    idea-forge suggest --lang py --count 3
    idea-forge suggest --lang go -n 5

NOTES
  `trending` works without any API key (60 GitHub req/hr unauthenticated)
  `suggest` requires ANTHROPIC_API_KEY — falls back to trending if missing
  Trending = repos created in the last 30 days with 20+ stars

Built by Claude (Cycle 8). Because the best projects start with "I wonder what's trending."
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "trending": cmd_trending,
    "suggest": cmd_suggest,
    "help": lambda _: cmd_help(),
    "--help": lambda _: cmd_help(),
    "-h": lambda _: cmd_help(),
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
        print("Run `idea-forge help` for available commands.")
        sys.exit(1)

    COMMANDS[command](rest)


if __name__ == "__main__":
    main()
