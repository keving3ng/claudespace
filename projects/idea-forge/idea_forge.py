#!/usr/bin/env python3
"""
idea-forge — AI-powered weekend project idea generator

Watches what's trending on GitHub in Kevin's tech stack, then asks Claude
to synthesize it into project ideas tailored to his interests and history.
Zero external dependencies. Pure stdlib + Anthropic API.

Usage:
    idea_forge.py ideas                     # 5 tailored project ideas
    idea_forge.py ideas --stack python      # filter by language
    idea_forge.py ideas --stack typescript
    idea_forge.py ideas --stack all         # everything trending
    idea_forge.py trending                  # just show trending repos (no Claude)
    idea_forge.py trending --stack rust     # any language GitHub supports
    idea_forge.py spark                     # one wild, opinionated project pitch
    idea_forge.py help
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
DEFAULT_STACKS = ["python", "typescript"]  # Kevin's primary languages

# GitHub trending search: repos created in last 30 days, sorted by stars
TRENDING_DAYS = 30
TRENDING_PER_STACK = 8  # repos to fetch per language

KEVIN_CONTEXT = """Kevin Geng is a full-stack engineer at Faire (Toronto). His stack: React,
TypeScript, Java/Spring Boot, Python, AWS. His active projects:
- matchamap.club — opinionated matcha cafe finder (maps, place data, curation)
- claudespace — this repo; autonomous Claude AI build lab
- kegbot — Python personal assistant CLI (daily briefings, automation)
- cookbook repo — cooking interest, recipe tools
Past interests: facial recognition/ML, Discord bots, personal finance automation,
transit status tools, board games. Loves: tools with personality, zero-dependency
scripts, practical automation, things that earn daily use. Hates: boilerplate, setup
hell, speculative abstraction. Builder energy: pragmatic + occasionally delighted by
a well-placed easter egg."""


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


# ─── GitHub trending ──────────────────────────────────────────────────────────


def _github_search(query: str, per_page: int = 10) -> list[dict]:
    """Search GitHub repos with a query string."""
    encoded = urllib.parse.quote(query)
    url = f"https://api.github.com/search/repositories?q={encoded}&sort=stars&order=desc&per_page={per_page}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "idea-forge/1.0",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data.get("items", [])
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"⚠️  GitHub search error {e.code}: {body[:200]}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return []


def fetch_trending(language: str, days: int = TRENDING_DAYS, per_page: int = TRENDING_PER_STACK) -> list[dict]:
    """Fetch trending repos for a language created in the last N days."""
    since = (date.today() - timedelta(days=days)).isoformat()
    query = f"language:{language} created:>{since} stars:>50"
    repos = _github_search(query, per_page=per_page)
    return repos


def fetch_trending_multi(stacks: list[str], days: int = TRENDING_DAYS) -> dict[str, list[dict]]:
    """Fetch trending repos for multiple languages."""
    results = {}
    for lang in stacks:
        print(f"  🔍 Fetching trending {lang} repos...", flush=True)
        results[lang] = fetch_trending(lang, days=days)
    return results


def format_repo_summary(repo: dict) -> str:
    """One-line summary of a repo for use in a prompt."""
    name = repo.get("full_name", "?")
    stars = repo.get("stargazers_count", 0)
    desc = (repo.get("description") or "").strip()[:100]
    topics = ", ".join(repo.get("topics", [])[:5])
    lang = repo.get("language") or ""
    parts = [f"★{stars:,}  {name}"]
    if lang:
        parts.append(f"[{lang}]")
    if desc:
        parts.append(f"— {desc}")
    if topics:
        parts.append(f"  ({topics})")
    return "  ".join(parts)


# ─── Claude calls ─────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 800) -> str:
    """Thin wrapper around Anthropic messages API."""
    if not ANTHROPIC_API_KEY:
        return "⚠️  ANTHROPIC_API_KEY not set. Set it in .env or environment."

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


def cmd_trending(args: list[str]):
    """Show trending repos without Claude synthesis."""
    stacks = _parse_stacks(args)
    days = _parse_days(args)

    print(f"📈 Trending on GitHub (last {days} days)\n")

    trend_data = fetch_trending_multi(stacks, days=days)
    print()

    found_any = False
    for lang, repos in trend_data.items():
        if not repos:
            print(f"── {lang.title()} ──────────────────────────────────────────")
            print("  (no results — may be rate-limited or no matching repos)")
            print()
            continue
        found_any = True
        print(f"── {lang.title()} " + "─" * max(0, 48 - len(lang)) + "\n")
        for repo in repos:
            print(f"  {format_repo_summary(repo)}")
        print()

    if not found_any:
        print("⚠️  No trending repos found. Check GITHUB_TOKEN for higher rate limits.")


def cmd_ideas(args: list[str]):
    """Fetch trending repos and ask Claude to synthesize weekend project ideas."""
    stacks = _parse_stacks(args)
    days = _parse_days(args)

    print(f"💡 idea-forge — Weekend project ideas from the GitHub zeitgeist\n")
    print(f"   Stacks: {', '.join(stacks)}  |  Trending window: last {days} days\n")

    trend_data = fetch_trending_multi(stacks, days=days)
    print()

    # Build trending context for the prompt
    trending_block = ""
    total_repos = 0
    for lang, repos in trend_data.items():
        if not repos:
            continue
        trending_block += f"\n### Trending {lang.title()} (last {days} days)\n"
        for repo in repos:
            trending_block += format_repo_summary(repo) + "\n"
            total_repos += 1

    if total_repos == 0:
        print("⚠️  Couldn't fetch trending repos. Check your network or GITHUB_TOKEN.")
        print("   Try `idea_forge.py trending` to debug the data source.")
        return

    today = date.today().strftime("%B %d, %Y")

    prompt = f"""You are idea-forge, an AI that watches GitHub's trending repos and translates
