#!/usr/bin/env python3
"""
forge — AI project idea generator

Scans trending GitHub repos in Kevin's stack and suggests personalized
weekend project ideas. Powered by Claude. Zero new deps.

Usage:
    forge suggest                    # 3 ideas inspired by trending GitHub repos
    forge suggest --stack python     # Filter to one language
    forge inspire                    # Pure AI brainstorm (no GitHub needed)
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
KEVIN_STACK = ["python", "typescript", "go"]

# Kevin's profile — used in every prompt as grounding context
KEVIN_PROFILE = """
Kevin Geng is a full-stack software engineer at Faire in Toronto.
Stack: React, TypeScript, Java/Spring Boot, Python, AWS.

His GitHub (@keving3ng) shows:
- matchamap.club — opinionated matcha cafe finder (actively building)
- vball-tracker — volleyball tracker (most active repo right now, 15 commits in 90 days)
- kegbot / kegclaude — Python personal assistant (daily briefings, automation, Claude-powered)
- cookbook — cooking/recipes; he's into meal planning and ingredient tools
- claudespace — THIS repo: he's literally running an autonomous Claude build agent
- ML/CV history (face-recog, facenet, Andrew Ng course)
- Discord bots and API integrations (personal + hackathon)
- Transit/status tools (metro-status-update)
- Personal finance automation (transact, private)

What he gravitates toward:
- Small, *complete* tools > half-finished ambitious projects
- Zero-dependency CLIs are his love language
- Things that do one thing brilliantly, with personality
- Automation that gives him back time
- Practical ML (not research, but applied)
- Tools that have a sense of humor

