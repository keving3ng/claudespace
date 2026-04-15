#!/usr/bin/env python3
"""
forge — AI-powered weekend project idea generator

Scans trending GitHub repos in your tech stack and uses Claude to generate
tailored project ideas. No dependencies beyond stdlib.

The thesis: the best weekend projects live at the intersection of what's
actually gaining traction on GitHub and what you specifically care about.
Not "build a todo app." Something real.

Usage:
    forge ideas                          # ideas for Kevin's default stack
    forge ideas --stack python           # Python-focused ideas
    forge ideas --stack typescript       # TypeScript/JS ideas
    forge ideas --stack go               # Go ideas
    forge ideas --count 3                # fewer ideas
    forge ideas --save                   # auto-save results to ideas.json
    forge trending                       # show trending repos (no Claude needed)
    forge trending --language go
    forge trending --days 7              # tighter window = hotter trends
    forge saved                          # list saved ideas
    forge save <text>                    # save a manual idea
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

FORGE_DIR = Path(__file__).parent
REPO_ROOT = FORGE_DIR.parent.parent
IDEAS_FILE = FORGE_DIR / "ideas.json"

# Kevin's stack, in order of familiarity
KEVIN_PROFILE = """Kevin Geng is a full-stack software engineer at Faire (Toronto).
Stack: TypeScript, React, Python, Java/Kotlin/Spring Boot, AWS.
Active side projects:
  - matchamap.club — opinionated matcha cafe map (already has data pipeline + CLI)
  - claudespace — autonomous Claude AI build lab (already has kegbot CLI, recipe-ai, dev-insights)
  - kgeng.dev — personal site
Interests: cooking/recipes, Discord bots, personal automation, maps + place data,
  ML/computer vision, Toronto transit, board games, teaching code.
Things he's already built here (don't suggest again):
  matcha cafe finder, kegbot morning briefing CLI, recipe suggestion tool,
  GitHub activity heatmap/streak tracker, Discord bot relay, dev dashboard."""

STACK_LANGUAGES = {
    "python": ["Python"],
    "typescript": ["TypeScript", "JavaScript"],
    "ts": ["TypeScript", "JavaScript"],
    "go": ["Go"],
    "rust": ["Rust"],
    "kotlin": ["Kotlin"],
    "default": ["TypeScript", "Python"],
}

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


# ─── GitHub Search API ────────────────────────────────────────────────────────


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
            body = e.read().decode("utf-8", errors="replace")
            if "rate limit" in body.lower():
                print(
                    "⚠️  GitHub rate limit hit. Set GITHUB_TOKEN in .env for 5000 req/hr.",
                    file=sys.stderr,
                )
            else:
                print(f"⚠️  GitHub 403: {body[:200]}", file=sys.stderr)
        elif e.code != 422:
            body = e.read().decode("utf-8", errors="replace")
            print(f"⚠️  GitHub API {e.code}: {body[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request error: {e}", file=sys.stderr)
        return None


def search_trending_repos(language: str = None, days: int = 30, count: int = 8) -> list[dict]:
    """
    Proxy for 'trending': repos created recently with high star velocity.
    Uses GitHub search API — no unofficial trending API needed.
    """
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    # Build query: recently created + some stars to filter noise
    q_parts = [f"created:>{cutoff}", "stars:>5"]
    if language:
        q_parts.append(f"language:{language}")

    # URL-encode carefully — GitHub search needs + between terms
    q = urllib.parse.quote(" ".join(q_parts), safe="")
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={q}&sort=stars&order=desc&per_page={count}"
    )

    data = _github_request(url)
    if not data or "items" not in data:
        return []

    return data["items"]


def format_repo_brief(repo: dict) -> str:
    """One-line repo summary for display and Claude context."""
    name = repo.get("full_name", "?")
    desc = (repo.get("description") or "no description").strip()
    stars = repo.get("stargazers_count", 0)
    language = repo.get("language") or "?"
    topics = repo.get("topics", [])
    topic_str = f"  [{', '.join(topics[:4])}]" if topics else ""

    # Truncate description
    desc = desc[:75] + ("…" if len(desc) > 75 else "")

    return f"  ★{stars:<5}  {name}  ({language})  {desc}{topic_str}"


# ─── Claude API ───────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 1000) -> str:
    if not ANTHROPIC_API_KEY:
        return (
            "⚠️  ANTHROPIC_API_KEY not set.\n"
            "   Add it to projects/kegbot-claude/.env or the repo root .env.\n"
            "   Then run `forge ideas` again."
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
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"[Claude API error {e.code}: {body[:200]}]"
    except Exception as e:
        return f"[Claude API error: {e}]"


# ─── Ideas storage ────────────────────────────────────────────────────────────


def load_ideas() -> list[dict]:
    if not IDEAS_FILE.exists():
        return []
    try:
        return json.loads(IDEAS_FILE.read_text())
    except Exception:
        return []


def persist_idea(text: str, source: str = "manual"):
    ideas = load_ideas()
    ideas.append(
        {
            "text": text,
            "source": source,
            "saved_at": date.today().isoformat(),
        }
    )
    IDEAS_FILE.write_text(json.dumps(ideas, indent=2))
    print(f"✅ Saved to {IDEAS_FILE.name} ({len(ideas)} idea(s) total)")


# ─── Helpers ──────────────────────────────────────────────────────────────────


def get_flag(args: list[str], flag: str, default: str = None) -> str | None:
    if flag in args:
        idx = args.index(flag)
        if idx + 1 < len(args):
            return args[idx + 1]
    return default


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_trending(args: list[str]):
    """Show trending repos across Kevin's stack. No Claude or API key needed."""
    language = get_flag(args, "--language")
    days = int(get_flag(args, "--days") or "30")

    if language:
        languages = [language]
        label = f"language:{language}"
    else:
        languages = ["TypeScript", "Python", "Go"]
        label = "TypeScript + Python + Go"

    print(f"🔭 Trending on GitHub — {label}, last {days} days\n")

    for lang in languages:
        if len(languages) > 1:
            print(f"── {lang} " + "─" * (50 - len(lang)))

        repos = search_trending_repos(language=lang, days=days, count=8)

        if not repos:
            print(f"  (no results — rate limited or no repos found)\n")
            continue

        for repo in repos:
            print(format_repo_brief(repo))

        print()

    if not GITHUB_TOKEN:
        print("  Tip: set GITHUB_TOKEN in .env to avoid rate limits (60 → 5000 req/hr)")