the zeitgeist into personalized weekend project ideas.

Today is {today}. Here's what's hot on GitHub right now:
{trending_block}

---
About the developer you're generating ideas for:
{KEVIN_CONTEXT}

---
Your job: Generate **5 tailored weekend project ideas** for Kevin.

Rules:
- Each idea should be inspired by or adjacent to something in the trending data above.
  Name the specific trend/library/technique that sparked it.
- Tailor each idea to Kevin's stack AND his interests (maps, automation, cooking, kegbot, matcha, ML, games).
- Each idea needs: a punchy name, one-sentence pitch, and a rough implementation sketch (2-3 lines, specific tech choices).
- One idea should be small (1-day build). One should be ambitious (weekend+). The rest can be anywhere.
- One idea should be genuinely weird — something Kevin wouldn't have thought of himself.
- Be concrete. "Build a CLI that..." is better than "Explore the intersection of...".
- Use first person occasionally ("I'd start with...", "The interesting part is..."). This isn't a resume.

Format each idea as:
## [name] — [size: tiny|small|medium|weekend+]
[One-sentence pitch]
[2-3 line implementation sketch]
*Sparked by: [specific trending repo or technique]*
"""

    print("[claude] Synthesizing ideas from trending data...\n")
    ideas = claude_call(prompt, max_tokens=1200)

    print("─" * 64)
    print(ideas)
    print("─" * 64)
    print(f"\n  {total_repos} trending repos analyzed · {len(stacks)} language(s) · {today}")
    print("  Run `idea_forge.py trending` to see the raw source data.\n")


def cmd_spark(args: list[str]):
    """One opinionated, fully-formed project pitch. No menus. Just a spark."""
    stacks = _parse_stacks(args)

    print("⚡ idea-forge spark — one project, fully pitched\n")

    # Fetch a small slice of trending to seed the prompt
    print("  Fetching a few trending signals...", flush=True)
    repos = []
    for lang in stacks[:2]:
        batch = fetch_trending(lang, days=14, per_page=5)
        repos.extend(batch)

    trending_sample = "\n".join(format_repo_summary(r) for r in repos[:10]) if repos else "(no data)"

    prompt = f"""You are idea-forge in spark mode. No lists. No options. Just one fully-formed project pitch.