Already building (don't suggest again):
matchamap, kegbot, recipe-ai, dev-insights, idea-forge
"""

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


# ─── GitHub trending search ───────────────────────────────────────────────────


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
        body = e.read().decode("utf-8", errors="replace")
        print(f"[github] HTTP {e.code}: {body[:150]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[github] Error: {e}", file=sys.stderr)
        return None


def fetch_trending_repos(language: str, days: int = 30, limit: int = 6) -> list[dict]:
    """Fetch recently-created popular repos for a language via GitHub search API."""
    since = (date.today() - timedelta(days=days)).isoformat()
    q = urllib.parse.quote(f"language:{language} created:>{since} stars:>5")
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={q}&sort=stars&order=desc&per_page={limit}"
    )
    data = _github_request(url)
    if not isinstance(data, dict):
        return []
    return data.get("items", [])[:limit]


def format_repo_block(repos: list[dict], language: str) -> str:
    """Format a language's trending repos for Claude's context window."""
    if not repos:
        return f"## Trending {language.title()} (none found)\n"

    lines = [f"## Trending {language.title()} (last 30 days, sorted by stars)"]
    for r in repos:
        name = r.get("full_name", "unknown")
        desc = (r.get("description") or "(no description)").strip()
        stars = r.get("stargazers_count", 0)
        topics = ", ".join(r.get("topics", [])[:6]) or "—"
        lines.append(f"\n**{name}**  ⭐ {stars:,}")
        lines.append(f"  {desc[:130]}")
        lines.append(f"  topics: {topics}")

    return "\n".join(lines)


# ─── Claude ───────────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 1000) -> str:
    if not ANTHROPIC_API_KEY:
        return "⚠️  ANTHROPIC_API_KEY not set. Add it to .env in projects/kegbot-claude/."

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
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"[Claude API error {e.code}: {body[:200]}]"
    except Exception as e:
        return f"[Claude API error: {e}]"


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_suggest(args: list[str]):
    """Fetch trending repos + generate personalized project ideas."""
    stack_filter = None
    if "--stack" in args:
        idx = args.index("--stack")
        if idx + 1 < len(args):
            stack_filter = args[idx + 1].lower()

    languages = [stack_filter] if stack_filter else KEVIN_STACK
    today_str = date.today().strftime("%B %d, %Y")

    print(f"💡 forge suggest — scanning GitHub trends ({', '.join(languages)})\n")

    repo_blocks = []
    for lang in languages:
        print(f"   fetching trending {lang} repos...")
        repos = fetch_trending_repos(lang, days=30, limit=6)
        repo_blocks.append(format_repo_block(repos, lang))

    trend_context = "\n\n".join(repo_blocks)

    if not ANTHROPIC_API_KEY:
        print("\n⚠️  ANTHROPIC_API_KEY not set — showing raw trending data only.\n")
        print(trend_context[:2000])
        return

    prompt = f"""You are idea-forge, a creative project idea generator for a specific developer.

Today is {today_str}. You've surveyed what's trending on GitHub and need to translate those trends into personalized project ideas.

---
## Developer Profile
{KEVIN_PROFILE}

---
## What's trending right now
{trend_context}

---
## Your task

Suggest **3 weekend project ideas** for Kevin that:
1. Are *inspired by* (not copies of) the trends above — find the underlying pattern, not the surface feature
2. Fit Kevin's specific stack, interests, and personality
3. Cover the range: one small+delightful, one medium, one slightly ambitious
4. Have real personality — avoid "build a CRUD app" or generic tool suggestions

For each idea format it as:

**[Project Name]**
*Pitch:* 2–3 sentences. What it does, why it's interesting, what makes it not boring.
*Why Kevin:* One sentence on why *specifically Kevin* would love building this.
*Stack:* What to use.
*Weekend scope:* What "done" looks like after 8–10 focused hours.

---

Be creative. Go specific. The weirder and more Kevin-shaped the idea, the better.
Generic ideas are worse than no ideas."""

    print("\n[claude] synthesizing ideas from trending repos...\n")
    result = claude_call(prompt, max_tokens=1400)

    print("─" * 65)
    print(result)
    print("─" * 65)
    print()


def cmd_inspire(args: list[str]):
    """Pure Claude brainstorm — project ideas from Kevin's profile, no GitHub."""
    today_str = date.today().strftime("%B %d, %Y")
    print(f"✨ forge inspire — pure AI brainstorm ({today_str})\n")

    if not ANTHROPIC_API_KEY:
        print("⚠️  ANTHROPIC_API_KEY not set.")
        return

    prompt = f"""You are idea-forge, a creative project idea generator.

Today is {today_str}. You're brainstorming directly from a developer's profile — no trending data, just instinct.

---
## Developer Profile
{KEVIN_PROFILE}

---
## Your task

Generate **3 surprising weekend project ideas** for Kevin that:
- He definitely hasn't thought of yet
- Could realistically be built in a weekend with Python, TypeScript, or Go
- Have a specific, delightful twist that makes them not generic
- Would make Kevin smile when he first reads the idea
- Connect to something real in his life or work

For each, format as:

**[Project Name]**
*Pitch:* What it does and why it's interesting.
*The twist:* The one specific detail that makes this not boring.
*Why now:* Why would Kevin want this today, this month?
*Stack:* What to build it with.

---

Don't play it safe. The best ideas are the ones that make you go "oh, *that's* a thing I didn't know I needed."
"""

    print("[claude] brainstorming...\n")
    result = claude_call(prompt, max_tokens=1000)

    print("─" * 65)
    print(result)
    print("─" * 65)
    print()


def cmd_help():
    print("""
💡 forge — AI project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    forge <command> [options]

COMMANDS

  suggest                    3 ideas inspired by trending GitHub repos
    --stack <lang>             Filter to one language: python, typescript, go

  inspire                    Pure AI brainstorm — no GitHub, just Kevin's profile

  help                       This help text

SETUP
  Requires ANTHROPIC_API_KEY in projects/kegbot-claude/.env or repo root .env.
  GitHub trending uses public search API (no key needed, 30 req/hr limit).
  Add GITHUB_TOKEN to .env for 5000 req/hr.

EXAMPLES
    forge suggest
    forge suggest --stack python
    forge inspire

NOTES
  forge suggest fetches repos created in the last 30 days, sorted by stars.
  Suggestions are always personalized to Kevin's stack and profile.
  Run every few days to catch fresh trends.

Built by Claude (Cycle 8). Ideas are cheap; building is the point.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────


COMMANDS = {
    "suggest": cmd_suggest,
    "inspire": cmd_inspire,
    "help": lambda _: cmd_help(),
    "--help": lambda _: cmd_help(),
    "-h": lambda _: cmd_help(),
}


def main():
    argv = sys.argv[1:]

    if not argv:
        cmd_suggest([])  # default: suggest from trends
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
