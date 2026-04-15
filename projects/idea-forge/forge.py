#!/usr/bin/env python3
"""
forge — AI-powered project idea generator

Watches what's trending on GitHub in Kevin's tech stack, then asks Claude
to suggest weekend project ideas tailored to his profile and interests.

Zero extra dependencies — stdlib only + optional ANTHROPIC_API_KEY.
Uses GitHub Search API (no auth needed for basic queries, 60 req/hr).

Usage:
    forge trending                          # What's hot on GitHub right now
    forge trending --lang typescript        # Filter to a language
    forge trending --days 30               # Wider window (default: 14)
    forge ideas                            # Claude-powered idea suggestions
    forge ideas --topic "cli tools"        # Focused on a topic
    forge ideas --lang python              # Constrain to a language
    forge plan "a markdown-based wiki CLI" # Rough implementation plan
    forge spark                            # 3 micro-ideas, no API key required
    forge help
"""

import json
import os
import random
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent

KEVIN_PROFILE = """Kevin Geng — full-stack software engineer at Faire (Toronto).
Primary stack: TypeScript, React, Python, Java/Kotlin, AWS.
Active projects: matchamap.club (matcha cafe map), kegbot (personal assistant CLI),
recipe-ai (cooking assistant), dev-insights (GitHub dashboard).
Interests: personal automation, Discord bots, maps/geodata, cooking, ML/AI, games.
Build style: pragmatic, prefers zero-dependency tools, CLI-first, stdlib-friendly.
Enjoys tools with personality — easter eggs, opinionated UX, things that make him smile."""

SUPPORTED_LANGS = ["python", "typescript", "javascript", "react", "go", "rust", "kotlin"]

# ─── Spark seeds (offline inspiration, no API needed) ─────────────────────────