The developer: {KEVIN_CONTEXT}

Some things trending on GitHub right now:
{trending_sample}

---
Pick ONE project idea. The most interesting one. The one you'd actually want to build.
Pitch it like you're excited about it. Include:
- A name with personality
- What it does (one vivid sentence)
- Why now (what trend makes this the right moment)
- Exactly how you'd build it: specific files, key functions, the interesting problem to solve
- One potential easter egg or detail that would make Kevin smile when he discovers it

This should read like a message from a collaborator who just had an idea at 11pm and can't wait to tell you.
Under 300 words. No headers. Just prose.
"""

    print("\n[claude] Forging a spark...\n")
    pitch = claude_call(prompt, max_tokens=500)

    print("─" * 64)
    print(pitch)
    print("─" * 64 + "\n")


def cmd_help():
    print("""
⚡ idea-forge — Weekend project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Watches what's trending on GitHub. Asks Claude what Kevin should build next.
Recursive? A little. Fun? Definitely.

USAGE
    idea_forge.py <command> [options]

COMMANDS

  ideas                    5 tailored project ideas from the GitHub zeitgeist
  ideas --stack python     Filter by language (python, typescript, go, rust, etc.)
  ideas --stack all        Pull from python + typescript + go

  trending                 Show trending repos without Claude synthesis
  trending --stack rust    Any language GitHub supports

  spark                    One opinionated project pitch. No list. Just a spark.

  help                     Show this help

OPTIONS
  --stack <lang>           Language filter (default: python, typescript)
                           Use "all" for python+typescript+go
  --days N                 Trending window in days (default: 30)

SETUP
  No API key for trending data (GitHub search is public, rate-limited to 10 req/min).
  Optionally add GITHUB_TOKEN to .env for higher rate limits.
  Add ANTHROPIC_API_KEY to .env to enable Claude synthesis.

  cp projects/kegbot-claude/.env.example projects/kegbot-claude/.env
  # Add ANTHROPIC_API_KEY=sk-ant-...

EXAMPLES
    idea_forge.py ideas
    idea_forge.py ideas --stack typescript --days 14
    idea_forge.py trending --stack python
    idea_forge.py spark

NOTES
  GitHub search returns repos created in the last N days with >50 stars.
  This isn't a popularity contest — it's a signal about what people are building.
  Claude synthesizes the signal into ideas that fit Kevin's actual interests.

Built by Claude (Cycle 8). Because someone should be watching what the world is building.
""")


# ─── Arg helpers ──────────────────────────────────────────────────────────────


def _parse_stacks(args: list[str]) -> list[str]:
    if "--stack" in args:
        idx = args.index("--stack")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val == "all":
                return ["python", "typescript", "go"]
            return [val]
    return list(DEFAULT_STACKS)


def _parse_days(args: list[str]) -> int:
    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                return int(args[idx + 1])
            except ValueError:
                pass
    return TRENDING_DAYS


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "ideas": cmd_ideas,
    "trending": cmd_trending,
    "spark": cmd_spark,
    "help": lambda _: cmd_help(),
    "--help": lambda _: cmd_help(),
    "-h": lambda _: cmd_help(),
}


def main():
    argv = sys.argv[1:]

    if not argv:
        cmd_ideas([])
        return

    command = argv[0]
    rest = argv[1:]

    if command not in COMMANDS:
        print(f"❓ Unknown command: {command}")
        print("Run `idea_forge.py help` for available commands.")
        sys.exit(1)

    COMMANDS[command](rest)


if __name__ == "__main__":
    main()
