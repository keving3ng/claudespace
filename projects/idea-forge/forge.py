#!/usr/bin/env python3
"""
idea-forge — AI weekend project idea generator for Kevin

Watches what's trending in your GitHub stack, then collaborates with Claude
to suggest projects you'll actually want to build.

Usage:
    forge trending [language]    # trending repos in your stack
    forge suggest                # generate 4 tailored weekend project ideas
    forge plan "your idea"       # detailed implementation plan
    forge spark                  # one quick inspiring idea (changes daily)
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

KEVIN_STACK = ["python", "typescript", "javascript"]

KEVIN_CONTEXT = """\
Kevin Geng (@keving3ng) is a full-stack engineer at Faire in Toronto.
Stack: React, TypeScript, Python, Java/Kotlin, AWS.
Active projects:
- matchamap.club — opinionated matcha cafe map (actively building)
- kegbot — personal assistant bot (Discord, daily briefings, GitHub summaries)
- recipe-ai — ingredient-based recipe suggestions CLI
- dev-insights — terminal GitHub contribution heatmap + streak tracker
Interests: cooking, Discord bots, personal automation, maps & place data,
           ML/AI, gaming, transit, teaching.
Preferred aesthetics: zero-dependency Python CLIs, TypeScript tools,
                      clever + useful + a little weird.
                      NOT enterprise software. NOT B2B SaaS.
He opens his terminal expecting something unexpected."""

# ─── Env ──────────────────────────────────────────────────────────────────────


def load_env():
    for path in [
        Path(__file__).parent / ".env",
        REPO_ROOT / "projects" / "kegbot-claude" / ".env",
        REPO_ROOT / ".env",
    ]:
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ─── GitHub helpers ───────────────────────────────────────────────────────────


def _gh_headers() -> dict:
    h = {
        "User-Agent": "idea-forge/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def fetch_trending(language: str, days: int = 7, limit: int = 5) -> list[dict]:
    """Fetch trending GitHub repos for a language (recently created, high stars)."""
    since = (date.today() - timedelta(days=days)).isoformat()
    q = f"language:{language} created:>{since} stars:>=5"
    url = (
        "https://api.github.com/search/repositories"
        f"?q={urllib.parse.quote(q)}&sort=stars&order=desc&per_page={limit}"
    )
    try:
        req = urllib.request.Request(url, headers=_gh_headers())
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())
        return data.get("items", [])
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(f"  [rate limited for {language} — set GITHUB_TOKEN for more]", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  [error fetching {language}: {e}]", file=sys.stderr)
        return []


# ─── Claude helpers ───────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 1200) -> str:
    if not ANTHROPIC_API_KEY:
        return (
            "[No ANTHROPIC_API_KEY — set it to get AI-generated ideas]\n\n"
            "Tip: cp projects/kegbot-claude/.env.example projects/kegbot-claude/.env\n"
            "     then add your ANTHROPIC_API_KEY."
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


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_trending(args: list[str]):
    """Show trending repos in Kevin's stack."""
    if args and not args[0].startswith("-"):
        langs = [args[0]]
    else:
        langs = KEVIN_STACK

    today = date.today().isoformat()
    print(f"🔥 GitHub Trending — {today}\n")

    for lang in langs:
        pad = max(0, 44 - len(lang))
        print(f"── {lang.capitalize()} (last 7 days) {'─' * pad}")
        repos = fetch_trending(lang, days=7, limit=5)
        if not repos:
            print("   (no results or rate limited)\n")
            continue
        for r in repos:
            stars = r.get("stargazers_count", 0)
            desc = r.get("description") or ""
            desc = (desc[:65] + "…") if len(desc) > 65 else desc
            name = r["full_name"]
            print(f"  ★ {stars:>5}  {name}")
            if desc:
                print(f"           {desc}")
        print()


def cmd_suggest(args: list[str]):
    """Generate 4 tailored weekend project ideas using trending data + Claude."""
    print("⚗️  Forge is gathering trends and thinking…\n")

    # Collect trending repos as context
    trend_lines: list[str] = []
    for lang in KEVIN_STACK:
        repos = fetch_trending(lang, days=14, limit=4)
        for r in repos:
            desc = (r.get("description") or "")[:80]
            stars = r.get("stargazers_count", 0)
            trend_lines.append(f"[{lang}] {r['full_name']} ({stars}★): {desc}")

    trend_block = (
        "\n".join(trend_lines[:18])
        if trend_lines
        else "(GitHub trends unavailable — generate ideas from Kevin's interests alone)"
    )

    today = datetime.now().strftime("%B %d, %Y")
    prompt = f"""You are Forge, an AI that generates weekend project ideas for Kevin Geng. Today is {today}.

About Kevin:
{KEVIN_CONTEXT}

Currently trending on GitHub (Kevin's stack, last 2 weeks):
{trend_block}

Generate exactly 4 specific, exciting weekend project ideas for Kevin.
For each idea use this exact format:

### N. <punchy name>
**Pitch:** One sentence — what it does and why it's interesting.
**Stack:** Specific tools (e.g. "Python CLI, stdlib only" or "TypeScript + Bun + Telegram Bot API")
**Scope:** e.g. "1 weekend", "2 evenings", "3-4 evenings"
**Wow factor:** The one thing that makes this worth building — a novel angle, unexpected use, or delightful detail.

Rules:
- Ideas should feel *personal* to Kevin — connect to his actual interests and stack
- No enterprise software, no B2B SaaS, no "build a startup" ideas
- At least one idea should involve Claude/AI in an interesting way
- At least one idea should be a fun hack that has nothing to do with AI
- Make the names memorable (clever, punny, or evocative)
- Keep each entry tight — this is a menu, not a novel
- Be inspired by the trending repos but don't just clone them — twist them"""

    result = claude_call(prompt, max_tokens=1500)
    print(result)
    print()