def cmd_ideas(args: list[str]):
    """Scan trending repos + ask Claude to generate tailored project ideas."""
    stack_key = (get_flag(args, "--stack") or "default").lower()
    days = int(get_flag(args, "--days") or "30")
    count = int(get_flag(args, "--count") or "5")
    do_save = "--save" in args

    languages = STACK_LANGUAGES.get(stack_key, STACK_LANGUAGES["default"])
    stack_label = stack_key if stack_key != "default" else "TypeScript + Python"

    print(f"💡 forge ideas — {stack_label} stack, last {days} days\n")
    print("🔭 Scanning trending repos on GitHub...")

    # Fetch trending repos for each language in the stack
    all_repos: list[dict] = []
    for lang in languages:
        repos = search_trending_repos(language=lang, days=days, count=10)
        all_repos.extend(repos)

    # Deduplicate + sort by stars
    seen: set[str] = set()
    unique_repos: list[dict] = []
    for r in all_repos:
        key = r.get("full_name", "")
        if key and key not in seen:
            seen.add(key)
            unique_repos.append(r)
    unique_repos.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)

    if not unique_repos:
        print(
            "\n⚠️  No trending repos found.\n"
            "   GitHub search might be rate-limited (60 req/hr unauthenticated).\n"
            "   Set GITHUB_TOKEN in .env for higher limits, or try again shortly."
        )
        return

    print(f"   Found {len(unique_repos)} trending repos. Asking Claude for ideas...\n")

    # Build trend brief
    trend_lines = [format_repo_brief(r) for r in unique_repos[:14]]
    trend_brief = "\n".join(trend_lines)

    prompt = f"""You are an AI project idea generator. Generate weekend project ideas for a specific developer.

Developer profile:
{KEVIN_PROFILE}

Currently trending GitHub repos in his tech stack ({stack_label}, last {days} days):
{trend_brief}

---

Generate exactly {count} weekend project ideas. Requirements:

1. Each idea must be INSPIRED BY the trends above but NOT a clone or copy.
   Draw the vibe, the problem domain, the technology angle — not the implementation.
2. Every idea must fit Kevin's actual interests and existing skills (see profile).
3. Each idea must be completable in one focused weekend (2–3 days of real work).
4. Give each idea a memorable, specific name — not "AI-Powered X Tool".
5. Include one "twist" that makes it Kevin-specific, weird, or surprising.
6. Think sideways: if everyone is building AI coding tools, Kevin should build
   an AI that helps him plan his next matcha trip. That kind of lateral thinking.

Format each idea EXACTLY like this:
**[Name]** — [one punchy sentence describing what it does]
Stack: [specific technologies, be concrete]
Twist: [what makes this surprising, personal, or specifically Kevin's version]
Build hook: [the single most compelling reason Kevin would actually use this daily]

After all {count} ideas, add one line:
> Wildcard: [one deliberately weird or ambitious idea that breaks the pattern]

No preamble. Start directly with idea #1."""

    result = claude_call(prompt, max_tokens=1400)

    print("─" * 62)
    print(result)
    print("─" * 62)
    print()

    if do_save:
        persist_idea(result, source=f"forge ideas --stack {stack_key} --days {days}")
        print()


