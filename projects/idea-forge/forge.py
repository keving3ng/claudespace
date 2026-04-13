#!/usr/bin/env python3
"""
idea-forge — AI-powered weekend project generator

Watches what's trending on GitHub in Kevin's stack, then asks Claude
to suggest project ideas tailored specifically to who Kevin is and
what he builds. The recursive project-idea-generator.

Usage:
    forge ideas                     # 5 tailored ideas from current trends
    forge ideas --lang typescript   # focus on TypeScript trends
    forge trends                    # show trending repos (no idea gen)
    forge trends --lang python
    forge random                    # one wild idea — no GitHub needed
    forge help
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent
DEFAULT_LANGS = ["python", "typescript"]
TRENDS_DAYS = 14

KEVIN_PROFILE = """
Kevin Geng — full-stack engineer at Faire (Toronto).
Stack: React, TypeScript, Python, Java/Kotlin/Spring Boot, AWS.
Active projects:
  - matchamap.club — opinionated matcha cafe finder (maps, place data, GeoJSON)
  - kegbot — personal assistant CLI (Claude-powered, daily briefings, automation)
  - claudespace — autonomous Claude build lab (this is where you live)
  - cookbook — cooking/recipes repo (ingredient tools, meal planning)
Dormant but interesting: face-recog (ML), discord bots, personal finance automation,
  transit notifications, board games, teaching/workshops.
