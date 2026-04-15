#!/usr/bin/env python3
"""
forge — AI-powered weekend project idea generator

Watches trending GitHub repos in Kevin's tech stack and uses Claude to suggest
personalized weekend project ideas with rough implementation plans.

Zero dependencies beyond stdlib. Uses GitHub Search API + Anthropic API.

Usage:
    forge trending                # trending repos across Kevin's full stack
    forge trending --lang python  # filter to one language
    forge trending --days 14      # look back 14 days (default: 30)
    forge ideas                   # 3 Claude-generated weekend project ideas
    forge ideas --topic "games"   # ideas focused on a topic
    forge spark <topic>           # quick idea burst for any topic
    forge help
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent

KEVIN_STACK = ["typescript", "python", "go", "java"]
KEVIN_INTERESTS = [
    "react",
    "discord bot",
    "personal automation",
    "maps and geo",
    "cooking tools",
    "machine learning",
    "games",
    "personal finance",
    "CLI tools",
    "dashboards",
]

KEVIN_BIO = """Kevin Geng is a full-stack software engineer at Faire in Toronto.
Stack: React, TypeScript, Java/Kotlin, Python, Go, AWS.
Active projects: matchamap.club (opinionated matcha cafe finder), claudespace (autonomous AI build lab), kegbot (personal CLI assistant), cookbook.
Interests: cooking, ML/AI, Discord bots, personal automation, maps, board games, transit data.
Vibe: pragmatic builder who likes tools that are genuinely useful AND a bit delightful.
Prefers: zero-dependency CLIs, pure Python/TypeScript, things that solve real daily friction."""

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
            print("⚠️  GitHub rate limit hit. Set GITHUB_TOKEN for higher limits.", file=sys.stderr)
        else:
            body = e.read().decode("utf-8", errors="replace")
            print(f"⚠️  GitHub API error {e.code}: {body[:160]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def fetch_trending_repos(lang: str, days: int = 30) -> list[dict]:
    """
    Fetch recently-created repos with high stars for a language.
    This is the best proxy for 'trending' using the public Search API.
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    query = urllib.parse.quote(f"language:{lang} created:>{cutoff} stars:>5")
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={query}&sort=stars&order=desc&per_page=8"
    )
    data = _github_request(url)
    if not data or "items" not in data:
        return []
    return data["items"]


def fetch_trending_all(langs: list[str], days: int = 30) -> dict[str, list[dict]]:
    """Fetch trending repos for each language. Returns {lang: [repos]}."""
    results = {}
    for lang in langs:
        repos = fetch_trending_repos(lang, days)
        if repos:
            results[lang] = repos
    return results


# ─── Formatting ───────────────────────────────────────────────────────────────


def _stars_str(n: int) -> str:
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)


def _truncate(s: str, n: int) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[: n - 1] + "…"


def format_repos_for_display(repos_by_lang: dict[str, list[dict]]) -> str:
    lines = []
    for lang, repos in repos_by_lang.items():
        if not repos:
            continue
        lines.append(f"\n  ── {lang.title()} ──────────────────────────────────────")
        for r in repos[:5]:
            stars = _stars_str(r.get("stargazers_count", 0))
            desc = _truncate(r.get("description") or "", 64)
            name = r["full_name"]
            lines.append(f"  ★{stars:>5}  {name}")
            if desc:
                lines.append(f"           {desc}")
    return "\n".join(lines)


def format_repos_for_prompt(repos_by_lang: dict[str, list[dict]]) -> str:
    """Compact format for Claude prompt — name + description only."""
    lines = []
    for lang, repos in repos_by_lang.items():
        if not repos:
            continue
        lines.append(f"\n[{lang.title()} trending]")
        for r in repos[:5]:
            name = r["full_name"]
            desc = (r.get("description") or "no description").strip()
            stars = _stars_str(r.get("stargazers_count", 0))
            lines.append(f"  - {name} ({stars}★): {_truncate(desc, 80)}")
    return "\n".join(lines)


# ─── Claude ───────────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 700) -> str:
    if not ANTHROPIC_API_KEY:
        return "⚠️  ANTHROPIC_API_KEY not set — cannot generate ideas."

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
        with urllib.request.urlopen(req, timeout=40) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"[Claude API error {e.code}: {body[:200]}]"
    except Exception as e:
        return f"[Claude API error: {e}]"


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_trending(args: list[str]):
    """Show trending repos in Kevin's stack, optionally filtered by language."""
    lang_filter = None
    if "--lang" in args:
        idx = args.index("--lang")
        if idx + 1 < len(args):
            lang_filter = args[idx + 1].lower()
    elif "-l" in args:
        idx = args.index("-l")
        if idx + 1 < len(args):
            lang_filter = args[idx + 1].lower()

    days = 30
    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                days = int(args[idx + 1])
            except ValueError:
                pass

    langs = [lang_filter] if lang_filter else KEVIN_STACK

    print(f"🔭 forge trending — hot repos in your stack (last {days} days)\n")

    repos_by_lang = fetch_trending_all(langs, days)

    if not repos_by_lang:
        print("⚠️  No trending repos found. GitHub rate limit or network issue?")
        return

    print(format_repos_for_display(repos_by_lang))

    total = sum(len(v) for v in repos_by_lang.values())
    langs_found = list(repos_by_lang.keys())
    print(f"\n\n  {total} repos across {len(langs_found)} language(s): {', '.join(langs_found)}")
    print(
        "  💡 Run `forge ideas` to get personalized project ideas based on what's trending.\n"
    )