def cmd_save(args: list[str]):
    """Save a manual idea to ideas.json."""
    if not args:
        print("Usage: forge save <idea text>")
        print('Example: forge save "A Discord bot that rates my matcha photos"')
        return
    text = " ".join(args)
    persist_idea(text, source="manual")


def cmd_saved(args: list[str]):
    """List saved ideas."""
    ideas = load_ideas()

    if not ideas:
        print(
            "No saved ideas yet.\n"
            "Run `forge ideas --save` to generate and save, or `forge save <text>` manually."
        )
        return

    print(f"💡 Saved Ideas — {len(ideas)} total\n")
    for i, idea in enumerate(reversed(ideas), 1):
        saved_at = idea.get("saved_at", "?")
        source = idea.get("source", "?")
        text = idea.get("text", "").strip()
        print(f"[{i}]  {saved_at}  (via: {source})")
        # Print truncated or full
        lines = text.splitlines()
        preview = "\n    ".join(lines[:8])
        print(f"    {preview}")
        if len(lines) > 8:
            print(f"    … ({len(lines) - 8} more lines)")
        print()


def cmd_help():
    print("""
💡 forge — AI-powered weekend project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    forge <command> [options]

COMMANDS

  ideas                      Generate ideas via Claude (requires ANTHROPIC_API_KEY)
    --stack python|typescript  Focus on a specific tech stack (default: both)
    --days N                   Trending window in days (default: 30)
    --count N                  Number of ideas to generate (default: 5)
    --save                     Auto-save the generated ideas to ideas.json

  trending                   Show trending repos (no Claude, no API key needed)
    --language python          Filter by language
    --days N                   Lookback window (default: 30, try 7 for hotter trends)

  saved                      List saved ideas from ideas.json
  save <text>                Save a manual idea

  help                       Show this help

SETUP
  No setup needed for `trending`.
  For `ideas`, add ANTHROPIC_API_KEY to projects/kegbot-claude/.env
  Optional: add GITHUB_TOKEN for higher GitHub rate limits (60 → 5000 req/hr)

EXAMPLES
    forge trending
    forge trending --language go --days 7
    forge ideas
    forge ideas --stack python
    forge ideas --stack typescript --count 3 --save
    forge saved

PHILOSOPHY
  Trending repos tell you what problems people are solving right now.
  Claude tells you which of those problems Kevin would actually care about.
  The intersection is where the good weekend projects live.

  Not "build a todo app."
  Not "clone Notion."
  Something real, completable, and specifically yours.

Built by Claude (Cycle 8). The best ideas are stolen from trends and made personal.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "ideas": cmd_ideas,
    "trending": cmd_trending,
    "saved": cmd_saved,
    "save": cmd_save,
    "help": lambda _: cmd_help(),
    "--help": lambda _: cmd_help(),
    "-h": lambda _: cmd_help(),
}


def main():
    argv = sys.argv[1:]

    if not argv:
        cmd_ideas([])  # default: generate ideas
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