Interests: cooking, ML/AI, Discord bots, personal automation, gaming, maps & place data.
Vibe: builder, pragmatic — fun + useful > perfect.
""".strip()

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

# ─── GitHub Search ─────────────────────────────────────────────────────────────


def github_search(lang: str, days: int = TRENDS_DAYS, per_page: int = 8) -> list[dict]:
    """Search for recently created, high-star repos in a language."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    query = f"language:{lang}+created:>{cutoff}"
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={query}&sort=stars&order=desc&per_page={per_page}"
    )
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "idea-forge/1.0",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data.get("items", [])
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(f"⚠️  GitHub rate limit hit for {lang}. Set GITHUB_TOKEN for more.", file=sys.stderr)
        else:
            body = e.read().decode("utf-8", errors="replace")
            print(f"⚠️  GitHub search failed ({lang}) [{e.code}]: {body[:120]}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"⚠️  GitHub search failed ({lang}): {e}", file=sys.stderr)
        return []


def format_repo_line(repo: dict) -> str:
    """Single-line repo summary for prompt context."""
    name = repo.get("full_name", "?")
    desc = (repo.get("description") or "(no description)")[:80]
    stars = repo.get("stargazers_count", 0)
    topics = repo.get("topics", [])
    topic_str = f"  [{', '.join(topics[:4])}]" if topics else ""
    return f"  ★{stars:<6} {name} — {desc}{topic_str}"


# ─── Claude API ───────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 1200) -> str:
    if not ANTHROPIC_API_KEY:
        return (
            "⚠️  ANTHROPIC_API_KEY not set.\n"
            "Add it to projects/kegbot-claude/.env or the repo root .env.\n"
            "Run `forge trends` to see raw GitHub data without Claude."
        )

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


def get_lang_arg(args: list[str]) -> str | None:
    if "--lang" in args:
        idx = args.index("--lang")
        if idx + 1 < len(args):
            return args[idx + 1].lower()
    if "-l" in args:
        idx = args.index("-l")
        if idx + 1 < len(args):
            return args[idx + 1].lower()
    return None


def cmd_trends(args: list[str]):
    """Show trending repos without generating ideas."""
    lang_arg = get_lang_arg(args)
    langs = [lang_arg] if lang_arg else DEFAULT_LANGS

    print(f"🔭 idea-forge trends — GitHub's hottest new repos (last {TRENDS_DAYS} days)\n")

    for lang in langs:
        header = f"── {lang.capitalize()} "
        print(header + "─" * max(0, 55 - len(header)))
        repos = github_search(lang, days=TRENDS_DAYS)
        if not repos:
            print("  (no results, or rate-limited — add GITHUB_TOKEN to .env)")
            print()
            continue
        for r in repos:
            stars = r.get("stargazers_count", 0)
            name = r.get("full_name", "?")
            desc = (r.get("description") or "(no description)")[:70]
            url = r.get("html_url", "")
            topics = r.get("topics", [])
            topic_str = f"  [{', '.join(topics[:4])}]" if topics else ""
            print(f"  ★{stars:<6}  {name}")
            print(f"             {desc}{topic_str}")
            print(f"             {url}")
            print()


def cmd_ideas(args: list[str]):
    """Fetch trends and generate tailored project ideas via Claude."""
    lang_arg = get_lang_arg(args)
    langs = [lang_arg] if lang_arg else DEFAULT_LANGS

    print("💡 idea-forge — generating project ideas for Kevin\n")
    print(f"🔭 Scanning GitHub trends (last {TRENDS_DAYS} days)...")

    all_repos: dict[str, list[dict]] = {}
    for lang in langs:
        repos = github_search(lang, days=TRENDS_DAYS, per_page=8)
        all_repos[lang] = repos
        print(f"   {lang.capitalize()}: {len(repos)} trending repo(s)")

    # Build trend context for the prompt
    trend_lines: list[str] = []
    total_repos = sum(len(v) for v in all_repos.values())
    for lang, repos in all_repos.items():
        if repos:
            trend_lines.append(f"\n### Trending {lang.capitalize()} repos (last {TRENDS_DAYS} days)\n")
            for r in repos[:6]:
                trend_lines.append(format_repo_line(r))

    if total_repos == 0:
        trend_context = (
            "(No trending data available — GitHub API may be rate-limited. "
            "Ideas will be based on Kevin's profile only.)"
        )
    else:
        trend_context = "\n".join(trend_lines)

    print("\n⚡ Generating ideas via Claude...\n")

    today = datetime.now().strftime("%B %d, %Y")

    prompt = f"""You are idea-forge, Kevin's AI project idea generator. Today is {today}.

### Who Kevin is
{KEVIN_PROFILE}

### What's trending on GitHub right now
{trend_context}

### Your job
Generate exactly 5 weekend project ideas for Kevin. Make them specific, personal, and surprising.

For each idea, follow this exact format — no deviations:

**[N]. [Project Name]**
[One punchy sentence: what it does and why it's useful to Kevin specifically]

Stack: [comma-separated, use his actual stack: Python, TypeScript, React, etc.]
Effort: [one of: afternoon | full day | full weekend]

Steps:
1. [Concrete first step — ends with a specific deliverable]
2. [Second step — also concrete]
3. [Third step — the thing that makes it actually usable]

---

Rules:
- NOT generic: no "CRUD app", no "todo list", no "social platform". These must feel like Kevin built them.
- At least 2 ideas should connect to his active projects (matchamap, kegbot, cookbook, claudespace).
- At least 1 idea should be playful or surprising — something he didn't ask for but will love.
- Use trending repos as INSPIRATION for patterns and ideas, not to clone them.
- Be specific about what the tool does: "a CLI that reads..." not "an app for..."
- Steps should have concrete deliverables: "outputs a JSON file", "renders a table", "serves on :5001"
- Velocity and fun matter more than polish.
"""

    result = claude_call(prompt, max_tokens=1500)

    print("═" * 62)
    print(result)
    print("═" * 62)
    print()
    print("💾 Run `forge trends` to browse the raw GitHub data.")
    print("🔁 Run again for different ideas — Claude thinks differently each time.\n")


def cmd_random(args: list[str]):
    """Generate one wild idea without fetching GitHub trends."""
    print("🎲 idea-forge random — one idea, no trends, pure Kevin\n")
    print("[claude] Rolling the dice...\n")

    today = datetime.now().strftime("%B %d, %Y")

    prompt = f"""You are idea-forge. Today is {today}.

### Who Kevin is
{KEVIN_PROFILE}

Generate ONE surprising, specific, delightful weekend project idea for Kevin.
It should feel personal — something built for him, not for a generic developer.

Format exactly as:

**[Project Name]** — [one-sentence description]

Why Kevin: [one sentence explaining why this fits Kevin specifically]
Stack: [comma-separated]
The hook: [the one thing that makes this idea genuinely interesting, in one sentence]
First move: [the single first thing to build this weekend — concrete, ends with a deliverable]
"""

    result = claude_call(prompt, max_tokens=350)
    print(result)
    print()


def cmd_help():
    print("""
💡 idea-forge — AI-powered weekend project generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    forge <command> [options]

COMMANDS

  ideas                       Generate 5 tailored ideas from GitHub trends
    --lang python|typescript    Focus on one language's trends
    -l python|typescript        Shorthand for --lang
                                (default: python + typescript)

  trends                      Show trending repos — no idea gen
    --lang / -l <lang>          Filter to one language

  random                      One wild idea — no GitHub needed, instant

  help                        Show this help

SETUP
  Requires ANTHROPIC_API_KEY in .env for idea generation.
  GITHUB_TOKEN optional — increases rate limit 60 → 5000 req/hr.
  Looks for .env in: this directory, repo root, or kegbot-claude/

HOW IT WORKS
  1. Searches GitHub for repos created in the last 14 days, sorted by stars
  2. Feeds those trends + Kevin's profile to Claude Opus
  3. Claude generates ideas that are surprising, personal, and buildable in a weekend
  4. Run again for fresh ideas — they'll be different every time

EXAMPLES
    forge ideas
    forge ideas --lang typescript
    forge trends
    forge trends -l python
    forge random

Built by Claude (Cycle 8). The recursive project-idea-generator.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "ideas": cmd_ideas,
    "trends": cmd_trends,
    "random": cmd_random,
    "help": cmd_help,
    "--help": cmd_help,
    "-h": cmd_help,
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
        print("Run `forge help` for available commands.")
        sys.exit(1)

    if command in ("help", "--help", "-h"):
        COMMANDS[command]()
    else:
        COMMANDS[command](rest)


if __name__ == "__main__":
    main()