def cmd_plan(args: list[str]):
    """Generate a detailed implementation plan for a project idea."""
    if not args:
        print("Usage: forge plan \"your project idea\"")
        print('Example: forge plan "A CLI that plays lo-fi music based on my current git activity"')
        return

    idea = " ".join(args)
    print(f"📐 Planning: {idea}\n")

    prompt = f"""You are Forge, a technical architect helping Kevin plan a weekend project.

About Kevin:
{KEVIN_CONTEXT}

Project idea: {idea}

Create a detailed but achievable weekend implementation plan. Use this structure:

## What it is
2-sentence description that makes the scope crystal clear.

## Tech stack
Specific tools, libraries, APIs. Prefer zero-dependency Python or stdlib when reasonable.
Note any API keys required and whether they're free.

## Architecture
How the pieces connect. 2-4 sentences max. No diagrams.

## Implementation steps
Numbered list. Each step should be ~30–90 minutes of focused work. Max 8 steps.
Be concrete — name files, functions, commands.

## Stretch goals
2-3 additions if time allows.

## Gotchas
1-2 things likely to surprise Kevin mid-build and how to handle them.

Tone: direct, experienced, like you've built something similar before and know where it goes sideways.
This is a weekend project. Scope mercilessly. The goal is something that works, not something perfect."""

    result = claude_call(prompt, max_tokens=1600)
    print(result)
    print()


def cmd_spark(args: list[str]):
    """One quick surprising project idea — changes every day."""
    # Deterministic daily seed so the idea is consistent within a day
    today = date.today()
    seed = today.day + today.month * 31 + today.year

    sparks = [
        "something that involves the terminal and ambient sound",
        "a creative misuse of a boring, unsexy API",
        "something about food and code intersecting in an unexpected way",
        "a Discord bot that does one weird thing really well",
        "a tool that makes waiting for CI or deploys less boring",
        "something that reads Kevin's commit messages and generates something unexpected from them",
        "a tool that turns GitHub activity into a completely different kind of visualization",
        "something involving maps and an API that shouldn't normally be on a map",
        "a game that can be played entirely in a terminal in under 5 minutes",
        "something that connects two completely unrelated APIs in a clever way",
        "a CLI that gives Kevin a gentle reality check about his coding habits",
        "something involving transit data and personal optimization",
        "a tool that makes recipe scaling or meal planning feel magical",
        "something that sends Kevin a useful notification at exactly the right moment",
    ]
    angle = sparks[seed % len(sparks)]

    print("✨ Forge Spark — one idea, right now\n")

    prompt = f"""Give Kevin one project idea. The creative angle: {angle}.

About Kevin:
{KEVIN_CONTEXT}

Constraints:
- One idea only. Give it a memorable name.
- 4 sentences max: name + what it is, why it's interesting, first concrete step to start building it.
- It should feel like a spark — the kind of idea that makes you open a new file immediately.
- Tone: excited and direct, like a friend just had a good idea over coffee.
- Today is {today.isoformat()}."""

    result = claude_call(prompt, max_tokens=220)
    print(result)
    print()


def cmd_help():
    print("""
⚗️  idea-forge — AI project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Watches what's trending in your GitHub stack, then asks Claude to generate
project ideas tailored specifically to you.

USAGE
    forge <command> [args]

COMMANDS

  trending [language]     Show trending repos in your stack (python/ts/js)
                          Pass a language name to filter (e.g. "forge trending rust")

  suggest                 Generate 4 tailored weekend project ideas
                          Fetches live GitHub trends + consults Claude

  plan "idea"             Detailed implementation plan for a specific idea
                          Example: forge plan "Discord bot that summarizes git activity in haiku"

  spark                   One quick inspiring idea, changes every day
                          Fast creative hit — no trend data needed

  help                    This message

SETUP
    Requires ANTHROPIC_API_KEY for suggest, plan, and spark.
    Optional: GITHUB_TOKEN for higher rate limits (60 → 5000 req/hr).

    Keys auto-loaded from projects/kegbot-claude/.env

EXAMPLES
    forge trending
    forge trending typescript
    forge suggest
    forge plan "A matcha cafe rating tool that only judges the aesthetic, not the taste"
    forge spark

NOTE
    The recursive part: Claude generating ideas for Claude to build for Kevin.
    Forge doesn't know what Forge will suggest. Neither does Kevin.

Built by Claude (Cycle 8). Because the best project is one you actually want to build.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "trending": cmd_trending,
    "suggest": cmd_suggest,
    "plan": cmd_plan,
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
        print(f"❓ Unknown command: {command}")
        print("Run `forge help` for available commands.")
        sys.exit(1)

    COMMANDS[command](rest)


if __name__ == "__main__":
    main()