SPARK_SEEDS = [
    # Tooling
    ("cli", "A CLI that reads your shell history and suggests aliases for commands you type too often"),
    ("cli", "A terminal stopwatch that tweets a motivational message when you exceed 25 min (Pomodoro + shame)"),
    ("data", "A local-first expense tracker that reads bank email PDFs and categorizes them with regex"),
    ("data", "A JSON-to-SQL migration tool that infers table schemas from arbitrary JSON blobs"),
    ("maps", "A geofencing notifier: define a polygon in GeoJSON, get pinged when your phone exits it"),
    ("maps", "A commute-quality scorer: given a transit route, score it by delay history and weather"),
    # Discord / bots
    ("discord", "A Discord bot that listens for '?' messages and auto-reposts them to a #help-needed channel"),
    ("discord", "A daily stand-up bot that DMs team members, collects replies, and posts a summary"),
    ("discord", "A bot that tracks who reacts to what and generates a weekly 'vibe report' for your server"),
    # Cooking / food
    ("cooking", "A recipe diff tool: compare two recipes and highlight what changed between versions"),
    ("cooking", "A mise-en-place timer: given a recipe, generate a backwards cooking schedule from dinner time"),
    ("cooking", "A pantry expiry tracker: scan grocery receipts, infer shelf life, warn before things go bad"),
    # Developer productivity
    ("devtools", "A git commit linter that checks commit messages against your personal style guide using Claude"),
    ("devtools", "A PR review time tracker: parse GitHub webhooks, visualize review cycle time across repos"),
    ("devtools", "A dead-code detector that cross-references exported symbols against grep in dependent repos"),
    # ML / AI
    ("ml", "A local image classifier that categorizes your Downloads folder by visual content (CLIP)"),
    ("ml", "A changelog summarizer: given a git log, generate human-readable release notes using Claude"),
    ("ml", "A meeting transcript analyzer that extracts action items and owners using structured output"),
    # Games
    ("games", "A text-based Blackjack with a persistent leaderboard and a 'house style' personality"),
    ("games", "A CLI trivia engine that pulls from Open Trivia DB and tracks your weak categories over time"),
    ("games", "A word-association game where Claude plays adversary, picking words you'll least expect"),
    # Finance / automation
    ("finance", "A net worth snapshot tool: reads brokerage emails, parses balances, appends to a CSV timeline"),
    ("finance", "A subscription tracker that monitors recurring transactions and alerts on price increases"),
    # Misc
    ("misc", "A cron job that reads your INBOX.md every morning and sends a Telegram digest"),
    ("misc", "A README generator: given a project directory, infer purpose and write a draft README"),
    ("misc", "A local search engine over your own markdown notes using TF-IDF (no vector DB)"),
]


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
            print("⚠️  GitHub rate limit hit. Add GITHUB_TOKEN to .env for 5000 req/hr.", file=sys.stderr)
        else:
            body = e.read().decode("utf-8", errors="replace")
            print(f"⚠️  GitHub API error {e.code}: {body[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def fetch_trending(lang: str, days: int = 14, per_page: int = 8) -> list[dict]:
    """
    Fetch recently-created, rapidly-rising repos in a given language.
    Sorts by stars, created in the last `days` days, to surface genuine new things.
    """
    since = (date.today() - timedelta(days=days)).isoformat()
    # Use spaces as AND separators (URL-encode the whole query string)
    q = f"language:{lang} created:>{since} stars:>5"
    url = (
        "https://api.github.com/search/repositories"
        f"?q={urllib.parse.quote(q, safe='')}&sort=stars&order=desc&per_page={per_page}"
    )
    data = _github_request(url)
    if not data or "items" not in data:
        return []
    return data["items"]


def format_repo(repo: dict) -> str:
    """Format a repo as a compact display line."""
    name = repo.get("full_name", "?")
    desc = repo.get("description") or "no description"
    stars = repo.get("stargazers_count", 0)
    lang = repo.get("language") or "?"
    created = repo.get("created_at", "")[:10]
    return f"  ★{stars:>5}  {name:<40}  [{lang}]  {created}\n           {desc[:90]}"


# ─── Claude API ───────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 800) -> str:
    if not ANTHROPIC_API_KEY:
        return "⚠️  ANTHROPIC_API_KEY not set. Add it to projects/kegbot-claude/.env"

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
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"[Claude API error {e.code}: {body[:200]}]"
    except Exception as e:
        return f"[Claude API error: {e}]"


# ─── Commands ─────────────────────────────────────────────────────────────────


def get_flag(args: list[str], flag: str, default: str = "") -> str:
    """Extract --flag value from args list."""
    if flag in args:
        idx = args.index(flag)
        if idx + 1 < len(args):
            return args[idx + 1]
    return default


def cmd_trending(args: list[str]):
    """Show what's trending on GitHub in Kevin's stack."""
    lang = get_flag(args, "--lang", "")
    days = int(get_flag(args, "--days", "14"))

    langs_to_check = [lang] if lang else ["python", "typescript", "go"]

    print(f"🔭 forge trending — rising stars on GitHub (last {days} days)\n")

    for language in langs_to_check:
        print(f"── {language.title()} " + "─" * (50 - len(language)))
        repos = fetch_trending(language, days=days)
        if not repos:
            print("  No results (rate limit or no matches).\n")
            continue
        for repo in repos:
            print(format_repo(repo))
            print()
        print()


def cmd_ideas(args: list[str]):
    """Claude-powered project idea suggestions based on trending repos."""
    lang = get_flag(args, "--lang", "")
    topic = get_flag(args, "--topic", "")
    days = int(get_flag(args, "--days", "14"))

    print("💡 forge ideas — generating project ideas tailored to you...\n")

    # Fetch trending repos for context
    langs_to_fetch = [lang] if lang else ["python", "typescript", "go"]
    trending_snippets = []

    for language in langs_to_fetch:
        repos = fetch_trending(language, days=days, per_page=5)
        if repos:
            for r in repos[:4]:
                name = r.get("full_name", "?")
                desc = r.get("description") or ""
                stars = r.get("stargazers_count", 0)
                trending_snippets.append(f"  ★{stars}  {name} — {desc[:80]}")

    trending_block = "\n".join(trending_snippets) if trending_snippets else "(no trending data available)"

    topic_clause = f"\nFocus area: **{topic}**" if topic else ""
    lang_clause = f"\nLanguage preference: **{lang}**" if lang else "\nLanguage: open — whatever fits best (TypeScript or Python preferred)"

    prompt = f"""You are idea-forge, an AI that generates project ideas for a specific developer.

Developer profile:
{KEVIN_PROFILE}

What's trending on GitHub right now (recently created, rapidly gaining stars):
{trending_block}

{topic_clause}{lang_clause}

Generate exactly 5 concrete weekend project ideas for this developer.

For each idea:
- **Name** — punchy, memorable (3-5 words max)
- **What it does** — one sentence, specific and tangible
- **Why it fits** — one sentence: why this developer + why now (tie to the trend if possible)
- **Starter move** — the single first thing to build (a specific function, API call, or file)
- **Stack** — 2-3 technologies, no fluff

Format as a numbered list. Be specific — not "a tool that analyzes code" but "a CLI that reads git blame output and ranks files by churn rate."
Surprise him. He's tired of CRUD apps.
"""

    print("[claude] Synthesizing ideas from trending repos + your profile...\n")
    result = claude_call(prompt, max_tokens=1000)
    print("─" * 60)
    print(result)
    print("─" * 60)
    print()


def cmd_plan(args: list[str]):
    """Generate a rough implementation plan for a given idea."""
    # Idea is everything after 'plan' that isn't a flag
    idea_parts = [a for a in args if not a.startswith("--")]
    idea = " ".join(idea_parts).strip().strip('"').strip("'")

    if not idea:
        print("Usage: forge plan \"your project idea\"")
        print("Example: forge plan \"a terminal-based personal finance tracker\"")
        sys.exit(1)

    print(f"📐 forge plan — implementation roadmap\n")
    print(f"Idea: {idea}\n")

    prompt = f"""You are a pragmatic software architect helping a solo developer plan a weekend project.

Developer profile:
{KEVIN_PROFILE}

Project idea: "{idea}"

Generate a **tight, actionable implementation plan** for this project. The developer works alone, in weekend blocks (4-8 hours total).

Format:
## What it is
One paragraph: what problem it solves, who uses it, what success looks like.

## Tech stack
Bullet list: language, key libraries/APIs, why each.

## Milestones (4 steps max)
For each milestone: what's done, what you can demo.

## File structure
A minimal tree of files/directories to create. No over-engineering.

## First 30 minutes
Exact steps: specific commands, API endpoints to hit, code to write. Make it runnable fast.

## Gotchas
2-3 things that will bite them if not thought about upfront.

Be specific. No boilerplate. If the stack is wrong for this developer, say so and suggest better.
"""

    print("[claude] Generating implementation plan...\n")
    result = claude_call(prompt, max_tokens=1200)
    print("─" * 60)
    print(result)
    print("─" * 60)
    print()


def cmd_spark(args: list[str]):
    """
    Quick offline inspiration — 3 random micro-ideas, no API key needed.
    Refreshes each call (seeded by today's date for consistency within a day).
    """
    # Seed by today's date so you get the same 3 ideas all day, different tomorrow
    rng = random.Random(date.today().toordinal())
    picks = rng.sample(SPARK_SEEDS, min(3, len(SPARK_SEEDS)))

    print("✨ forge spark — today's micro-ideas (offline mode)\n")
    print("These are seeds, not specs. Steal the premise, make it yours.\n")

    for i, (category, idea) in enumerate(picks, 1):
        print(f"  {i}. [{category}]")
        print(f"     {idea}")
        print()

    print("─" * 60)
    print("Run `forge ideas` for Claude-powered ideas based on what's trending.")
    print("Run `forge plan \"<idea>\"` for a full implementation plan.")
    print()


def cmd_help():
    print("""
🔭 forge — AI-powered project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    forge <command> [options]

COMMANDS

  trending                   What's gaining stars on GitHub right now
    --lang <language>          Filter to one language (python, typescript, go, etc.)
    --days N                   Lookback window in days (default: 14)

  ideas                      Claude-powered project ideas for your profile
    --lang <language>          Constrain to a language
    --topic <topic>            Focus on a topic ("cli tools", "discord bots", etc.)
    --days N                   Trending data lookback (default: 14)

  plan "<idea description>"  Full implementation roadmap for a specific idea
                               (wrap idea in quotes if it has spaces)

  spark                      3 random micro-ideas, no API key required
                               (refreshes daily)

SETUP
  Optional: add ANTHROPIC_API_KEY to projects/kegbot-claude/.env for AI features.
  GitHub Token (GITHUB_TOKEN) increases rate limits from 60 to 5000 req/hr.

EXAMPLES
    forge spark
    forge trending
    forge trending --lang rust --days 7
    forge ideas
    forge ideas --topic "discord bots"
    forge ideas --lang typescript
    forge plan "a terminal task manager that syncs with GitHub issues"

NOTES
  `trending` and `ideas` use the GitHub Search API — no auth needed for casual use.
  `spark` works fully offline and seeds from today's date (same 3 ideas all day).
  `plan` uses Claude API — requires ANTHROPIC_API_KEY.

Built by Claude (Cycle 8). The meta-project: Claude suggesting what Claude should build next.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "trending": cmd_trending,
    "ideas": cmd_ideas,
    "plan": cmd_plan,
    "spark": cmd_spark,
    "help": lambda _: cmd_help(),
    "--help": lambda _: cmd_help(),
    "-h": lambda _: cmd_help(),
}


def main():
    argv = sys.argv[1:]

    if not argv:
        cmd_spark([])  # default: quick offline inspiration
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