def cmd_ideas(args: list[str]):
    """Generate 3 personalized weekend project ideas using trending repos + Kevin's profile."""
    topic_override = None
    if "--topic" in args:
        idx = args.index("--topic")
        if idx + 1 < len(args):
            topic_override = args[idx + 1]

    days = 30
    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                days = int(args[idx + 1])
            except ValueError:
                pass

    raw = "--raw" in args

    print("💡 forge ideas — generating weekend project ideas for you\n")

    if not raw:
        print("  Fetching trending repos...")
    repos_by_lang = fetch_trending_all(KEVIN_STACK, days)
    trending_text = format_repos_for_prompt(repos_by_lang)

    if raw:
        print("── TRENDING REPOS (raw) ────────────────────────────────")
        print(trending_text[:2000])
        return

    topic_line = f"\nFocus especially on ideas related to: {topic_override}" if topic_override else ""

    prompt = f"""You are idea-forge, an AI project idea generator for a specific developer.

DEVELOPER PROFILE:
{KEVIN_BIO}

TRENDING REPOS IN HIS STACK (last {days} days):
{trending_text}
{topic_line}

Generate exactly 3 weekend project ideas for Kevin. Each idea should:
1. Be buildable in a weekend (1-3 days) by one developer
2. Connect to either something trending OR his existing interests (cooking, maps, automation, Discord, ML)
3. Use at least one technology from his stack (TypeScript/React, Python, Go, Java/Spring)
4. Feel genuinely useful OR genuinely delightful — ideally both
5. Be specific enough that he could start coding it tonight

FORMAT for each idea:
**[Idea N] — [Punchy Project Name]**
*One-line pitch: what it does and why Kevin specifically would care*
Stack: [languages/tools]
Build it: [3-5 concrete steps — specific enough to be a rough plan, not just vibes]
Twist: [one unexpected or fun detail that makes this more interesting than it sounds]

No filler. No "this could be a great way to learn X." Kevin already knows his stack.
Think like a developer who's read his GitHub and knows what makes him smile.
"""

    print("  [claude] Synthesizing ideas...\n")
    ideas = claude_call(prompt, max_tokens=900)

    print("─" * 64)
    print(ideas)
    print("─" * 64)
    print(
        "\n  Run `forge spark <topic>` to drill deeper into any of these topics.\n"
    )


def cmd_spark(args: list[str]):
    """Quick idea burst for a specific topic — forge spark 'board games'"""
    if not args or args[0].startswith("--"):
        print("❓ Usage: forge spark <topic>")
        print("   Example: forge spark 'board games'")
        print("            forge spark 'cooking automation'")
        sys.exit(1)

    # Collect topic from args (allow multi-word without quotes)
    topic = " ".join(a for a in args if not a.startswith("--"))

    print(f"⚡ forge spark — {topic}\n")

    prompt = f"""You are idea-forge. Give me 5 quick project ideas about "{topic}" for this developer:

{KEVIN_BIO}

Rules:
- 5 ideas, numbered
- Each idea: one punchy name, one sentence pitch, one sentence on tech (from his stack)
- Weekend-sized, not enterprise SaaS
- At least one idea should be weird or unexpected
- Under 250 words total. No fluff.
"""

    if not ANTHROPIC_API_KEY:
        print("⚠️  ANTHROPIC_API_KEY not set. Can't generate ideas without it.")
        print(f"\nSearch GitHub for trending '{topic}' repos:")
        encoded = urllib.parse.quote(f"{topic} created:>2024-01-01 stars:>10")
        print(f"  https://api.github.com/search/repositories?q={encoded}&sort=stars")
        return

    print("[claude] Sparking...\n")
    ideas = claude_call(prompt, max_tokens=600)

    print("─" * 60)
    print(ideas)
    print("─" * 60 + "\n")


def cmd_help():
    print("""
💡 forge — AI weekend project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    forge <command> [options]

COMMANDS

  trending                   Hot repos in your stack (TypeScript, Python, Go, Java)
    --lang LANG                Filter to one language
    -l LANG                    Shorthand for --lang
    --days N                   Lookback window in days (default: 30)

  ideas                      3 personalized weekend project ideas via Claude
    --topic TOPIC              Focus ideas on a specific topic
    --days N                   Trending data window (default: 30)
    --raw                      Dump trending data without Claude (debug)

  spark <topic>               Quick 5-idea burst on any topic
                               e.g.: forge spark "board games"
                                     forge spark "cooking automation"
                                     forge spark "transit data"

  help                        Show this help

SETUP
    No API key needed for `forge trending`.
    Add ANTHROPIC_API_KEY to .env for `forge ideas` and `forge spark`.
    Optionally set GITHUB_TOKEN for higher GitHub API rate limits.

EXAMPLES
    forge trending
    forge trending --lang python --days 14
    forge ideas
    forge ideas --topic "personal finance"
    forge spark "matcha cafe tooling"
    forge spark "discord bots"

HOW IT WORKS
    `forge trending` hits the GitHub Search API to find recently-created repos
    with high star counts — a reliable proxy for what's gaining momentum.
    `forge ideas` feeds that data + Kevin's profile to Claude, which synthesizes
    project ideas that actually fit his stack and interests, not generic tutorials.

Built by Claude (Cycle 8). Because the best project idea is one you're already
excited about before you've written a single line.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "trending": cmd_trending,
    "ideas": cmd_ideas,
    "spark": cmd_spark,
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
        # Try treating it as a spark topic
        print(f"❓ Unknown command: {command}")
        print('Tip: `forge spark "{command}"` to get ideas on that topic.')
        print("Run `forge help` for all commands.")
        sys.exit(1)

    COMMANDS[command](rest)


if __name__ == "__main__":
    main()
